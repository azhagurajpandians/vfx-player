import os
import re
import sys
import time
import datetime
import subprocess
import traceback
import numpy as np
import cv2

from PyQt6 import QtWidgets, QtCore, QtGui
from core.player_core import _find_ffmpeg, _find_ffprobe

# OpenCV Font Mapping
FONT_MAP = {
    'simplex': cv2.FONT_HERSHEY_SIMPLEX,
    'plain': cv2.FONT_HERSHEY_PLAIN,
    'duplex': cv2.FONT_HERSHEY_DUPLEX,
    'complex': cv2.FONT_HERSHEY_COMPLEX,
    'triplex': cv2.FONT_HERSHEY_TRIPLEX
}

class ExportWorker(QtCore.QThread):
    """
    Background worker thread to transcode images/video frames to MOV/MP4 using FFmpeg.
    Applies OCIO, color grading adjustments, and overlays burn-in texts frame-by-frame.
    """
    progress = QtCore.pyqtSignal(int, int, float)  # current, total, current_fps
    finished = QtCore.pyqtSignal(str)              # empty on success, error message on failure
    cancelled = QtCore.pyqtSignal()

    def __init__(self, core, output_path, start_frame, end_frame, format_preset,
                 width, height, aspect_mode, fps, apply_ocio, apply_grade,
                 burnin_options, include_audio, exposure=0.0, gamma=1.0,
                 color_snapshot=None, slate_options=None):
        super().__init__()
        self.core = core
        self.output_path = output_path
        self.start_frame = start_frame
        self.end_frame = end_frame
        self.format_preset = format_preset  # 'mp4' (H.264) or 'prores_hq', etc.
        self.width = width
        self.height = height
        self.aspect_mode = aspect_mode      # 'fill', 'fit', 'stretch'
        self.fps = fps
        self.apply_ocio = apply_ocio
        self.apply_grade = apply_grade
        self.burnin_options = burnin_options
        self.include_audio = include_audio
        self.exposure = exposure
        self.gamma = gamma
        self.slate_options = slate_options or {}
        self.is_cancelled = False

        from core.color_pipeline import ColorPipeline, ColorState
        if color_snapshot:
            self.color_pipeline = ColorPipeline.from_snapshot(color_snapshot)
        elif hasattr(core, 'color_pipeline') and core.color_pipeline:
            self.color_pipeline = ColorPipeline.from_snapshot(core.color_pipeline.snapshot())
        else:
            self.color_pipeline = ColorPipeline(ColorState(exposure=exposure, gamma=gamma))

    def cancel(self):
        self.is_cancelled = True

    def run(self):
        ffmpeg_path = _find_ffmpeg()
        if not ffmpeg_path:
            self.finished.emit("FFmpeg executable not found. Cannot export.")
            return

        total_frames = self.end_frame - self.start_frame + 1
        if total_frames <= 0:
            self.finished.emit("Invalid frame range specified.")
            return

        # Handle final resolution (no resize processing)
        target_w = self.width
        target_h = self.height

        # Prepare FFmpeg input command (stdin pipe)
        cmd = [
            ffmpeg_path,
            '-y',
            '-f', 'rawvideo',
            '-vcodec', 'rawvideo',
            '-pix_fmt', 'rgb24',
            '-s', f"{target_w}x{target_h}",
            '-r', f"{self.fps:.3f}",
            '-i', '-',  # input 0 is stdin
        ]

        # Extract/trim audio if input is a video file containing audio
        has_audio = False
        if self.include_audio and self.core.media.type == 'video' and os.path.exists(self.core.media.path):
            try:
                # Seek start time and duration for audio
                start_time_sec = self.start_frame / self.core.media.fps
                duration_sec = total_frames / self.core.media.fps
                
                # Check if file has audio streams via ffprobe
                ffprobe_path = _find_ffprobe()
                if ffprobe_path:
                    probe_cmd = [
                        ffprobe_path, '-v', 'error',
                        '-select_streams', 'a',
                        '-show_entries', 'stream=index',
                        '-of', 'csv=p=0',
                        self.core.media.path
                    ]
                    res = subprocess.run(probe_cmd, capture_output=True, text=True, timeout=5,
                                         creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
                    if res.returncode == 0 and res.stdout.strip():
                        # Has audio streams, append input 1 with seeking
                        cmd.extend([
                            '-ss', f"{start_time_sec:.6f}",
                            '-t', f"{duration_sec:.6f}",
                            '-i', self.core.media.path
                        ])
                        has_audio = True
            except Exception as e:
                print(f"Error checking audio: {e}")

        # Set export format video codecs and parameters
        if self.format_preset in ('mp4', 'mov_h264'):
            cmd.extend([
                '-c:v', 'libx264',
                '-pix_fmt', 'yuv420p',
                '-crf', '18',
                '-preset', 'medium'
            ])
        elif self.format_preset in ('mp4_h265', 'mov_h265'):
            cmd.extend([
                '-c:v', 'libx265',
                '-pix_fmt', 'yuv420p',
                '-crf', '23',
                '-preset', 'medium',
                '-tag:v', 'hvc1'
            ])
        elif self.format_preset == 'mp4_h265_hq':
            cmd.extend([
                '-c:v', 'libx265',
                '-pix_fmt', 'yuv420p10le',
                '-crf', '20',
                '-preset', 'medium',
                '-tag:v', 'hvc1'
            ])
        elif self.format_preset == 'prores_hq':
            cmd.extend([
                '-c:v', 'prores_ks',
                '-profile:v', '3', # HQ
                '-vendor', 'ap10',
                '-pix_fmt', 'yuv422p10le'
            ])
        elif self.format_preset == 'prores_std':
            cmd.extend([
                '-c:v', 'prores_ks',
                '-profile:v', '2', # Standard
                '-vendor', 'ap10',
                '-pix_fmt', 'yuv422p10le'
            ])
        elif self.format_preset == 'prores_4444':
            cmd.extend([
                '-c:v', 'prores_ks',
                '-profile:v', '4', # 4444
                '-vendor', 'ap10',
                '-pix_fmt', 'yuva4444p10le'
            ])
        elif self.format_preset == 'dnxhr_hq':
            cmd.extend([
                '-c:v', 'dnxhd',
                '-profile:v', 'dnxhr_hq',
                '-pix_fmt', 'yuv422p10le'
            ])

        # Map audio from input 1 if present
        if has_audio:
            cmd.extend([
                '-map', '0:v:0',
                '-map', '1:a:0?',
                '-c:a', 'aac',
                '-shortest'
            ])
        else:
            cmd.extend([
                '-map', '0:v:0'
            ])

        cmd.append(self.output_path)

        # Open FFmpeg process. Redirect stderr to log file to prevent OS pipe deadlocks.
        log_path = os.path.join(os.path.dirname(self.output_path), "ffmpeg_export.log")
        log_file = None
        cap = None
        try:
            log_file = open(log_path, 'w', encoding='utf-8')
        except Exception as e:
            print(f"Failed to create ffmpeg log file: {e}")
            log_file = subprocess.DEVNULL

        try:
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=log_file,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
            )

            # Setup video source
            if self.core.media.type == 'video':
                cap = cv2.VideoCapture(self.core.media.path)
                cap.set(cv2.CAP_PROP_POS_FRAMES, self.start_frame)

            # Setup OCIO in worker thread if checked
            ocio_config = None
            if self.apply_ocio:
                try:
                    import PyOpenColorIO as OCIO
                    cfg_path = self.core.loader.ocio_config_path or os.environ.get('OCIO')
                    if cfg_path and os.path.exists(cfg_path):
                        ocio_config = OCIO.Config.CreateFromFile(cfg_path)
                except Exception as e:
                    print(f"Failed to load OCIO configuration in Export: {e}")

            start_time = time.time()

            # Prepend delivery slate frame(s) if enabled
            if self.slate_options and self.slate_options.get('enabled', False):
                try:
                    from core.slate_builder import SlateBuilder, SlateConfig
                    slate_cfg = SlateConfig.from_dict(self.slate_options.get('config', {}))
                    thumb = self.core.get_frame(self.start_frame) if self.core else None
                    slate_rgb = SlateBuilder.create_slate(target_w, target_h, slate_cfg, thumbnail=thumb)
                    duration_frames = max(1, int(self.slate_options.get('duration_frames', 1)))
                    for _ in range(duration_frames):
                        proc.stdin.write(slate_rgb.tobytes())
                except Exception as e:
                    print(f"Error generating delivery slate: {e}")

            # Transcode frame-by-frame loop
            for idx, frame_idx in enumerate(range(self.start_frame, self.end_frame + 1)):
                if self.is_cancelled:
                    break

                # 1. Load image frame
                frame_rgb = None
                if self.core.media.type == 'sequence':
                    path = self.core.sequence[frame_idx]
                    frame_rgb = self._load_exr(path)
                else:
                    if cap and cap.isOpened():
                        ret, bgr = cap.read()
                        if ret:
                            frame_rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
                
                # Check for load failure -> fallback black frame
                if frame_rgb is None:
                    frame_rgb = np.zeros((self.height, self.width, 3), dtype=np.uint8)

                # 2. Process Color spaces and grading adjustments
                processed = self._process_color(frame_rgb, ocio_config)

                # 3. Apply Aspect Ratio scaling (Crop / Letterbox / Stretch) to get target resolution
                processed = self._apply_aspect_ratio(processed, target_w, target_h, self.aspect_mode)

                # 4. Draw overlays / Burn-in text and Logo
                self._draw_burnins(processed, frame_idx)

                # 5. Write to FFmpeg stdin
                try:
                    proc.stdin.write(processed.tobytes())
                except Exception as e:
                    print(f"Pipe write failed at frame {frame_idx}: {e}")
                    raise RuntimeError("FFmpeg closed its input pipe early.")

                # Emit progress update
                elapsed = time.time() - start_time
                fps_curr = (idx + 1) / elapsed if elapsed > 0 else 0.0
                self.progress.emit(idx + 1, total_frames, fps_curr)

            # Cleanup video file reader
            if cap:
                cap.release()
                cap = None

            # Gracefully close stdin and communicate
            if proc.stdin:
                try: proc.stdin.close()
                except: pass
            
            proc.wait()

            if log_file and log_file != subprocess.DEVNULL:
                try: log_file.close()
                except: pass
            
            if self.is_cancelled:
                try: os.remove(self.output_path)
                except: pass
                try: os.remove(log_path)
                except: pass
                self.cancelled.emit()
            elif proc.returncode == 0:
                try: os.remove(log_path)
                except: pass
                self.finished.emit("")
            else:
                err_msg = "Unknown FFmpeg transcode error."
                if os.path.exists(log_path):
                    try:
                        with open(log_path, 'r', encoding='utf-8') as lf:
                            err_msg = lf.read()
                    except: pass
                self.finished.emit(f"FFmpeg failed with exit code {proc.returncode}.\nErrors:\n{err_msg}")

        except Exception as e:
            traceback.print_exc()
            if cap:
                cap.release()
            if log_file and log_file != subprocess.DEVNULL:
                try: log_file.close()
                except: pass
            try: os.remove(self.output_path)
            except: pass
            try: os.remove(log_path)
            except: pass
            self.finished.emit(str(e))

    def _load_exr(self, path):
        """Read EXR via OpenImageIO into RGB float32."""
        try:
            import OpenImageIO as oiio
            inp = oiio.ImageInput.open(path)
            if inp:
                spec = inp.spec()
                try:
                    fmt = oiio.TypeFloat
                except AttributeError:
                    fmt = oiio.TypeDesc(oiio.FLOAT)
                raw_data = inp.read_image(format=fmt)
                inp.close()
                if raw_data is not None:
                    n_ch = spec.nchannels
                    if n_ch >= 3:
                        return raw_data[:, :, :3]
                    elif n_ch == 1:
                        return np.repeat(raw_data[:, :, np.newaxis], 3, axis=2)
                    else:
                        return np.repeat(raw_data[:, :, 0:1], 3, axis=2)
        except Exception as e:
            print(f"Error reading {path} during export: {e}")
        return None

    def _process_color(self, img, ocio_config=None):
        """Transform colorspaces (OCIO) and apply authoritative viewer color pipeline."""
        if getattr(self, 'color_pipeline', None) is not None:
            # Synchronize OCIO parameters from loader if not set in pipeline
            if hasattr(self.core, 'loader'):
                if not self.color_pipeline.state.input_cs:
                    self.color_pipeline.state.input_cs = getattr(self.core.loader, 'ocio_input_cs', None)
                if not self.color_pipeline.state.output_cs:
                    self.color_pipeline.state.output_cs = getattr(self.core.loader, 'ocio_output_cs', None)
                if not self.color_pipeline.state.ocio_config_path:
                    self.color_pipeline.state.ocio_config_path = getattr(self.core.loader, 'ocio_config_path', None)

            return self.color_pipeline.process(
                img,
                apply_ocio=self.apply_ocio,
                apply_grade=self.apply_grade,
                to_uint8=True
            )

        # Fallback if no color_pipeline is attached
        if img.dtype == np.uint8:
            if not self.apply_grade:
                return img
            img_float = img.astype(np.float32) / 255.0
            if self.exposure != 0.0:
                img_float *= pow(2.0, self.exposure)
            if self.gamma != 1.0 and abs(self.gamma) > 0.01:
                np.clip(img_float, 0.0, None, out=img_float)
                np.power(img_float, 1.0 / self.gamma, out=img_float)
            return np.clip(img_float * 255.0, 0, 255).astype(np.uint8)

        if ocio_config and self.apply_ocio:
            try:
                import OpenImageIO as oiio
                h, w, c = img.shape
                if not img.flags['C_CONTIGUOUS']:
                    img = np.ascontiguousarray(img)
                spec = oiio.ImageSpec(w, h, c, oiio.TypeFloat)
                buf = oiio.ImageBuf(spec)
                buf.set_pixels(oiio.ROI(), img)
                in_cs = getattr(self.core.loader, 'ocio_input_cs', None)
                out_cs = getattr(self.core.loader, 'ocio_output_cs', None)
                cfg_path = getattr(self.core.loader, 'ocio_config_path', None) or ""
                res_buf = oiio.ImageBufAlgo.colorconvert(buf, in_cs, out_cs, False, cfg_path)
                if not res_buf.has_error:
                    raw = res_buf.get_pixels(oiio.TypeFloat)
                    img = np.array(raw, dtype=np.float32).reshape((h, w, c))
            except Exception as e:
                print(f"OCIO color conversion failed in export: {e}")

        if self.apply_grade:
            if self.exposure != 0.0:
                img *= pow(2.0, self.exposure)
            if self.gamma != 1.0 and abs(self.gamma) > 0.01:
                np.clip(img, 0.0, None, out=img)
                img = np.power(img, 1.0 / self.gamma)

        return np.clip(img * 255.0, 0.0, 255.0).astype(np.uint8)

    def _apply_aspect_ratio(self, img, target_w, target_h, mode):
        """Fit, Crop or Stretch source frame to destination size."""
        h, w = img.shape[:2]
        if w == target_w and h == target_h:
            return img

        if mode == 'stretch':
            return cv2.resize(img, (target_w, target_h), interpolation=cv2.INTER_CUBIC)

        aspect_src = w / h
        aspect_dst = target_w / target_h

        if mode == 'fit':  # Letterbox/Pillarbox
            if aspect_src > aspect_dst:
                # Fit width, pad height (letterbox)
                new_w = target_w
                new_h = int(target_w / aspect_src)
                resized = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_CUBIC)
                pad_y = (target_h - new_h) // 2
                padded = np.zeros((target_h, target_w, 3), dtype=np.uint8)
                padded[pad_y:pad_y + new_h, :] = resized
                return padded
            else:
                # Fit height, pad width (pillarbox)
                new_h = target_h
                new_w = int(target_h * aspect_src)
                resized = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_CUBIC)
                pad_x = (target_w - new_w) // 2
                padded = np.zeros((target_h, target_w, 3), dtype=np.uint8)
                padded[:, pad_x:pad_x + new_w] = resized
                return padded

        else:  # 'fill' (Crop)
            if aspect_src > aspect_dst:
                # Fit height, crop width
                new_h = target_h
                new_w = int(target_h * aspect_src)
                resized = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_CUBIC)
                crop_x = (new_w - target_w) // 2
                return resized[:, crop_x:crop_x + target_w]
            else:
                # Fit width, crop height
                new_w = target_w
                new_h = int(target_w / aspect_src)
                resized = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_CUBIC)
                crop_y = (new_h - target_h) // 2
                return resized[crop_y:crop_y + target_h, :]

    def _draw_burnins(self, img_uint8, frame_idx):
        """Bakes overlay burn-ins and logo watermarks onto the frame."""
        if not self.burnin_options.get('enabled', False):
            return

        h, w = img_uint8.shape[:2]
        
        # Scale fonts proportional to target height (standard size: 1.0 for 1080p)
        font_scale = (h / 1080.0) * self.burnin_options.get('font_scale', 0.6)
        font_thickness = max(1, int(self.burnin_options.get('font_thickness', 1)))
        bg_alpha = self.burnin_options.get('bg_alpha', 0.4)

        # Get Selected Font from combobox selection
        font_name = self.burnin_options.get('font_name', 'simplex')
        font = FONT_MAP.get(font_name, cv2.FONT_HERSHEY_SIMPLEX)

        # VFX Reference-matched fixed positions:
        # Top-Left: Studio Name
        # Top-Center: Shot Name
        # Top-Right: Task Name
        # Bottom-Left: Date (YYYY-MM-DD)
        # Bottom-Center: Project Code
        # Bottom-Right: Start Frame - Current Frame - End Frame
        margin = int(24 * (h / 1080.0))
        margin = max(10, margin)

        # Compute frame numbers and timecode
        user_start_frame = self.burnin_options.get('start_frame_val', 0)
        curr_frame_val = user_start_frame + (frame_idx - self.start_frame)
        total_frames = self.end_frame - self.start_frame + 1
        user_end_frame = user_start_frame + total_frames - 1

        file_frame_digit = curr_frame_val
        filename = ""
        if self.core.media:
            if self.core.media.type == 'sequence' and self.core.sequence:
                path = self.core.sequence[frame_idx]
                filename = os.path.basename(path)
                match = re.findall(r'\d+', os.path.splitext(filename)[0])
                if match:
                    file_frame_digit = int(match[-1])
                    seq_start_val = file_frame_digit - (frame_idx - self.start_frame)
                    seq_end_val = seq_start_val + total_frames - 1
                    frame_str = f"{seq_start_val} - {file_frame_digit} - {seq_end_val}"
                else:
                    frame_str = f"{user_start_frame} - {curr_frame_val} - {user_end_frame}"
            else:
                filename = os.path.basename(self.core.media.path)
                frame_str = f"{user_start_frame} - {curr_frame_val} - {user_end_frame}"
        else:
            frame_str = f"{user_start_frame} - {curr_frame_val} - {user_end_frame}"

        from core.timeline_service import TimelineService, frame_to_timecode
        fps_val = self.fps or 24.0
        timecode_str = frame_to_timecode(file_frame_digit, fps_val)

        studio = self.burnin_options.get('studio', '').strip()
        shot = self.burnin_options.get('shot', '').strip()
        task = self.burnin_options.get('task', '').strip()
        proj_code = self.burnin_options.get('proj_code', '').strip()
        version_str = self.burnin_options.get('version', 'v001').strip()
        artist_str = self.burnin_options.get('artist', '').strip()
        colorspace_str = self.burnin_options.get('colorspace', 'ACEScg').strip()
        preset = self.burnin_options.get('preset', 'vfx_ref')
        date_str = datetime.date.today().strftime('%Y-%m-%d')

        if preset == 'netflix':
            # Netflix VFX Standard:
            # Top-Left: Vendor / Studio
            # Top-Center: Show Name
            # Top-Right: Date (YYYY-MM-DD)
            # Bottom-Left: Version Name
            # Bottom-Right: Start Frame - Current Frame - End Frame
            vendor_txt = studio or "Template Team"
            show_txt = self.burnin_options.get('show', '') or proj_code or "Netflix VFX Template Demo Show"
            self._draw_text(img_uint8, vendor_txt, "top_left", font, font_scale, font_thickness, margin, bg_alpha)
            if show_txt:
                self._draw_text(img_uint8, show_txt, "top_center", font, font_scale, font_thickness, margin, bg_alpha)
            self._draw_text(img_uint8, date_str, "top_right", font, font_scale, font_thickness, margin, bg_alpha)
            v_name = self.burnin_options.get('version_name', '') or (f"{shot}_{version_str}" if (shot and version_str) else (shot or version_str))
            if v_name:
                self._draw_text(img_uint8, v_name, "bottom_left", font, font_scale, font_thickness, margin, bg_alpha)
            self._draw_text(img_uint8, frame_str, "bottom_right", font, font_scale, font_thickness, margin, bg_alpha)

        elif preset == 'client_review':
            # Client Review: Shot, Version, Timecode, Frame
            if shot:
                self._draw_text(img_uint8, shot, "top_left", font, font_scale, font_thickness, margin, bg_alpha)
            if version_str:
                self._draw_text(img_uint8, version_str, "top_right", font, font_scale, font_thickness, margin, bg_alpha)
            self._draw_text(img_uint8, f"TC {timecode_str}", "bottom_left", font, font_scale, font_thickness, margin, bg_alpha)
            self._draw_text(img_uint8, f"FR {file_frame_digit}", "bottom_right", font, font_scale, font_thickness, margin, bg_alpha)

        elif preset == 'internal_vfx':
            # Internal VFX: Shot | Version, Artist/Task, Colorspace, TC, Frame
            top_l = f"{shot} | {version_str}" if version_str else shot
            if top_l:
                self._draw_text(img_uint8, top_l, "top_left", font, font_scale, font_thickness, margin, bg_alpha)
            task_artist = f"{task} ({artist_str})" if (task and artist_str) else (task or artist_str)
            if task_artist:
                self._draw_text(img_uint8, task_artist, "top_center", font, font_scale, font_thickness, margin, bg_alpha)
            if colorspace_str:
                self._draw_text(img_uint8, colorspace_str, "top_right", font, font_scale, font_thickness, margin, bg_alpha)
            self._draw_text(img_uint8, f"TC {timecode_str}", "bottom_left", font, font_scale, font_thickness, margin, bg_alpha)
            self._draw_text(img_uint8, frame_str, "bottom_right", font, font_scale, font_thickness, margin, bg_alpha)

        elif preset == 'dailies':
            # Dailies: Shot & Version, Task, Filename, Timecode, Frame
            top_l = f"{shot} {version_str}" if version_str else shot
            if top_l:
                self._draw_text(img_uint8, top_l, "top_left", font, font_scale, font_thickness, margin, bg_alpha)
            if task:
                self._draw_text(img_uint8, task, "top_right", font, font_scale, font_thickness, margin, bg_alpha)
            if filename:
                self._draw_text(img_uint8, filename, "bottom_left", font, font_scale, font_thickness, margin, bg_alpha)
            self._draw_text(img_uint8, timecode_str, "bottom_center", font, font_scale, font_thickness, margin, bg_alpha)
            self._draw_text(img_uint8, frame_str, "bottom_right", font, font_scale, font_thickness, margin, bg_alpha)

        else:
            # Full VFX Reference / Custom
            if studio:
                self._draw_text(img_uint8, studio, "top_left", font, font_scale, font_thickness, margin, bg_alpha)
            if shot:
                self._draw_text(img_uint8, shot, "top_center", font, font_scale, font_thickness, margin, bg_alpha)
            if task:
                self._draw_text(img_uint8, task, "top_right", font, font_scale, font_thickness, margin, bg_alpha)

            show_tc = self.burnin_options.get('show_timecode', True)
            b_left = f"{date_str}  TC:{timecode_str}" if show_tc else date_str
            self._draw_text(img_uint8, b_left, "bottom_left", font, font_scale, font_thickness, margin, bg_alpha)

            if proj_code:
                self._draw_text(img_uint8, proj_code, "bottom_center", font, font_scale, font_thickness, margin, bg_alpha)
            self._draw_text(img_uint8, frame_str, "bottom_right", font, font_scale, font_thickness, margin, bg_alpha)

        # 7. Logo Watermark overlay (centered on the screen)
        logo_path = self.burnin_options.get('logo_path', '').strip()
        logo_opacity = self.burnin_options.get('logo_opacity', 0.5)
        if logo_path and os.path.exists(logo_path):
            self._overlay_logo(img_uint8, logo_path, logo_opacity)

    def _draw_text(self, img, text, position, font, font_scale, font_thickness, margin, bg_alpha):
        """Draws standard VFX text overlay with black backdrop box (no outline, white text)."""
        text_size, baseline = cv2.getTextSize(text, font, font_scale, font_thickness)
        tw, th = text_size[0], text_size[1]
        h, w = img.shape[:2]

        if position.startswith('top'):
            y = margin + th
        else:
            y = h - margin - baseline

        if position.endswith('left'):
            x = margin
        elif position.endswith('center'):
            x = (w - tw) // 2
        else:
            x = w - margin - tw

        # Safety clamps
        x = max(0, min(x, w - tw))
        y = max(th, min(y, h - baseline))

        # Backing box coordinates
        bx1 = max(0, x - 6)
        by1 = max(0, y - th - 6)
        bx2 = min(w, x + tw + 6)
        by2 = min(h, y + baseline + 6)

        # Backing box
        if bg_alpha > 0.01:
            overlay = img[by1:by2, bx1:bx2].copy()
            cv2.rectangle(overlay, (0, 0), (bx2 - bx1, by2 - by1), (0, 0, 0), -1)
            cv2.addWeighted(overlay, bg_alpha, img[by1:by2, bx1:bx2], 1.0 - bg_alpha, 0, dst=img[by1:by2, bx1:bx2])

        # Draw single layer white text (no black outline for clean modern VFX look)
        cv2.putText(img, text, (x, y), font, font_scale, (255, 255, 255), font_thickness, cv2.LINE_AA)

    def _overlay_logo(self, frame, logo_path, opacity):
        """Overlay transparent watermark logo in the center of the frame."""
        try:
            logo = cv2.imread(logo_path, cv2.IMREAD_UNCHANGED)
            if logo is None:
                return
                
            fh, fw = frame.shape[:2]
            lh, lw = logo.shape[:2]
            
            # Scale logo so it is max 40% of target frame height/width
            max_h = int(fh * 0.40)
            max_w = int(fw * 0.40)
            if lh > max_h or lw > max_w:
                scale = min(max_h / lh, max_w / lw)
                logo = cv2.resize(logo, (int(lw * scale), int(lh * scale)), interpolation=cv2.INTER_AREA)
                lh, lw = logo.shape[:2]
                
            # Place centered on screen
            x = (fw - lw) // 2
            y = (fh - lh) // 2
            
            if x < 0 or y < 0:
                return
                
            roi = frame[y:y+lh, x:x+lw]
            if logo.shape[2] == 4:
                # Alpha blend
                logo_rgb = logo[:, :, :3]
                logo_alpha = (logo[:, :, 3].astype(float) / 255.0) * opacity
                for c in range(3):
                    roi[:, :, c] = (logo_alpha * logo_rgb[:, :, c] + (1.0 - logo_alpha) * roi[:, :, c]).astype(np.uint8)
            else:
                # RGB blend
                cv2.addWeighted(logo, opacity, roi, 1.0 - opacity, 0, dst=roi)
        except Exception as e:
            print(f"Error drawing logo: {e}")

    def _frames_to_tc(self, frames, fps):
        if fps <= 0:
            return "00:00:00:00"
        total_seconds = int(frames / fps)
        ff = int(frames % fps)
        hh = total_seconds // 3600
        mm = (total_seconds % 3600) // 60
        ss = total_seconds % 60
        return f"{hh:02d}:{mm:02d}:{ss:02d}:{ff:02d}"

    def _tc_to_frames(self, tc_str, fps):
        try:
            parts = tc_str.split(':')
            if len(parts) == 4:
                hh, mm, ss, ff = map(int, parts)
                return int((hh * 3600 + mm * 60 + ss) * fps + ff)
        except:
            pass
        return 0


