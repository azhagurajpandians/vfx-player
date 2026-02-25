"""
PlayerCore: Handles EXR sequence loading and playback logic with async caching.

Architecture:
  - FrameLoader uses SEPARATE queues for video vs image sequence loading.
  - Video: 1 dedicated sequential-read thread. Tries cv2 first; if cv2 can't
    open the file (e.g. ProRes), falls back to FFmpeg subprocess pipe.
  - Sequence: N threads for parallel I/O via OIIO. Workers also apply OCIO
    colorconvert so the cache stores DISPLAY-READY float32.
  - The main thread only does fast exposure/gamma (vectorized numpy).
"""
import os
import sys
import glob
import time
import subprocess
import shutil
import threading
import queue
import collections
import numpy as np
import traceback
from dataclasses import dataclass
from typing import List, Optional, Tuple, Dict, Any

@dataclass
class MediaInfo:
    path: str
    type: str  # 'sequence' or 'video'
    frame_count: int
    size: Tuple[int, int]
    fps: float


# ---------------------------------------------------------------------------
# FFmpeg helpers
# ---------------------------------------------------------------------------

def _find_ffmpeg():
    """Locate ffmpeg binary: bundled first, .knacktools, then system PATH."""
    if getattr(sys, 'frozen', False):
        app_dir = os.path.dirname(sys.executable)
    else:
        app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # Check bundled locations (order: most specific first)
    search_dirs = [
        os.path.join(app_dir, 'bin', 'ffmpeg', 'windows', 'bin'),
        os.path.join(app_dir, 'bin', 'ffmpeg'),
        os.path.join(app_dir, 'ffmpeg'),
        os.path.join(app_dir, 'bin'),
        app_dir,
    ]

    # .knacktools locations (production machines)
    home = os.path.expanduser('~')
    for root in [home, 'C:\\', 'D:\\', 'E:\\']:
        search_dirs.append(os.path.join(root, '.knacktools', 'ffmpeg', 'bin'))
        search_dirs.append(os.path.join(root, '.knacktools', 'ffmpeg'))
        search_dirs.append(os.path.join(root, '.knacktools', 'bin'))

    for d in search_dirs:
        candidate = os.path.join(d, 'ffmpeg.exe')
        if os.path.isfile(candidate):
            return candidate

    # System PATH
    found = shutil.which('ffmpeg')
    if found:
        return found
    return None


def _find_ffprobe():
    """Locate ffprobe binary: bundled first, .knacktools, then system PATH."""
    if getattr(sys, 'frozen', False):
        app_dir = os.path.dirname(sys.executable)
    else:
        app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    search_dirs = [
        os.path.join(app_dir, 'bin', 'ffmpeg', 'windows', 'bin'),
        os.path.join(app_dir, 'bin', 'ffmpeg'),
        os.path.join(app_dir, 'ffmpeg'),
        os.path.join(app_dir, 'bin'),
        app_dir,
    ]

    # .knacktools locations (production machines)
    home = os.path.expanduser('~')
    for root in [home, 'C:\\', 'D:\\', 'E:\\']:
        search_dirs.append(os.path.join(root, '.knacktools', 'ffmpeg', 'bin'))
        search_dirs.append(os.path.join(root, '.knacktools', 'ffmpeg'))
        search_dirs.append(os.path.join(root, '.knacktools', 'bin'))

    for d in search_dirs:
        candidate = os.path.join(d, 'ffprobe.exe')
        if os.path.isfile(candidate):
            return candidate

    found = shutil.which('ffprobe')
    if found:
        return found
    return None


