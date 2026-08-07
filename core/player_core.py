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
import enum
import av
from dataclasses import dataclass
from typing import List, Optional, Tuple, Dict, Any

class PlaybackStrategy(enum.Enum):
    PERFORMANCE = "performance"  # Full aggressive caching
    PROGRESSIVE = "progressive"  # Sequential foreground lead
    STREAM = "stream"           # Zero RAM caching, direct pipe
    READ_BEHIND = "readbehind"  # Performance + keep N frames behind

@dataclass
class MediaInfo:
    path: str
    type: str  # 'sequence' or 'video'
    frame_count: int
    size: Tuple[int, int]
    fps: float
    format: str = ""
    codec: str = ""
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


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
            '-show_entries', 'stream=width,height,r_frame_rate,nb_frames,duration,codec_name,codec_long_name',
            '-show_entries', 'format=duration,format_name,format_long_name',
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
            # First line: stream info: width,height,r_frame_rate,nb_frames,duration,codec_name,codec_long_name
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
                
                # codec
                if len(parts) >= 6 and parts[5]:
                    info['codec'] = parts[5]
                if len(parts) >= 7 and parts[6]:
                    info['codec_long'] = parts[6]

            # Second line might be format info: duration,format_name,format_long_name
            if len(lines) > 1:
                fparts = lines[1].split(',')
                if 'duration' not in info and fparts[0]:
                    try:
                        info['duration'] = float(fparts[0])
                    except (ValueError, IndexError):
                        pass
                if len(fparts) >= 2 and fparts[1]:
                    info['format'] = fparts[1]
                if len(fparts) >= 3 and fparts[2]:
                    info['format_long'] = fparts[2]

        # Estimate frame count from duration if not available
        if 'frame_count' not in info and 'duration' in info and 'fps' in info:
            info['frame_count'] = int(info['duration'] * info['fps'])

        return info
    except Exception:
        return {}


class FFmpegReader:
    """Read video frames via PyAV wrapper. Supports ProRes, DNxHR, etc. with native seeking."""

    def __init__(self, path: str, width: int, height: int):
        self.path = path
        self.width = width
        self.height = height
        self._container = None
        self._stream = None
        self._current_frame = -1
        self._frames_generator = None
        self.is_available = True
        self._open()

    def _open(self):
        try:
            self._container = av.open(self.path)
            self._stream = self._container.streams.video[0]
            # Enable multi-threaded decoding in PyAV natively
            self._stream.thread_type = "AUTO"
            self._frames_generator = None
            self._current_frame = -1
        except Exception:
            traceback.print_exc()

    def read_frame(self, target_index: int, fps: float = 24.0, seek: bool = False):
        """Read frame at target_index. Returns RGB uint8 numpy array or None."""
        if not self._container:
            self._open()
            if not self._container:
                return None

        # Seek if forced, target is backwards, or target is significantly ahead (>30 frames)
        need_seek = seek or (self._current_frame < 0) or (target_index < self._current_frame) or (target_index > self._current_frame + 30)

        if need_seek:
            try:
                time_base = float(self._stream.time_base)
                sec = target_index / fps
                pts = int(sec / time_base)
                
                self._container.seek(pts, stream=self._stream)
                self._frames_generator = self._container.decode(self._stream)
                self._current_frame = -1
            except Exception:
                traceback.print_exc()
                self._open()
                try:
                    time_base = float(self._stream.time_base)
                    sec = target_index / fps
                    pts = int(sec / time_base)
                    self._container.seek(pts, stream=self._stream)
                    self._frames_generator = self._container.decode(self._stream)
                    self._current_frame = -1
                except Exception:
                    return None

        frame = None
        while True:
            try:
                av_frame = next(self._frames_generator)
                if av_frame.pts is not None:
                    time_base = float(self._stream.time_base)
                    pts_sec = av_frame.pts * time_base
                    curr_idx = int(round(pts_sec * fps))
                else:
                    curr_idx = self._current_frame + 1

                self._current_frame = curr_idx

                if self._current_frame == target_index:
                    frame = av_frame.to_ndarray(format='rgb24')
                    break
                elif self._current_frame > target_index:
                    frame = av_frame.to_ndarray(format='rgb24')
                    break
            except (StopIteration, av.AVError):
                break
            except Exception:
                traceback.print_exc()
                break

        return frame

    def close(self):
        if self._container:
            try:
                self._container.close()
            except Exception:
                pass
            self._container = None
            self._stream = None
            self._frames_generator = None
            self._current_frame = -1