class SlatePreviewDialog(QtWidgets.QDialog):
    """Modal preview window for generated delivery slate frames."""
    def __init__(self, parent, slate_rgb: np.ndarray):
        super().__init__(parent)
        self.setWindowTitle("Delivery Slate Preview")
        self.resize(980, 580)
        self.setStyleSheet("background-color: #16181c; color: #eee; font-family: 'Segoe UI', sans-serif;")
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(15, 15, 15, 15)
        lay.setSpacing(10)

        lbl = QtWidgets.QLabel()
        lbl.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet("background-color: #0d0e11; border: 1px solid #333; border-radius: 4px;")
        
        h, w, ch = slate_rgb.shape
        bytes_per_line = ch * w
        qimg = QtGui.QImage(slate_rgb.data, w, h, bytes_per_line, QtGui.QImage.Format.Format_RGB888)
        pix = QtGui.QPixmap.fromImage(qimg).scaled(940, 500, QtCore.Qt.AspectRatioMode.KeepAspectRatio, QtCore.Qt.TransformationMode.SmoothTransformation)
        lbl.setPixmap(pix)
        lay.addWidget(lbl)

        btn_box = QtWidgets.QHBoxLayout()
        btn_box.addStretch()
        close_btn = QtWidgets.QPushButton("Close Preview")
        close_btn.setStyleSheet("background-color: #0078d4; color: white; padding: 6px 16px; border-radius: 4px; font-weight: 500;")
        close_btn.clicked.connect(self.accept)
        btn_box.addWidget(close_btn)
        btn_box.addStretch()
        lay.addLayout(btn_box)