def probe_video(path: str) -> dict:
    """Use ffprobe to get video metadata. Returns dict with fps, width, height, frame_count."""
    ffprobe = _find_ffprobe()
    if not ffprobe:
        return {}
    try:
        cmd = [
            ffprobe, '-v', 'quiet',
            '-select_streams', 'v:0',
            '-show_entries', 'stream=width,height,r_frame_rate,nb_frames,duration',
            '-show_entries', 'format=duration',
            '-of', 'csv=p=0',
            path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10,
                                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
        if result.returncode != 0:
            return {}

        lines = [l.strip() for l in result.stdout.strip().split('\n') if l.strip()]
        info = {}
        if lines:
            # First line: stream info: width,height,r_frame_rate,nb_frames,duration
            parts = lines[0].split(',')
            if len(parts) >= 3:
                info['width'] = int(parts[0]) if parts[0] else 1920
                info['height'] = int(parts[1]) if parts[1] else 1080
                # Parse frame rate fraction (e.g. "24/1" or "24000/1001")
                fps_str = parts[2]
                if '/' in fps_str:
                    num, den = fps_str.split('/')
                    info['fps'] = float(num) / float(den) if float(den) else 24.0
                else:
                    info['fps'] = float(fps_str) if fps_str else 24.0

                # nb_frames
                if len(parts) >= 4 and parts[3] and parts[3] != 'N/A':
                    info['frame_count'] = int(parts[3])
                # stream duration
                if len(parts) >= 5 and parts[4] and parts[4] != 'N/A':
                    info['duration'] = float(parts[4])

            # Second line might be format duration
            if len(lines) > 1 and 'duration' not in info:
                try:
                    info['duration'] = float(lines[1])
                except (ValueError, IndexError):
                    pass

        # Estimate frame count from duration if not available
        if 'frame_count' not in info and 'duration' in info and 'fps' in info:
            info['frame_count'] = int(info['duration'] * info['fps'])

        return info
    except Exception:
        return {}


class FFmpegReader:
    """Read video frames via FFmpeg subprocess pipe. Supports ProRes, DNxHR, etc."""

    def __init__(self, path: str, width: int, height: int):
        self.path = path
        self.width = width
        self.height = height
        self.frame_size = width * height * 3  # RGB24
        self._proc = None
        self._current_frame = 0
        self._ffmpeg = _find_ffmpeg()

    def _start_process(self, start_frame: int = 0, fps: float = 24.0):
        """Start or restart FFmpeg subprocess at given frame."""
        self.close()
        if not self._ffmpeg:
            return False

        cmd = [self._ffmpeg, '-hide_banner', '-loglevel', 'error']

        # Seek to start_frame if not 0
        if start_frame > 0:
            seek_sec = start_frame / fps
            cmd.extend(['-ss', f'{seek_sec:.4f}'])

        cmd.extend([
            '-i', self.path,
            '-f', 'rawvideo',
            '-pix_fmt', 'rgb24',
            '-v', 'error',
            '-'
        ])

        try:
            self._proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=self.frame_size * 4,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
            )
            self._current_frame = start_frame
            return True
        except Exception:
            traceback.print_exc()
            return False

    def read_frame(self, target_index: int, fps: float = 24.0):
        """Read frame at target_index. Returns RGB uint8 numpy array or None."""
        if self._proc is None or self._proc.poll() is not None:
            if not self._start_process(target_index, fps):
                return None

        # If target is behind current position or too far ahead, seek
        if target_index < self._current_frame or target_index > self._current_frame + 100:
            if not self._start_process(target_index, fps):
                return None

        # Skip frames to reach target
        while self._current_frame < target_index:
            skip_data = self._proc.stdout.read(self.frame_size)
            if len(skip_data) < self.frame_size:
                # EOF or error, restart at target
                if not self._start_process(target_index, fps):
                    return None
                break
            self._current_frame += 1

        # Read target frame
        raw = self._proc.stdout.read(self.frame_size)
        if len(raw) < self.frame_size:
            return None

        self._current_frame += 1
        frame = np.frombuffer(raw, dtype=np.uint8).reshape((self.height, self.width, 3))
        return frame

    def close(self):
        if self._proc is not None:
            try:
                self._proc.stdout.close()
                self._proc.kill()
                self._proc.wait(timeout=2)
            except Exception:
                pass
            self._proc = None

    @property
    def is_available(self):
        return self._ffmpeg is not None