class FrameLoader:
    def __init__(self, cache_ref: collections.OrderedDict, cache_lock: threading.Lock,
                 seq_workers: int = 4):
        self._seq_queue = queue.PriorityQueue()
        self._vid_queue = queue.PriorityQueue()
        self.lock = threading.Lock()
        self.stopping = False
        self.cache_ref = cache_ref
        self.cache_lock = cache_lock
        self.cache_capacity = 500  # Default, synced from PlayerCore
        self.seq_workers_count = seq_workers
        self._threads = []
        self.session_id = 0
        self.strategy = PlaybackStrategy.PERFORMANCE
        self.read_behind_count = 12

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
        
        # Check if already in cache (quick check without lock first)
        if index in self.cache_ref:
            return

        item = (priority, time.time(), index, path)
        if self._is_video(path):
            if priority == 0:
                with self.lock:
                    self._vid_queue = queue.PriorityQueue()
            self._vid_queue.put(item)
        else:
            if priority == 0:
                with self.lock:
                    self._seq_queue = queue.PriorityQueue()
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
                        # Synchronize next_seq_frame even if we skip
                        if index >= _next_seq_frame:
                            _next_seq_frame = index + 1
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
                # Only seek if it's a backwards jump or a significant forward jump
                # (Reading sequential through the pipe is faster than re-starting FFmpeg)
                need_seek = (_next_seq_frame != index)
                if not need_seek:
                    pass # Already where we need to be
                elif index > _next_seq_frame and index < _next_seq_frame + 24:
                    # Minor forward jump? Just read-skip to keep the pipe alive
                    need_seek = False
                
                frame = None
                if _use_ffmpeg and _ffmpeg_reader:
                    raw = _ffmpeg_reader.read_frame(index, _media_fps, seek=need_seek)
                    if raw is not None:
                        # Keep as uint8 to save 4x bandwidth and memory
                        # GPU handles normalization [0, 255] -> [0, 1]
                        frame = raw
                    _next_seq_frame = index + 1
                elif _cap is not None and _cap.isOpened():
                    if need_seek:
                        _cap.set(cv2.CAP_PROP_POS_FRAMES, index)
                    ret, bgr = _cap.read()
                    if ret:
                        # Keep as uint8 (BGR -> RGB)
                        frame = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
                    _next_seq_frame = index + 1

                if frame is not None:
                    # Cache the frame. Strategy handling is now in PlayerCore.get_frame
                    # and cache pruning logic.
                    with self.cache_lock:
                        if index not in self.cache_ref:
                            self.cache_ref[index] = frame
                    
                    _next_seq_frame = index + 1

                    # --- Read-ahead burst ---
                    # Only prefetch if NOT in STREAM mode
                    if self.strategy != PlaybackStrategy.STREAM:
                        for ahead in range(_next_seq_frame, _next_seq_frame + 16): 
                            if self.session_id != _local_session or self.stopping:
                                break
                            with self.cache_lock:
                                if ahead in self.cache_ref:
                                    _next_seq_frame = ahead + 1
                                    continue
                            
                            if _use_ffmpeg and _ffmpeg_reader:
                                # Sequential read (no seek)
                                raw = _ffmpeg_reader.read_frame(ahead, _media_fps, seek=False)
                                if raw is not None:
                                    # Always keep as uint8 for video burst
                                    fr = raw
                                        
                                    with self.cache_lock:
                                        self.cache_ref[ahead] = fr
                                        # Enforce capacity in worker
                                        while len(self.cache_ref) > self.cache_capacity:
                                            self.cache_ref.popitem(last=False)
                                    _next_seq_frame = ahead + 1
                                else:
                                    break
                            elif _cap is not None and _cap.isOpened():
                                ret, bgr = _cap.read()
                                if not ret:
                                    break
                                # Keep as uint8
                                fr = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
                                    
                                with self.cache_lock:
                                    self.cache_ref[ahead] = fr
                                    # Enforce capacity
                                    while len(self.cache_ref) > self.cache_capacity:
                                        self.cache_ref.popitem(last=False)
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
                            # Enforce capacity in worker
                            while len(self.cache_ref) > self.cache_capacity:
                                self.cache_ref.popitem(last=False)

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
        self.cache_enabled = True  # Toggle for enable/disable cache
        self.cache_gb = 4.0  # Default 4 GB memory budget
        self.strategy = PlaybackStrategy.PERFORMANCE
        self.read_behind_count = 12
        self._frame_mem_bytes = 0  # Auto-set when first frame is cached
        self.media: Optional[MediaInfo] = None

        self.cache_lock = threading.Lock()
        self.cache = collections.OrderedDict()

        self.clock = PlaybackClock()
        self.last_direction = 1

        import os
        workers = max(4, min(os.cpu_count() or 4, 8))
        self.loader = FrameLoader(self.cache, self.cache_lock, seq_workers=workers)
        self.loader.start()

    def load_sequence(self, folder_path):
        self.sequence = sorted(glob.glob(os.path.join(folder_path, '*.exr')))
        self.current_frame = 0
        if self.sequence:
            self.media = MediaInfo(path=folder_path, type='sequence', frame_count=len(self.sequence), size=(0,0), fps=24.0)
            self._extract_sequence_metadata()

    def _extract_sequence_metadata(self):
        """Extract resolution and metadata from the first frame of a sequence."""
        if not self.sequence or not self.loader._oiio_loaded:
            return
        
        try:
            import OpenImageIO as oiio
            first_frame = self.sequence[0]
            inp = oiio.ImageInput.open(first_frame)
            if inp:
                spec = inp.spec()
                self.media.size = (spec.width, spec.height)
                self.media.format = inp.format_name()
                
                # Pre-calculate frame memory size (RGB float32)
                self._frame_mem_bytes = spec.width * spec.height * 3 * 4
                self._recalc_capacity_from_gb()
                
                # Extract compression (codec)
                compression = spec.get_string_attribute("compression")
                if compression:
                    self.media.codec = compression
                
                # Extract extra metadata
                for i in range(len(spec.extra_attribs)):
                    attr = spec.extra_attribs[i]
                    if attr.type.basetype == oiio.BASETYPE.STRING:
                         self.media.metadata[attr.name] = spec.get_string_attribute(attr.name)
                    elif attr.type.basetype in (oiio.BASETYPE.INT, oiio.BASETYPE.FLOAT):
                         self.media.metadata[attr.name] = spec.get_float_attribute(attr.name)
                         
                inp.close()
        except Exception:
            traceback.print_exc()

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
                self._extract_sequence_metadata()
            else:
                import cv2
                self.sequence = [path]
                fc, fps, w, h = 100, 24.0, 1920, 1080

                # Try cv2 for metadata first
                info = {}
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
                if info:
                    self.media.format = info.get('format', '')
                    self.media.codec = info.get('codec', '')
                    # Store long names as well if available
                    if 'format_long' in info: self.media.metadata['format_long'] = info['format_long']
                    if 'codec_long' in info: self.media.metadata['codec_long'] = info['codec_long']
                
                # Pre-compute frame size for GB-based cache capacity
                # Videos are now kept as uint8 to save 4x memory
                self._frame_mem_bytes = w * h * 3 * 1 # uint8 RGB
                self._recalc_capacity_from_gb()

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

        # If cache disabled, load directly (no caching)
        if not self.cache_enabled:
            path = self._get_path(index)
            self.loader.request(path, index, priority=0)
            with self.cache_lock:
                if index in self.cache:
                    return self.cache.pop(index)
            return None

        # Check cache (release lock BEFORE calling prefetch!)
        frame = None
        with self.cache_lock:
            if index in self.cache:
                self.cache.move_to_end(index)
                frame = self.cache[index]

        if frame is not None:
            # Auto-detect frame memory size for GB-based capacity calculation
            if self._frame_mem_bytes == 0:
                self._frame_mem_bytes = frame.nbytes
                self._recalc_capacity_from_gb()
            # Prefetch OUTSIDE the lock to avoid deadlock
            if self.prefetch_enabled:
                self.predictive_prefetch(index, self.last_direction)
            return frame

        # Cache miss
        # In STREAM mode, we limit the cache to a small buffer (e.g. 16 frames)
        # to smooth out I/O without hogging GBs of RAM.
        if self.strategy == PlaybackStrategy.STREAM:
            self.cache_capacity = 16
            self.loader.cache_capacity = 16
            
        path = self._get_path(index)
        self.loader.request(path, index, priority=0)
        
        # Adaptive prefetch based on strategy
        if self.prefetch_enabled:
             self.predictive_prefetch(index, self.last_direction)
        
        # Immediate prune to enforce strategy-specific limits
        self._prune_cache(current_index=index)
            
        return None

    def _get_path(self, index: int) -> str:
        if self.media.type == 'video':
            return self.sequence[0]
        return self.sequence[index]

    def predictive_prefetch(self, current_index: int, direction: int):
        if not self.prefetch_enabled or not self.media:
            return
        
        # STREAM mode: Absolutely no prefetching
        if self.strategy == PlaybackStrategy.STREAM:
            return

        # PROGRESSIVE mode for sequences: Sequential only (no random jumps)
        # (For videos, we already handle this in the worker burst)
        is_video = self.media.type == 'video'
        
        if self.strategy == PlaybackStrategy.PROGRESSIVE:
            if is_video:
                return # Worker handles it
            # For sequences in progressive, just load next 12 frames
            for f in range(current_index + 1, current_index + 13):
                if 0 <= f < self.media.frame_count:
                    with self.cache_lock:
                        if f not in self.cache:
                            self.loader.request(self._get_path(f), f, priority=2)
            return

        # PERFORMANCE / READ_BEHIND mode
        if is_video:
            # For video, if READ_BEHIND is on, we might want to prefetch backwards too
            if self.strategy == PlaybackStrategy.READ_BEHIND:
                for f in range(current_index - self.read_behind_count, current_index):
                    if 0 <= f < self.media.frame_count:
                        with self.cache_lock:
                            if f not in self.cache:
                                self.loader.request(self._get_path(f), f, priority=3)
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
        
        # For videos, cap burst to avoid flooding single worker
        if self.media.type == 'video':
            count = min(count, 24, self.cache_capacity // 2)

        for f in range(start_index, min(start_index + count, cnt)):
            with self.cache_lock:
                if f not in self.cache:
                    self.loader.request(self._get_path(f), f, priority=0)

    def _prune_cache(self, current_index: int = -1):
        if not self.media: return
        with self.cache_lock:
            if len(self.cache) <= self.cache_capacity:
                return

            # Smart Pruning:
            # We want to keep frames near the 'current_index' (playhead).
            # If current_index is -1, we just do LRU.
            if current_index < 0:
                while len(self.cache) > self.cache_capacity:
                    self.cache.popitem(last=False)
                return

            # O(1) Check oldest keys first to avoid N log N sorting overhead
            back_limit = 5
            if self.strategy == PlaybackStrategy.READ_BEHIND:
                back_limit = self.read_behind_count
            elif self.strategy == PlaybackStrategy.PERFORMANCE:
                back_limit = self.cache_capacity // 3
                
            keys_to_remove = []
            for idx in self.cache:
                if len(self.cache) - len(keys_to_remove) <= self.cache_capacity:
                    break
                dist = idx - current_index
                if dist < -back_limit or dist > self.cache_capacity:
                    keys_to_remove.append(idx)
                    
            for idx in keys_to_remove:
                del self.cache[idx]
                
            while len(self.cache) > self.cache_capacity:
                self.cache.popitem(last=False)

    def _recalc_capacity_from_gb(self):
        """Recalculate frame capacity from GB budget and per-frame memory size."""
        if self._frame_mem_bytes > 0:
            max_frames = int((self.cache_gb * 1024 * 1024 * 1024) / self._frame_mem_bytes)
            self.cache_capacity = max(10, max_frames)
            self.loader.cache_capacity = self.cache_capacity

    def set_strategy(self, strategy: PlaybackStrategy):
        self.strategy = strategy
        self.loader.strategy = strategy
        
        if strategy == PlaybackStrategy.STREAM:
            # Stream mode uses tiny cache
            self.set_cache_capacity(5)
        else:
            # Restore capacity from GB
            self._recalc_capacity_from_gb()
        
        # Clear cache to ensure new logic applies
        # (Optional, but cleaner for mode switching)
        with self.cache_lock:
            self.cache.clear()

    def set_economy_mode(self, enabled: bool):
        # Map old economy_mode to STREAM vs PERFORMANCE
        self.set_strategy(PlaybackStrategy.STREAM if enabled else PlaybackStrategy.PERFORMANCE)

    def set_cache_capacity(self, capacity: int):
        self.cache_capacity = capacity
        self.loader.cache_capacity = capacity
        self._prune_cache()

    def set_cache_gb(self, gb: float):
        """Set cache budget in gigabytes. Auto-calculates frame capacity."""
        self.cache_gb = max(0.5, gb)
        self._recalc_capacity_from_gb()
        self._prune_cache()

    def get_cached_indices(self) -> set:
        """Return set of cached frame indices for timeline display."""
        with self.cache_lock:
            return set(self.cache.keys())

    def cache_stats(self):
        with self.cache_lock:
            count = len(self.cache)
            mem_bytes = count * self._frame_mem_bytes if self._frame_mem_bytes > 0 else 0
        cap = self.cache_capacity
        pct = (count / cap * 100.0) if cap > 0 else 0.0
        mem_mb = mem_bytes / (1024 * 1024)
        return count, cap, pct, mem_mb