class ExportDialog(QtWidgets.QDialog):
    """
    Export Settings window matching the clean layout with simplified fixed overlays.
    """
    def __init__(self, parent, core):
        super().__init__(parent)
        self.core = core
        self.setWindowTitle("Export / Transcode Video")
        self.resize(850, 560)
        self.setMinimumSize(700, 500)
        
        # Stylesheet matching player dark theme and reference clean lines
        self.setStyleSheet("""
            QDialog {
                background-color: #121212;
                color: #e0e0e0;
                font-family: 'Segoe UI', sans-serif;
            }
            QGroupBox {
                border: 1px solid #333;
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 12px;
                font-weight: bold;
                color: #aaa;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 4px;
            }
            QLabel {
                color: #aaa;
                font-size: 11px;
            }
            QLineEdit, QComboBox, QSpinBox {
                background-color: #222;
                border: 1px solid #333;
                border-radius: 4px;
                padding: 4px;
                color: #ddd;
            }
            QLineEdit:focus, QComboBox:focus, QSpinBox:focus {
                border: 1px solid #0078d4;
            }
            QCheckBox {
                color: #ccc;
                spacing: 8px;
            }
            QSlider::groove:horizontal {
                border: 1px solid #444;
                height: 4px;
                background: #222;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #888;
                border: 1px solid #666;
                width: 12px;
                height: 16px;
                margin: -6px 0;
                border-radius: 2px;
            }
            QPushButton {
                background-color: #2a2a2a;
                border: none;
                border-radius: 4px;
                padding: 6px 12px;
                color: #e0e0e0;
            }
            QPushButton:hover {
                background-color: #3a3a3a;
            }
            QPushButton:pressed {
                background-color: #0078d4;
            }
            QProgressBar {
                background-color: #1a1a1a;
                border: 1px solid #333;
                border-radius: 4px;
                text-align: center;
                color: #fff;
                font-weight: bold;
            }
            QProgressBar::chunk {
                background-color: #0078d4;
                border-radius: 2px;
            }
            QTabWidget::pane {
                border: 1px solid #333;
                background: #18191c;
                border-radius: 6px;
                padding: 4px;
            }
            QTabBar::tab {
                background: #25262a;
                color: #bbb;
                padding: 7px 16px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                margin-right: 3px;
                font-weight: 500;
            }
            QTabBar::tab:selected {
                background: #0078d4;
                color: white;
                font-weight: bold;
            }
        """)

        # Main Vertical Layout
        self.layout = QtWidgets.QVBoxLayout(self)
        self.layout.setContentsMargins(15, 15, 15, 15)
        self.layout.setSpacing(10)

        # Output Path Select
        path_layout = QtWidgets.QHBoxLayout()
        path_layout.addWidget(QtWidgets.QLabel("Output Path:"))
        self.path_edit = QtWidgets.QLineEdit()
        
        # Default destination path
        default_out = ""
        if self.core.media:
            src_dir = os.path.dirname(self.core.media.path) if self.core.media.type == 'video' else self.core.media.path
            default_out = os.path.join(src_dir, "export_output.mp4")
        self.path_edit.setText(default_out)
        path_layout.addWidget(self.path_edit)

        self.browse_btn = QtWidgets.QPushButton("Browse...")
        self.browse_btn.clicked.connect(self._browse_output)
        path_layout.addWidget(self.browse_btn)
        self.layout.addLayout(path_layout)

        # 1. Format & Resolution Options Group Box
        fr_group = QtWidgets.QGroupBox("Format Resolution Options")
        fr_grid = QtWidgets.QGridLayout(fr_group)
        fr_grid.setSpacing(6)

        # Col 0, 1: Format
        fr_grid.addWidget(QtWidgets.QLabel("Format Preset:"), 0, 0)
        self.format_combo = QtWidgets.QComboBox()
        self.format_combo.addItem("MP4 (H.264 / AAC)", "mp4")
        self.format_combo.addItem("MP4 (H.265 / HEVC)", "mp4_h265")
        self.format_combo.addItem("MP4 (H.265 10-bit HQ)", "mp4_h265_hq")
        self.format_combo.addItem("MOV (ProRes 422 HQ)", "prores_hq")
        self.format_combo.addItem("MOV (ProRes 422 Standard)", "prores_std")
        self.format_combo.addItem("MOV (ProRes 4444)", "prores_4444")
        self.format_combo.addItem("MOV (DNxHR HQ)", "dnxhr_hq")
        self.format_combo.addItem("MOV (H.264)", "mov_h264")
        self.format_combo.addItem("MOV (H.265 / HEVC)", "mov_h265")
        self.format_combo.currentIndexChanged.connect(self._format_changed)
        fr_grid.addWidget(self.format_combo, 0, 1)

        # Col 2, 3: Frame Range
        fr_grid.addWidget(QtWidgets.QLabel("Frame Range:"), 0, 2)
        self.range_combo = QtWidgets.QComboBox()
        self.range_combo.addItem("Entire Sequence", "full")
        r_in = getattr(parent, 'range_in', 0)
        total_fc = self.core.frame_count() if (self.core and self.core.media) else 0
        r_out = getattr(parent, 'range_out', max(0, total_fc - 1))
        has_in_out = (r_in > 0 or (total_fc > 0 and r_out < (total_fc - 1)))
        if has_in_out:
            self.range_combo.addItem(f"In/Out Range ({r_in} - {r_out})", "in_out")
        self.range_combo.addItem("Current Frame", "current")
        self.range_combo.addItem("Custom Range", "custom")
        self.range_combo.currentIndexChanged.connect(self._range_changed)
        fr_grid.addWidget(self.range_combo, 0, 3)

        # Col 0, 1: Resolution
        fr_grid.addWidget(QtWidgets.QLabel("Resolution:"), 1, 0)
        self.res_combo = QtWidgets.QComboBox()
        self.res_combo.addItem("Match Source", "source")
        self.res_combo.addItem("3840 x 2160 (4K UHD)", "4k")
        self.res_combo.addItem("1920 x 1080 (1080p)", "1080p")
        self.res_combo.addItem("1280 x 720 (720p)", "720p")
        fr_grid.addWidget(self.res_combo, 1, 1)

        # Col 2, 3: Frame Rate
        fr_grid.addWidget(QtWidgets.QLabel("Frame Rate (FPS):"), 1, 2)
        self.fps_combo = QtWidgets.QComboBox()
        self.fps_combo.addItem("Match Source", "source")
        for f in [23.976, 24.0, 25.0, 29.97, 30.0, 48.0, 50.0, 60.0]:
            self.fps_combo.addItem(f"{f} FPS", f)
        fr_grid.addWidget(self.fps_combo, 1, 3)

        # Col 0, 1: Start Frame
        fr_grid.addWidget(QtWidgets.QLabel("Start Frame:"), 2, 0)
        self.start_spin = QtWidgets.QSpinBox()
        self.start_spin.setRange(0, 999999)
        fr_grid.addWidget(self.start_spin, 2, 1)

        # Col 2, 3: End Frame
        fr_grid.addWidget(QtWidgets.QLabel("End Frame:"), 2, 2)
        self.end_spin = QtWidgets.QSpinBox()
        self.end_spin.setRange(0, 999999)
        fr_grid.addWidget(self.end_spin, 2, 3)

        # Defaults range
        if self.core.media:
            if has_in_out:
                self.start_spin.setValue(r_in)
                self.end_spin.setValue(r_out)
                idx_io = self.range_combo.findData("in_out")
                if idx_io >= 0:
                    self.range_combo.setCurrentIndex(idx_io)
            else:
                self.start_spin.setValue(0)
                self.end_spin.setValue(self.core.frame_count() - 1)
            self.start_spin.setEnabled(False)
            self.end_spin.setEnabled(False)

        self.layout.addWidget(fr_group)

        # 2. Checkboxes Row
        chk_layout = QtWidgets.QHBoxLayout()
        self.ocio_chk = QtWidgets.QCheckBox("Apply OCIO Color Management")
        self.ocio_chk.setChecked(self.core.loader.ocio_enabled)
        chk_layout.addWidget(self.ocio_chk)

        self.grade_chk = QtWidgets.QCheckBox("Bake Grade (Exposure: +{:.2f}, Gamma: {:.2f})".format(
            getattr(parent, 'exposure', 0.0), getattr(parent, 'gamma', 1.0)
        ))
        self.grade_chk.setChecked(True)
        chk_layout.addWidget(self.grade_chk)

        self.audio_chk = QtWidgets.QCheckBox("Include Audio")
        self.audio_chk.setChecked(True)
        chk_layout.addWidget(self.audio_chk)
        self.layout.addLayout(chk_layout)

        # 3. Overlay Burn-in Options Group Box
        burn_group = QtWidgets.QGroupBox("Overlay Burn-in Options")
        burn_layout = QtWidgets.QVBoxLayout(burn_group)
        burn_layout.setSpacing(10)

        burn_header = QtWidgets.QHBoxLayout()
        self.burn_chk = QtWidgets.QCheckBox("Enable Burn-ins")
        self.burn_chk.setChecked(True)
        self.burn_chk.stateChanged.connect(self._toggle_burn_inputs)
        burn_header.addWidget(self.burn_chk)

        burn_header.addSpacing(20)
        burn_header.addWidget(QtWidgets.QLabel("Preset:"))
        self.preset_combo = QtWidgets.QComboBox()
        self.preset_combo.addItem("Full VFX Reference", "vfx_ref")
        self.preset_combo.addItem("Netflix VFX Standard", "netflix")
        self.preset_combo.addItem("Client Review (Shot / Ver / TC / FR)", "client_review")
        self.preset_combo.addItem("Internal VFX (Shot / Ver / Artist / CS / TC)", "internal_vfx")
        self.preset_combo.addItem("Dailies (Shot / Ver / Task / TC / File)", "dailies")
        self.preset_combo.addItem("Custom", "custom")
        self.preset_combo.currentIndexChanged.connect(self._on_preset_changed)
        burn_header.addWidget(self.preset_combo)

        burn_header.addSpacing(15)
        self.timecode_chk = QtWidgets.QCheckBox("SMPTE Timecode")
        self.timecode_chk.setChecked(True)
        burn_header.addWidget(self.timecode_chk)
        burn_header.addStretch()
        burn_layout.addLayout(burn_header)

        # Form grid for text field entries
        fields_grid = QtWidgets.QGridLayout()
        fields_grid.setSpacing(6)

        fields_grid.addWidget(QtWidgets.QLabel("Studio Name:"), 0, 0)
        self.studio_edit = QtWidgets.QLineEdit("Knack Studios")
        fields_grid.addWidget(self.studio_edit, 0, 1)

        fields_grid.addWidget(QtWidgets.QLabel("Task Name:"), 0, 2)
        self.task_edit = QtWidgets.QLineEdit("Comp")
        fields_grid.addWidget(self.task_edit, 0, 3)

        fields_grid.addWidget(QtWidgets.QLabel("Shot Name:"), 1, 0)
        shot_def = "SHOT_010"
        if self.core.media:
            shot_def = os.path.basename(self.core.media.path)
        self.shot_edit = QtWidgets.QLineEdit(shot_def)
        fields_grid.addWidget(self.shot_edit, 1, 1)

        fields_grid.addWidget(QtWidgets.QLabel("Version:"), 1, 2)
        self.ver_edit = QtWidgets.QLineEdit("v001")
        fields_grid.addWidget(self.ver_edit, 1, 3)

        fields_grid.addWidget(QtWidgets.QLabel("Artist:"), 2, 0)
        self.artist_edit = QtWidgets.QLineEdit("Lead Artist")
        fields_grid.addWidget(self.artist_edit, 2, 1)

        fields_grid.addWidget(QtWidgets.QLabel("Project Code:"), 2, 2)
        self.proj_edit = QtWidgets.QLineEdit("KNK")
        fields_grid.addWidget(self.proj_edit, 2, 3)

        # Logo Watermark selection row
        fields_grid.addWidget(QtWidgets.QLabel("Logo Watermark:"), 3, 0)
        logo_lay = QtWidgets.QHBoxLayout()
        self.logo_path_edit = QtWidgets.QLineEdit()
        self.logo_path_edit.setPlaceholderText("Select logo image to bake in center...")
        self.logo_browse = QtWidgets.QPushButton("...")
        self.logo_browse.setFixedWidth(24)
        self.logo_browse.clicked.connect(self._browse_logo)
        logo_lay.addWidget(self.logo_path_edit)
        logo_lay.addWidget(self.logo_browse)
        fields_grid.addLayout(logo_lay, 3, 1, 1, 3)

        burn_layout.addLayout(fields_grid)

        # Style adjusters grid (2-row grid)
        style_grid = QtWidgets.QGridLayout()
        style_grid.setSpacing(8)
        style_grid.setContentsMargins(0, 5, 0, 0)

        # Row 0: Font Dropdown & Font Scale Slider
        style_grid.addWidget(QtWidgets.QLabel("Font:"), 0, 0)
        self.font_combo = QtWidgets.QComboBox()
        self.font_combo.addItem("Simplex", "simplex")
        self.font_combo.addItem("Plain", "plain")
        self.font_combo.addItem("Duplex", "duplex")
        self.font_combo.addItem("Complex", "complex")
        self.font_combo.addItem("Triplex", "triplex")
        self.font_combo.setCurrentIndex(0) # Simplex default
        self.font_combo.setFixedWidth(100)
        style_grid.addWidget(self.font_combo, 0, 1)

        style_grid.addWidget(QtWidgets.QLabel("Font Scale:"), 0, 2)
        scale_lay = QtWidgets.QHBoxLayout()
        scale_lay.setContentsMargins(0, 0, 0, 0)
        self.scale_lbl = QtWidgets.QLabel("0.6")
        self.scale_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.scale_slider.setRange(5, 30) # 0.5 - 3.0
        self.scale_slider.setValue(6)     # Default 0.6
        self.scale_slider.valueChanged.connect(lambda v: self.scale_lbl.setText(f"{v/10.0:.1f}"))
        scale_lay.addWidget(self.scale_slider)
        scale_lay.addWidget(self.scale_lbl)
        style_grid.addLayout(scale_lay, 0, 3)

        # Row 1: Thickness Spinbox & Opacity Box Slider
        style_grid.addWidget(QtWidgets.QLabel("Thickness:"), 1, 0)
        self.thick_spin = QtWidgets.QSpinBox()
        self.thick_spin.setRange(1, 6)
        self.thick_spin.setValue(1)       # Default 1
        self.thick_spin.setFixedWidth(50)
        style_grid.addWidget(self.thick_spin, 1, 1)

        style_grid.addWidget(QtWidgets.QLabel("Opacity Box:"), 1, 2)
        op_lay = QtWidgets.QHBoxLayout()
        op_lay.setContentsMargins(0, 0, 0, 0)
        self.opacity_lbl = QtWidgets.QLabel("0.4")
        self.opacity_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(0, 10)
        self.opacity_slider.setValue(4)
        self.opacity_slider.valueChanged.connect(lambda v: self.opacity_lbl.setText(f"{v/10.0:.1f}"))
        op_lay.addWidget(self.opacity_slider)
        op_lay.addWidget(self.opacity_lbl)
        style_grid.addLayout(op_lay, 1, 3)

        # Row 2: Logo Opacity Slider (spanning columns)
        style_grid.addWidget(QtWidgets.QLabel("Logo Opacity:"), 2, 0)
        logo_op_lay = QtWidgets.QHBoxLayout()
        logo_op_lay.setContentsMargins(0, 0, 0, 0)
        self.logo_op_lbl = QtWidgets.QLabel("0.5")
        self.logo_op_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.logo_op_slider.setRange(0, 10)
        self.logo_op_slider.setValue(5)
        self.logo_op_slider.valueChanged.connect(lambda v: self.logo_op_lbl.setText(f"{v/10.0:.1f}"))
        logo_op_lay.addWidget(self.logo_op_slider)
        logo_op_lay.addWidget(self.logo_op_lbl)
        style_grid.addLayout(logo_op_lay, 2, 1, 1, 3)

        burn_layout.addLayout(style_grid)

        # 4. Delivery Slate Options Group Box
        slate_group = QtWidgets.QGroupBox("Delivery Slate Options")
        slate_layout = QtWidgets.QVBoxLayout(slate_group)
        slate_layout.setSpacing(10)

        slate_header = QtWidgets.QHBoxLayout()
        self.slate_chk = QtWidgets.QCheckBox("Prepend Delivery Slate Frame")
        self.slate_chk.setChecked(False)
        self.slate_chk.stateChanged.connect(self._toggle_slate_inputs)
        slate_header.addWidget(self.slate_chk)
        slate_header.addStretch()

        slate_header.addWidget(QtWidgets.QLabel("Duration:"))
        self.slate_duration_spin = QtWidgets.QSpinBox()
        self.slate_duration_spin.setRange(1, 120)
        self.slate_duration_spin.setValue(1)
        self.slate_duration_spin.setSuffix(" frame(s)")
        slate_header.addWidget(self.slate_duration_spin)

        self.slate_preview_btn = QtWidgets.QPushButton("Preview Slate...")
        self.slate_preview_btn.setStyleSheet("background-color: #333; padding: 4px 12px;")
        self.slate_preview_btn.clicked.connect(self._on_slate_preview)
        slate_header.addWidget(self.slate_preview_btn)
        slate_layout.addLayout(slate_header)

        # Template Selection Row
        template_bar = QtWidgets.QHBoxLayout()
        template_bar.addWidget(QtWidgets.QLabel("Slate Template:"))
        self.slate_template_combo = QtWidgets.QComboBox()
        self.slate_template_combo.addItem("Standard Studio Slate", "standard")
        self.slate_template_combo.addItem("Netflix VFX Delivery Slate", "netflix")
        self.slate_template_combo.currentIndexChanged.connect(self._on_slate_template_changed)
        template_bar.addWidget(self.slate_template_combo)
        template_bar.addStretch()
        slate_layout.addLayout(template_bar)

        slate_grid = QtWidgets.QGridLayout()
        slate_grid.setSpacing(6)

        slate_grid.addWidget(QtWidgets.QLabel("Show / Production:"), 0, 0)
        self.slate_show_edit = QtWidgets.QLineEdit("Netflix VFX Templates")
        slate_grid.addWidget(self.slate_show_edit, 0, 1)

        slate_grid.addWidget(QtWidgets.QLabel("Submitting For:"), 0, 2)
        self.slate_submitting_edit = QtWidgets.QLineEdit("SAMPLE")
        slate_grid.addWidget(self.slate_submitting_edit, 0, 3)

        slate_grid.addWidget(QtWidgets.QLabel("Sequence:"), 1, 0)
        self.slate_seq_edit = QtWidgets.QLineEdit("001")
        slate_grid.addWidget(self.slate_seq_edit, 1, 1)

        slate_grid.addWidget(QtWidgets.QLabel("Episode:"), 1, 2)
        self.slate_episode_edit = QtWidgets.QLineEdit("101")
        slate_grid.addWidget(self.slate_episode_edit, 1, 3)

        slate_grid.addWidget(QtWidgets.QLabel("Shot Name:"), 2, 0)
        self.slate_shot_edit = QtWidgets.QLineEdit(shot_def)
        slate_grid.addWidget(self.slate_shot_edit, 2, 1)

        slate_grid.addWidget(QtWidgets.QLabel("Scene:"), 2, 2)
        self.slate_scene_edit = QtWidgets.QLineEdit("001")
        slate_grid.addWidget(self.slate_scene_edit, 2, 3)

        slate_grid.addWidget(QtWidgets.QLabel("Version:"), 3, 0)
        self.slate_ver_edit = QtWidgets.QLineEdit("v001")
        slate_grid.addWidget(self.slate_ver_edit, 3, 1)

        slate_grid.addWidget(QtWidgets.QLabel("Shot Types:"), 3, 2)
        self.slate_shot_types_edit = QtWidgets.QLineEdit("2d comp")
        slate_grid.addWidget(self.slate_shot_types_edit, 3, 3)

        slate_grid.addWidget(QtWidgets.QLabel("Full Version Name:"), 4, 0)
        ver_name_def = f"{shot_def}_slate_VND_v001" if shot_def else "nflx_101_001_0020_slate_VND_v001"
        self.slate_version_name_edit = QtWidgets.QLineEdit(ver_name_def)
        slate_grid.addWidget(self.slate_version_name_edit, 4, 1)

        slate_grid.addWidget(QtWidgets.QLabel("Media Color:"), 4, 2)
        self.slate_color_edit = QtWidgets.QLineEdit("rec709 with show lut")
        slate_grid.addWidget(self.slate_color_edit, 4, 3)

        slate_grid.addWidget(QtWidgets.QLabel("Artist:"), 5, 0)
        self.slate_artist_edit = QtWidgets.QLineEdit("Lead Compositor")
        slate_grid.addWidget(self.slate_artist_edit, 5, 1)

        slate_grid.addWidget(QtWidgets.QLabel("Department:"), 5, 2)
        self.slate_dept_edit = QtWidgets.QLineEdit("Comp / VFX")
        slate_grid.addWidget(self.slate_dept_edit, 5, 3)

        slate_grid.addWidget(QtWidgets.QLabel("Colorspace:"), 6, 0)
        active_cs = "ACEScg"
        if hasattr(self.core, 'loader') and hasattr(self.core.loader, 'output_cs') and self.core.loader.output_cs:
            active_cs = self.core.loader.output_cs
        self.slate_cs_edit = QtWidgets.QLineEdit(active_cs)
        slate_grid.addWidget(self.slate_cs_edit, 6, 1)

        slate_grid.addWidget(QtWidgets.QLabel("Notes:"), 6, 2)
        self.slate_notes_edit = QtWidgets.QLineEdit("Review Delivery")
        slate_grid.addWidget(self.slate_notes_edit, 6, 3)

        slate_grid.addWidget(QtWidgets.QLabel("Shot Description:"), 7, 0)
        self.slate_desc_edit = QtWidgets.QLineEdit("If a description field is required, it goes on the left to provide more space.")
        slate_grid.addWidget(self.slate_desc_edit, 7, 1, 1, 3)

        slate_grid.addWidget(QtWidgets.QLabel("VFX Scope of Work:"), 8, 0)
        self.slate_scope_edit = QtWidgets.QLineEdit("Demo a sample slate.")
        slate_grid.addWidget(self.slate_scope_edit, 8, 1, 1, 3)

        slate_grid.addWidget(QtWidgets.QLabel("Submission Note:"), 9, 0)
        self.slate_note_edit = QtWidgets.QLineEdit("Submitting as an example with all template fields filled out.")
        slate_grid.addWidget(self.slate_note_edit, 9, 1, 1, 3)

        # Dedicated Vendor Logo picker row
        slate_grid.addWidget(QtWidgets.QLabel("Vendor Logo:"), 10, 0)
        logo_lay = QtWidgets.QHBoxLayout()
        self.slate_logo_edit = QtWidgets.QLineEdit()
        self.slate_logo_edit.setPlaceholderText("Select vendor logo image (PNG with transparency, JPG)...")
        if hasattr(self.parent(), 'prefs') and self.parent().prefs.get('vendor_logo_path'):
            self.slate_logo_edit.setText(self.parent().prefs.get('vendor_logo_path', ''))
        self.slate_logo_browse = QtWidgets.QPushButton("Browse...")
        self.slate_logo_browse.setFixedWidth(70)
        self.slate_logo_browse.clicked.connect(self._browse_slate_logo)
        self.slate_logo_clear = QtWidgets.QPushButton("Clear")
        self.slate_logo_clear.setFixedWidth(50)
        self.slate_logo_clear.clicked.connect(lambda: self.slate_logo_edit.clear())
        logo_lay.addWidget(self.slate_logo_edit)
        logo_lay.addWidget(self.slate_logo_browse)
        logo_lay.addWidget(self.slate_logo_clear)
        slate_grid.addLayout(logo_lay, 10, 1, 1, 3)

        slate_layout.addLayout(slate_grid)
        self._toggle_slate_inputs(False)

        # Assemble Tabs
        self.tab_widget = QtWidgets.QTabWidget()

        tab_format = QtWidgets.QWidget()
        tab_format_lay = QtWidgets.QVBoxLayout(tab_format)
        tab_format_lay.setContentsMargins(8, 8, 8, 8)
        tab_format_lay.addWidget(fr_group)
        tab_format_lay.addLayout(chk_layout)
        tab_format_lay.addStretch()
        self.tab_widget.addTab(tab_format, "Video & Format")

        tab_burn = QtWidgets.QWidget()
        tab_burn_lay = QtWidgets.QVBoxLayout(tab_burn)
        tab_burn_lay.setContentsMargins(8, 8, 8, 8)
        tab_burn_lay.addWidget(burn_group)
        tab_burn_lay.addStretch()
        self.tab_widget.addTab(tab_burn, "Burn-In Overlays")

        tab_slate = QtWidgets.QWidget()
        tab_slate_lay = QtWidgets.QVBoxLayout(tab_slate)
        tab_slate_lay.setContentsMargins(8, 8, 8, 8)
        tab_slate_lay.addWidget(slate_group)
        tab_slate_lay.addStretch()
        self.tab_widget.addTab(tab_slate, "Delivery Slate")

        self.layout.addWidget(self.tab_widget)

        # 5. Progress Row
        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.hide()
        self.layout.addWidget(self.progress_bar)

        self.status_lbl = QtWidgets.QLabel("")
        self.status_lbl.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.status_lbl.setStyleSheet("color: #0078d4; font-weight: 500;")
        self.layout.addWidget(self.status_lbl)

        # 6. Action buttons
        actions = QtWidgets.QHBoxLayout()
        actions.addStretch()
        
        self.cancel_btn = QtWidgets.QPushButton("Stop Export")
        self.cancel_btn.clicked.connect(self._on_cancel_clicked)
        actions.addWidget(self.cancel_btn)

        self.export_btn = QtWidgets.QPushButton("Export")
        self.export_btn.clicked.connect(self._on_export_clicked)
        self.export_btn.setStyleSheet("background-color: #0078d4; color: white;")
        actions.addWidget(self.export_btn)

        self.layout.addLayout(actions)

        self.worker = None

    def _toggle_burn_inputs(self, state):
        enabled = (state == 2 or state is True)
        if hasattr(self, 'preset_combo'): self.preset_combo.setEnabled(enabled)
        if hasattr(self, 'timecode_chk'): self.timecode_chk.setEnabled(enabled)
        self.studio_edit.setEnabled(enabled)
        self.task_edit.setEnabled(enabled)
        self.shot_edit.setEnabled(enabled)
        if hasattr(self, 'ver_edit'): self.ver_edit.setEnabled(enabled)
        if hasattr(self, 'artist_edit'): self.artist_edit.setEnabled(enabled)
        self.proj_edit.setEnabled(enabled)
        self.logo_path_edit.setEnabled(enabled)
        self.logo_browse.setEnabled(enabled)
        self.font_combo.setEnabled(enabled)
        self.scale_slider.setEnabled(enabled)
        self.thick_spin.setEnabled(enabled)
        self.opacity_slider.setEnabled(enabled)
        self.logo_op_slider.setEnabled(enabled)

    def _toggle_slate_inputs(self, state):
        enabled = (state == 2 or state is True)
        if hasattr(self, 'slate_template_combo'): self.slate_template_combo.setEnabled(enabled)
        if hasattr(self, 'slate_show_edit'): self.slate_show_edit.setEnabled(enabled)
        if hasattr(self, 'slate_submitting_edit'): self.slate_submitting_edit.setEnabled(enabled)
        if hasattr(self, 'slate_seq_edit'): self.slate_seq_edit.setEnabled(enabled)
        if hasattr(self, 'slate_episode_edit'): self.slate_episode_edit.setEnabled(enabled)
        if hasattr(self, 'slate_shot_edit'): self.slate_shot_edit.setEnabled(enabled)
        if hasattr(self, 'slate_scene_edit'): self.slate_scene_edit.setEnabled(enabled)
        if hasattr(self, 'slate_ver_edit'): self.slate_ver_edit.setEnabled(enabled)
        if hasattr(self, 'slate_shot_types_edit'): self.slate_shot_types_edit.setEnabled(enabled)
        if hasattr(self, 'slate_version_name_edit'): self.slate_version_name_edit.setEnabled(enabled)
        if hasattr(self, 'slate_color_edit'): self.slate_color_edit.setEnabled(enabled)
        if hasattr(self, 'slate_artist_edit'): self.slate_artist_edit.setEnabled(enabled)
        if hasattr(self, 'slate_dept_edit'): self.slate_dept_edit.setEnabled(enabled)
        if hasattr(self, 'slate_cs_edit'): self.slate_cs_edit.setEnabled(enabled)
        if hasattr(self, 'slate_notes_edit'): self.slate_notes_edit.setEnabled(enabled)
        if hasattr(self, 'slate_desc_edit'): self.slate_desc_edit.setEnabled(enabled)
        if hasattr(self, 'slate_scope_edit'): self.slate_scope_edit.setEnabled(enabled)
        if hasattr(self, 'slate_note_edit'): self.slate_note_edit.setEnabled(enabled)
        if hasattr(self, 'slate_duration_spin'): self.slate_duration_spin.setEnabled(enabled)
        if hasattr(self, 'slate_preview_btn'): self.slate_preview_btn.setEnabled(enabled)
        if hasattr(self, 'slate_logo_edit'): self.slate_logo_edit.setEnabled(enabled)
        if hasattr(self, 'slate_logo_browse'): self.slate_logo_browse.setEnabled(enabled)
        if hasattr(self, 'slate_logo_clear'): self.slate_logo_clear.setEnabled(enabled)

    def _browse_slate_logo(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select Vendor Logo", "", "Images (*.png *.jpg *.jpeg *.bmp);;All Files (*.*)"
        )
        if path:
            self.slate_logo_edit.setText(path)
            # Save in parent prefs
            if hasattr(self.parent(), 'prefs') and isinstance(self.parent().prefs, dict):
                self.parent().prefs['vendor_logo_path'] = path
                if hasattr(self.parent(), 'save_preferences'):
                    try:
                        self.parent().save_preferences()
                    except Exception:
                        pass

    def _on_slate_template_changed(self, idx):
        pass

    def _get_fps(self) -> float:
        fps = 24.0
        if hasattr(self, 'core') and self.core and self.core.media:
            fps = self.core.media_fps() or 24.0
        if hasattr(self, 'fps_combo'):
            fps_preset = self.fps_combo.currentData()
            if fps_preset and fps_preset != 'source':
                try:
                    fps = float(fps_preset)
                except (ValueError, TypeError):
                    pass
        return float(fps)

    def _on_preset_changed(self, idx):
        preset = self.preset_combo.currentData()
        if preset in ('client_review', 'internal_vfx', 'dailies', 'netflix'):
            self.timecode_chk.setChecked(True)

    def _on_slate_preview(self):
        from core.slate_builder import SlateBuilder, SlateConfig
        w, h = 1920, 1080
        res_data = self.res_combo.currentData()
        if res_data == '4k': w, h = 3840, 2160
        elif res_data == '720p': w, h = 1280, 720
        elif res_data == 'source' and self.core.media:
            w = getattr(self.core.media, 'width', 1920) or 1920
            h = getattr(self.core.media, 'height', 1080) or 1080

        fps = self._get_fps()
        thumb = None
        if hasattr(self, 'core') and self.core and self.core.media:
            try:
                thumb = self.core.get_frame(self.start_spin.value())
            except Exception:
                try:
                    thumb = self.core.get_frame(self.core.current_frame)
                except Exception:
                    pass

        template = self.slate_template_combo.currentData() if hasattr(self, 'slate_template_combo') else 'standard'
        vendor_logo = self.slate_logo_edit.text().strip() if hasattr(self, 'slate_logo_edit') else ''
        if not vendor_logo and hasattr(self, 'logo_path_edit'):
            vendor_logo = self.logo_path_edit.text().strip()

        cfg = SlateConfig(
            template=template,
            show=self.slate_show_edit.text().strip() if hasattr(self, 'slate_show_edit') else '',
            submitting_for=self.slate_submitting_edit.text().strip() if hasattr(self, 'slate_submitting_edit') else 'SAMPLE',
            sequence=self.slate_seq_edit.text().strip() if hasattr(self, 'slate_seq_edit') else '',
            shot=self.slate_shot_edit.text().strip() if hasattr(self, 'slate_shot_edit') else '',
            version=self.slate_ver_edit.text().strip() if hasattr(self, 'slate_ver_edit') else 'v001',
            version_name=self.slate_version_name_edit.text().strip() if hasattr(self, 'slate_version_name_edit') else '',
            artist=self.slate_artist_edit.text().strip() if hasattr(self, 'slate_artist_edit') else '',
            department=self.slate_dept_edit.text().strip() if hasattr(self, 'slate_dept_edit') else '',
            colorspace=self.slate_cs_edit.text().strip() if hasattr(self, 'slate_cs_edit') else 'ACEScg',
            media_color=self.slate_color_edit.text().strip() if hasattr(self, 'slate_color_edit') else 'rec709 with show lut',
            shot_types=self.slate_shot_types_edit.text().strip() if hasattr(self, 'slate_shot_types_edit') else '2d comp',
            episode=self.slate_episode_edit.text().strip() if hasattr(self, 'slate_episode_edit') else '101',
            scene=self.slate_scene_edit.text().strip() if hasattr(self, 'slate_scene_edit') else '001',
            shot_description=self.slate_desc_edit.text().strip() if hasattr(self, 'slate_desc_edit') else '',
            scope_of_work=self.slate_scope_edit.text().strip() if hasattr(self, 'slate_scope_edit') else '',
            submission_note=self.slate_note_edit.text().strip() if hasattr(self, 'slate_note_edit') else '',
            notes=self.slate_notes_edit.text().strip() if hasattr(self, 'slate_notes_edit') else '',
            studio=self.studio_edit.text().strip() if hasattr(self, 'studio_edit') else '',
            fps=str(fps),
            resolution=f"{w} x {h}",
            frame_range=f"{self.start_spin.value()} - {self.end_spin.value()}",
            logo_path=vendor_logo,
            vendor_logo_path=vendor_logo
        )
        slate_rgb = SlateBuilder.create_slate(w, h, cfg, thumbnail=thumb)
        dlg = SlatePreviewDialog(self, slate_rgb)
        dlg.exec()

    def _format_changed(self):
        preset = str(self.format_combo.currentData() or '')
        path = self.path_edit.text().strip()
        if not path:
            return
            
        base, ext = os.path.splitext(path)
        new_ext = ".mp4" if preset.startswith('mp4') else ".mov"
        self.path_edit.setText(base + new_ext)

    def _range_changed(self):
        mode = self.range_combo.currentData()
        if mode == 'full':
            self.start_spin.setValue(0)
            self.end_spin.setValue(self.core.frame_count() - 1)
            self.start_spin.setEnabled(False)
            self.end_spin.setEnabled(False)
        elif mode == 'in_out':
            r_in = getattr(self.parent(), 'range_in', 0)
            r_out = getattr(self.parent(), 'range_out', self.core.frame_count() - 1 if self.core.media else 0)
            self.start_spin.setValue(r_in)
            self.end_spin.setValue(r_out)
            self.start_spin.setEnabled(False)
            self.end_spin.setEnabled(False)
        elif mode == 'current':
            curr = getattr(self.parent(), 'current_index', 0)
            self.start_spin.setValue(curr)
            self.end_spin.setValue(curr)
            self.start_spin.setEnabled(False)
            self.end_spin.setEnabled(False)
        elif mode == 'custom':
            self.start_spin.setEnabled(True)
            self.end_spin.setEnabled(True)

    def _browse_output(self):
        preset = str(self.format_combo.currentData() or '')
        filt = "MP4 Video (*.mp4)" if preset.startswith('mp4') else "MOV Video (*.mov)"
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save Transcode Video", self.path_edit.text(), f"{filt};;All Files (*.*)"
        )
        if path:
            self.path_edit.setText(path)

    def _browse_logo(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select Watermark Logo", "", "Images (*.png *.jpg *.jpeg *.bmp);;All Files (*.*)"
        )
        if path:
            self.logo_path_edit.setText(path)

    def _on_cancel_clicked(self):
        if self.worker and self.worker.isRunning():
            self.status_lbl.setText("Stopping transcode... please wait.")
            self.worker.cancel()
        else:
            self.reject()

    def _on_export_clicked(self):
        if not self.core.media:
            QtWidgets.QMessageBox.warning(self, "No Media", "Please load a sequence or video first.")
            return

        out_path = self.path_edit.text().strip()
        if not out_path:
            QtWidgets.QMessageBox.warning(self, "Invalid Path", "Please specify a destination output path.")
            return

        # Prepare output resolution
        w, h = self.core.media.size
        res_preset = self.res_combo.currentData()
        if res_preset == '4k':
            w, h = 3840, 2160
        elif res_preset == '1080p':
            w, h = 1920, 1080
        elif res_preset == '720p':
            w, h = 1280, 720
            
        # Determine Frame rate
        fps = self.core.media_fps()
        fps_preset = self.fps_combo.currentData()
        if fps_preset != 'source':
            fps = float(fps_preset)

        # Parse start frame spinner / offset
        first_frame_val = 1001
        if self.core.media.type == 'sequence' and self.core.sequence:
            filename = os.path.basename(self.core.sequence[0])
            match = re.findall(r'\d+', os.path.splitext(filename)[0])
            if match:
                first_frame_val = int(match[-1])

        # Prepare Burn-in options dict
        burnin = {
            'enabled': self.burn_chk.isChecked(),
            'preset': self.preset_combo.currentData() if hasattr(self, 'preset_combo') else 'vfx_ref',
            'show_timecode': self.timecode_chk.isChecked() if hasattr(self, 'timecode_chk') else True,
            'font_name': self.font_combo.currentData(),
            'font_scale': self.scale_slider.value() / 10.0,
            'font_thickness': self.thick_spin.value(),
            'bg_alpha': self.opacity_slider.value() / 10.0,
            'studio': self.studio_edit.text().strip(),
            'show': self.slate_show_edit.text().strip() if hasattr(self, 'slate_show_edit') else self.proj_edit.text().strip(),
            'task': self.task_edit.text().strip(),
            'shot': self.shot_edit.text().strip(),
            'version': self.ver_edit.text().strip() if hasattr(self, 'ver_edit') else 'v001',
            'version_name': self.slate_version_name_edit.text().strip() if hasattr(self, 'slate_version_name_edit') else '',
            'artist': self.artist_edit.text().strip() if hasattr(self, 'artist_edit') else '',
            'colorspace': self.slate_cs_edit.text().strip() if hasattr(self, 'slate_cs_edit') else 'ACEScg',
            'proj_code': self.proj_edit.text().strip(),
            'start_frame_val': first_frame_val,
            'logo_path': self.logo_path_edit.text().strip(),
            'logo_opacity': self.logo_op_slider.value() / 10.0,
        }

        # Prepare Delivery Slate options
        slate_vendor_logo = self.slate_logo_edit.text().strip() if hasattr(self, 'slate_logo_edit') else ''
        if not slate_vendor_logo and hasattr(self, 'logo_path_edit'):
            slate_vendor_logo = self.logo_path_edit.text().strip()

        slate_opts = {
            'enabled': self.slate_chk.isChecked() if hasattr(self, 'slate_chk') else False,
            'duration_frames': self.slate_duration_spin.value() if hasattr(self, 'slate_duration_spin') else 1,
            'config': {
                'template': self.slate_template_combo.currentData() if hasattr(self, 'slate_template_combo') else 'standard',
                'show': self.slate_show_edit.text().strip() if hasattr(self, 'slate_show_edit') else '',
                'submitting_for': self.slate_submitting_edit.text().strip() if hasattr(self, 'slate_submitting_edit') else 'SAMPLE',
                'sequence': self.slate_seq_edit.text().strip() if hasattr(self, 'slate_seq_edit') else '',
                'shot': self.slate_shot_edit.text().strip() if hasattr(self, 'slate_shot_edit') else '',
                'version': self.slate_ver_edit.text().strip() if hasattr(self, 'slate_ver_edit') else 'v001',
                'version_name': self.slate_version_name_edit.text().strip() if hasattr(self, 'slate_version_name_edit') else '',
                'artist': self.slate_artist_edit.text().strip() if hasattr(self, 'slate_artist_edit') else '',
                'department': self.slate_dept_edit.text().strip() if hasattr(self, 'slate_dept_edit') else '',
                'colorspace': self.slate_cs_edit.text().strip() if hasattr(self, 'slate_cs_edit') else 'ACEScg',
                'media_color': self.slate_color_edit.text().strip() if hasattr(self, 'slate_color_edit') else 'rec709 with show lut',
                'shot_types': self.slate_shot_types_edit.text().strip() if hasattr(self, 'slate_shot_types_edit') else '2d comp',
                'episode': self.slate_episode_edit.text().strip() if hasattr(self, 'slate_episode_edit') else '101',
                'scene': self.slate_scene_edit.text().strip() if hasattr(self, 'slate_scene_edit') else '001',
                'shot_description': self.slate_desc_edit.text().strip() if hasattr(self, 'slate_desc_edit') else '',
                'scope_of_work': self.slate_scope_edit.text().strip() if hasattr(self, 'slate_scope_edit') else '',
                'submission_note': self.slate_note_edit.text().strip() if hasattr(self, 'slate_note_edit') else '',
                'notes': self.slate_notes_edit.text().strip() if hasattr(self, 'slate_notes_edit') else '',
                'studio': self.studio_edit.text().strip() if hasattr(self, 'studio_edit') else '',
                'fps': str(fps),
                'resolution': f"{w} x {h}",
                'frame_range': f"{self.start_spin.value()} - {self.end_spin.value()}",
                'logo_path': slate_vendor_logo,
                'vendor_logo_path': slate_vendor_logo
            }
        }

        # Check path directory
        out_dir = os.path.dirname(out_path)
        if not os.path.exists(out_dir):
            try:
                os.makedirs(out_dir, exist_ok=True)
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "Invalid Directory", f"Failed to create output directory:\n{e}")
                return

        # Lock UI
        self._toggle_ui_enabled(False)
        self.progress_bar.show()
        self.progress_bar.setValue(0)
        self.status_lbl.setText("Starting transcode export...")
        
        color_snap = None
        if hasattr(self.core, 'color_pipeline') and self.core.color_pipeline:
            color_snap = self.core.color_pipeline.snapshot()

        # Start Worker QThread
        self.worker = ExportWorker(
            core=self.core,
            output_path=out_path,
            start_frame=self.start_spin.value(),
            end_frame=self.end_spin.value(),
            format_preset=self.format_combo.currentData(),
            width=w,
            height=h,
            aspect_mode='fill',
            fps=fps,
            apply_ocio=self.ocio_chk.isChecked(),
            apply_grade=self.grade_chk.isChecked(),
            burnin_options=burnin,
            include_audio=self.audio_chk.isChecked(),
            exposure=getattr(self.parent(), 'exposure', 0.0),
            gamma=getattr(self.parent(), 'gamma', 1.0),
            color_snapshot=color_snap,
            slate_options=slate_opts
        )
        self.worker.progress.connect(self._on_progress)
        self.worker.finished.connect(self._on_finished)
        self.worker.cancelled.connect(self._on_cancelled)
        self.worker.start()

    def _on_progress(self, current, total, fps_curr):
        pct = int((current / total) * 100)
        self.progress_bar.setValue(pct)
        # Compute time remaining
        remaining = total - current
        time_rem_str = "Calculating..."
        if fps_curr > 0:
            rem_sec = int(remaining / fps_curr)
            time_rem_str = f"{rem_sec}s" if rem_sec < 60 else f"{rem_sec // 60}m {rem_sec % 60}s"
            
        self.status_lbl.setText(f"Processing frame {current} / {total} | {fps_curr:.1f} FPS | Est. Remaining: {time_rem_str}")

    def _on_finished(self, err_msg):
        self._toggle_ui_enabled(True)
        self.progress_bar.hide()
        
        if err_msg:
            self.status_lbl.setText("Export Failed.")
            QtWidgets.QMessageBox.critical(self, "Export Error", f"Transcode failed:\n{err_msg}")
        else:
            self.status_lbl.setText("Export Completed Successfully!")
            path = self.path_edit.text()
            
            box = QtWidgets.QMessageBox(self)
            box.setWindowTitle("Export Complete")
            box.setIcon(QtWidgets.QMessageBox.Icon.Information)
            box.setText(f"Successfully exported video to:\n{path}")
            
            open_folder_btn = box.addButton("Open Folder", QtWidgets.QMessageBox.ButtonRole.AcceptRole)
            close_btn = box.addButton(QtWidgets.QMessageBox.StandardButton.Ok)
            box.setDefaultButton(close_btn)
            
            box.exec()
            
            if box.clickedButton() == open_folder_btn:
                try:
                    folder = os.path.dirname(os.path.normpath(path))
                    if sys.platform == 'win32':
                        os.startfile(folder)
                    else:
                        subprocess.run(['xdg-open', folder])
                except Exception as e:
                    print(f"Failed to open directory: {e}")
                    
            self.accept()

    def _on_cancelled(self):
        self._toggle_ui_enabled(True)
        self.progress_bar.hide()
        self.status_lbl.setText("Export Cancelled.")
        QtWidgets.QMessageBox.information(self, "Export Cancelled", "The transcoding export was cancelled and incomplete file removed.")

    def _toggle_ui_enabled(self, enabled):
        self.path_edit.setEnabled(enabled)
        self.browse_btn.setEnabled(enabled)
        self.format_combo.setEnabled(enabled)
        self.range_combo.setEnabled(enabled)
        self.res_combo.setEnabled(enabled)
        self.fps_combo.setEnabled(enabled)
        
        # Ranges only enabled if custom range is selected
        is_custom = (self.range_combo.currentData() == 'custom')
        self.start_spin.setEnabled(enabled and is_custom)
        self.end_spin.setEnabled(enabled and is_custom)
        
        self.ocio_chk.setEnabled(enabled)
        self.grade_chk.setEnabled(enabled)
        self.audio_chk.setEnabled(enabled)
        
        self.burn_chk.setEnabled(enabled)
        self._toggle_burn_inputs(enabled and self.burn_chk.isChecked())
        
        if hasattr(self, 'slate_chk'):
            self.slate_chk.setEnabled(enabled)
            self._toggle_slate_inputs(enabled and self.slate_chk.isChecked())
            
        self.export_btn.setEnabled(enabled)
        if enabled:
            self.cancel_btn.setText("Stop Export")
        else:
            self.cancel_btn.setText("Stop Export")