class FrameLoader:
    def __init__(self, cache_ref: collections.OrderedDict, cache_lock: threading.Lock,
                 seq_workers: int = 4):
        self._seq_queue = queue.PriorityQueue()
        self._vid_queue = queue.PriorityQueue()
        self.lock = threading.Lock()
        self.stopping = False
        self.cache_ref = cache_ref
        self.cache_lock = cache_lock
        self.seq_workers_count = seq_workers
        self._threads = []
        self.session_id = 0

        # OCIO params for background processing
        self.ocio_enabled = False
        self.ocio_input_cs = None
        self.ocio_output_cs = None
        self.ocio_config_path = None

        self._oiio_loaded = False
        try:
            global oiio
            import OpenImageIO as oiio
            self._oiio_loaded = True
        except ImportError:
            pass

    def start(self):
        for i in range(self.seq_workers_count):
            t = threading.Thread(target=self._seq_worker_loop, daemon=True, name=f"SeqLoader-{i}")
            t.start()
            self._threads.append(t)
        t = threading.Thread(target=self._video_worker_loop, daemon=True, name="VideoLoader")
        t.start()
        self._threads.append(t)

    def _is_video(self, path: str) -> bool:
        return path.lower().endswith(('.mov', '.mp4', '.avi', '.mkv', '.mxf'))

    def request(self, path: str, index: int, priority: int):
        if self.stopping:
            return
        item = (priority, time.time(), index, path)
        if self._is_video(path):
            self._vid_queue.put(item)
        else:
            self._seq_queue.put(item)

    def clear_pending(self):
        with self.lock:
            self._seq_queue = queue.PriorityQueue()
            self._vid_queue = queue.PriorityQueue()
            self.session_id += 1

    def stop(self):
        self.stopping = True

    def set_ocio_params(self, enabled, input_cs, output_cs, config_path):
        """Called from main thread when OCIO params change."""
        self.ocio_enabled = enabled
        self.ocio_input_cs = input_cs
        self.ocio_output_cs = output_cs
        self.ocio_config_path = config_path

    def _apply_ocio(self, disp):
        """Apply OIIO colorconvert. Called from background threads."""
        if not self.ocio_enabled or not self._oiio_loaded:
            return disp
        if not self.ocio_input_cs or not self.ocio_output_cs:
            return disp
        try:
            h, w, c = disp.shape
            if not disp.flags['C_CONTIGUOUS']:
                disp = np.ascontiguousarray(disp)
            spec = oiio.ImageSpec(w, h, c, oiio.TypeFloat)
            buf = oiio.ImageBuf(spec)
            buf.set_pixels(oiio.ROI(), disp)

            in_cs = self.ocio_input_cs
            out_cs = self.ocio_output_cs
            cfg = self.ocio_config_path or ""

            res_buf = oiio.ImageBufAlgo.colorconvert(buf, in_cs, out_cs, False, cfg)

            if not res_buf.has_error:
                raw = res_buf.get_pixels(oiio.TypeFloat)
                return np.array(raw, dtype=np.float32).reshape((h, w, c))
        except Exception:
            traceback.print_exc()
        return disp

    def _video_worker_loop(self):
        """Video worker: sequential read-ahead ring buffer.
        
        Instead of seeking per-frame (extremely slow with cv2), this reads
        frames sequentially forward from the current playback position.
        When a seek is needed (scrub/reverse), it repositions once and
        resumes sequential reading. This matches how RV/DJV achieve
        real-time playback.
        """
        import cv2

        _cap = None           # cv2.VideoCapture
        _ffmpeg_reader = None  # FFmpegReader fallback
        _cap_path = None
        _use_ffmpeg = False
        _local_session = self.session_id
        _media_fps = 24.0
        _next_seq_frame = -1  # Next frame to read sequentially
        _inv255 = np.float32(1.0 / 255.0)

        while not self.stopping:
            if self.session_id != _local_session:
                # Session changed — release resources
                if _cap is not None:
                    try: _cap.release()
                    except: pass
                    _cap = None
                if _ffmpeg_reader is not None:
                    _ffmpeg_reader.close()
                    _ffmpeg_reader = None
                _cap_path = None
                _use_ffmpeg = False
                _next_seq_frame = -1
                _local_session = self.session_id

            try:
                item = self._vid_queue.get(timeout=0.02)
                priority, _, index, path = item

                with self.cache_lock:
                    if index in self.cache_ref:
                        continue

                # Open video source if needed
                if _cap_path != path:
                    # Release old
                    if _cap is not None:
                        try: _cap.release()
                        except: pass
                        _cap = None
                    if _ffmpeg_reader is not None:
                        _ffmpeg_reader.close()
                        _ffmpeg_reader = None
                    _use_ffmpeg = False
                    _cap_path = path
                    _next_seq_frame = -1

                    # Try cv2 first
                    _cap = cv2.VideoCapture(path)
                    if _cap.isOpened():
                        _media_fps = _cap.get(cv2.CAP_PROP_FPS) or 24.0
                        _use_ffmpeg = False
                    else:
                        # cv2 failed — fall back to FFmpeg
                        _cap.release()
                        _cap = None
                        info = probe_video(path)
                        w = info.get('width', 1920)
                        h = info.get('height', 1080)
                        _media_fps = info.get('fps', 24.0)
                        _ffmpeg_reader = FFmpegReader(path, w, h)
                        if _ffmpeg_reader.is_available:
                            _use_ffmpeg = True
                        else:
                            _ffmpeg_reader = None
                            continue

                # --- Sequential read-ahead strategy ---
                # Only seek if the requested frame is NOT the next sequential frame
                need_seek = (_next_seq_frame != index)

                frame = None
                if _use_ffmpeg and _ffmpeg_reader:
                    raw = _ffmpeg_reader.read_frame(index, _media_fps)
                    if raw is not None:
                        frame = raw.astype(np.float32) * _inv255
                    _next_seq_frame = index + 1
                elif _cap is not None and _cap.isOpened():
                    if need_seek:
                        _cap.set(cv2.CAP_PROP_POS_FRAMES, index)
                    ret, bgr = _cap.read()
                    if ret:
                        frame = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB).astype(np.float32) * _inv255
                    _next_seq_frame = index + 1

                if frame is not None:
                    with self.cache_lock:
                        if index not in self.cache_ref:
                            self.cache_ref[index] = frame

                    # --- Read-ahead burst: fill cache with next N frames sequentially ---
                    if not _use_ffmpeg and _cap is not None and _cap.isOpened():
                        for ahead in range(_next_seq_frame, _next_seq_frame + 8):
                            if self.session_id != _local_session or self.stopping:
                                break
                            with self.cache_lock:
                                if ahead in self.cache_ref:
                                    continue
                            ret, bgr = _cap.read()
                            if not ret:
                                break
                            fr = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB).astype(np.float32) * _inv255
                            with self.cache_lock:
                                if ahead not in self.cache_ref:
                                    self.cache_ref[ahead] = fr
                            _next_seq_frame = ahead + 1

            except queue.Empty:
                continue
            except Exception:
                traceback.print_exc()

    def _seq_worker_loop(self):
        _local_session = self.session_id

        while not self.stopping:
            if self.session_id != _local_session:
                _local_session = self.session_id

            try:
                item = self._seq_queue.get(timeout=0.05)
                priority, _, index, path = item

                with self.cache_lock:
                    if index in self.cache_ref:
                        continue

                frame = self._load_image(path)

                if frame is not None:
                    frame = self._apply_ocio(frame)

                    with self.cache_lock:
                        if index not in self.cache_ref:
                            self.cache_ref[index] = frame

            except queue.Empty:
                continue
            except Exception:
                traceback.print_exc()

    def _load_image(self, path: str):
        if not self._oiio_loaded:
            return None
        try:
            inp = oiio.ImageInput.open(path)
            if not inp:
                return None
            try:
                fmt = oiio.TypeFloat
            except AttributeError:
                fmt = oiio.TypeDesc(oiio.FLOAT)
            raw_data = inp.read_image(format=fmt)
            spec = inp.spec()
            inp.close()
            if raw_data is None:
                return None
            n_ch = spec.nchannels
            if n_ch >= 3:
                rgb = raw_data[:, :, :3]
            elif n_ch == 1:
                rgb = np.repeat(raw_data[:, :, np.newaxis], 3, axis=2)
            else:
                rgb = np.repeat(raw_data[:, :, 0:1], 3, axis=2)
            return np.ascontiguousarray(rgb, dtype=np.float32)
        except Exception as e:
            print(f"Error loading {path}: {e}")
            traceback.print_exc()
            return None


class PlaybackClock:
    def __init__(self):
        self.samples = collections.deque(maxlen=12)
        self.last_time = time.time()
        self.last_frame = 0

    def update(self, frame):
        now = time.time()
        dt = now - self.last_time
        df = abs(frame - self.last_frame)
        if dt > 0 and 0 < df < 5:
            self.samples.append(df / dt)
        self.last_time = now
        self.last_frame = frame

    def speed(self):
        return sum(self.samples) / len(self.samples) if self.samples else 24.0

class PlayerCore:
    def __init__(self, cache_capacity: int = 500, prefetch_enabled: bool = True):
        self.sequence: List[str] = []
        self.current_frame: int = 0
        self.cache_capacity = cache_capacity
        self.prefetch_enabled = prefetch_enabled
        self.media: Optional[MediaInfo] = None

        self.cache_lock = threading.Lock()
        self.cache = collections.OrderedDict()

        self.clock = PlaybackClock()
        self.last_direction = 1

        self.loader = FrameLoader(self.cache, self.cache_lock, seq_workers=4)
        self.loader.start()

    def load_sequence(self, folder_path):
        self.sequence = sorted(glob.glob(os.path.join(folder_path, '*.exr')))
        self.current_frame = 0
        if self.sequence:
            self.media = MediaInfo(path=folder_path, type='sequence', frame_count=len(self.sequence), size=(0,0), fps=24.0)

    def load(self, path: str):
        with self.cache_lock:
            self.cache.clear()
            self.loader.clear_pending()

        if os.path.isfile(path):
            folder = os.path.dirname(path)
            if path.lower().endswith('.exr'):
                self.sequence = sorted(glob.glob(os.path.join(folder, '*.exr')))
                if not self.sequence:
                    self.sequence = [path]
                self.media = MediaInfo(path=folder, type='sequence', frame_count=len(self.sequence), size=(0,0), fps=24.0)
            else:
                import cv2
                self.sequence = [path]
                fc, fps, w, h = 100, 24.0, 1920, 1080

                # Try cv2 for metadata first
                try:
                    cap = cv2.VideoCapture(path)
                    if cap.isOpened():
                        fc = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                        fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
                        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                        cap.release()
                    else:
                        # cv2 can't open (ProRes etc.) — use ffprobe
                        cap.release()
                        info = probe_video(path)
                        if info:
                            w = info.get('width', 1920)
                            h = info.get('height', 1080)
                            fps = info.get('fps', 24.0)
                            fc = info.get('frame_count', 100)
                except Exception:
                    # Last resort: try ffprobe
                    info = probe_video(path)
                    if info:
                        w = info.get('width', 1920)
                        h = info.get('height', 1080)
                        fps = info.get('fps', 24.0)
                        fc = info.get('frame_count', 100)

                self.media = MediaInfo(path=path, type='video', frame_count=fc, size=(w,h), fps=fps)

    def get_frame_count(self):
        return self.media.frame_count if self.media else 0

    def frame_count(self) -> int:
        return self.media.frame_count if self.media else 0

    def media_fps(self) -> float:
        return float(self.media.fps) if self.media else 24.0

    def get_frame(self, index: int):
        if self.media is None or not (0 <= index < self.media.frame_count):
            return None

        if index != self.current_frame:
            direction = 1 if index > self.current_frame else -1
            self.last_direction = direction
            self.clock.update(index)
            self.current_frame = index

        # Check cache (release lock BEFORE calling prefetch!)
        frame = None
        with self.cache_lock:
            if index in self.cache:
                self.cache.move_to_end(index)
                frame = self.cache[index]

        if frame is not None:
            # Prefetch OUTSIDE the lock to avoid deadlock
            if self.prefetch_enabled:
                self.predictive_prefetch(index, self.last_direction)
            return frame

        # Cache miss
        path = self._get_path(index)
        self.loader.request(path, index, priority=0)
        if self.prefetch_enabled:
             self.predictive_prefetch(index, self.last_direction)
        return None

    def _get_path(self, index: int) -> str:
        if self.media.type == 'video':
            return self.sequence[0]
        return self.sequence[index]

    def predictive_prefetch(self, current_index: int, direction: int):
        if not self.prefetch_enabled or not self.media:
            return
        cnt = self.media.frame_count
        fps = self.clock.speed()
        future_frame = current_index + int(fps * 0.8 * direction)

        # Large prefetch zone: 24 frames (1 second at 24fps)
        zone_size = 24
        for f in range(future_frame - zone_size, future_frame + zone_size):
            if 0 <= f < cnt:
                with self.cache_lock:
                    if f not in self.cache:
                        self.loader.request(self._get_path(f), f, priority=1)

        # Fill gap between current and future prediction
        if abs(future_frame - current_index) < 200:
             r = range(current_index + 1, future_frame) if direction > 0 else range(current_index - 1, future_frame, -1)
             for f in r:
                if 0 <= f < cnt:
                    with self.cache_lock:
                        if f not in self.cache:
                            self.loader.request(self._get_path(f), f, priority=2)
        self._prune_cache()

    def burst_prefetch(self, start_index: int, count: int = 48):
        """Aggressively prefetch `count` frames forward from start_index.
        Called on play() start to fill the cache pipeline."""
        if not self.media:
            return
        cnt = self.media.frame_count
        for f in range(start_index, min(start_index + count, cnt)):
            with self.cache_lock:
                if f not in self.cache:
                    self.loader.request(self._get_path(f), f, priority=0)

    def _prune_cache(self):
        with self.cache_lock:
            while len(self.cache) > self.cache_capacity:
                self.cache.popitem(last=False)

    def set_cache_capacity(self, capacity: int):
        self.cache_capacity = capacity
        self._prune_cache()

    def cache_stats(self):
        with self.cache_lock:
            count = len(self.cache)
        cap = self.cache_capacity
        pct = (count / cap * 100.0) if cap > 0 else 0.0
        return count, cap, pct
