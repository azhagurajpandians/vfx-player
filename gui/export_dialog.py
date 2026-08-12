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
                 burnin_options, include_audio, exposure=0.0, gamma=1.0):
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
        self.is_cancelled = False

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
        if self.format_preset == 'mp4':
            cmd.extend([
                '-c:v', 'libx264',
                '-pix_fmt', 'yuv420p',
                '-crf', '18',
                '-preset', 'medium'
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

    def _process_color(self, img, ocio_config):
        """Transform colorspaces (OCIO) and apply viewer gain/gamma."""
        # 1. Video files are uint8
        if img.dtype == np.uint8:
            if not self.apply_grade:
                return img
            # Grade uint8 directly
            img_float = img.astype(np.float32) / 255.0
            if self.exposure != 0.0:
                img_float *= pow(2.0, self.exposure)
            if self.gamma != 1.0 and abs(self.gamma) > 0.01:
                np.clip(img_float, 0.0, None, out=img_float)
                np.power(img_float, 1.0 / self.gamma, out=img_float)
            return np.clip(img_float * 255.0, 0, 255).astype(np.uint8)

        # 2. Float32 images (EXR)
        # Apply OCIO if config and colorspaces are available
        if ocio_config and self.apply_ocio:
            try:
                import OpenImageIO as oiio
                h, w, c = img.shape
                if not img.flags['C_CONTIGUOUS']:
                    img = np.ascontiguousarray(img)
                spec = oiio.ImageSpec(w, h, c, oiio.TypeFloat)
                buf = oiio.ImageBuf(spec)
                buf.set_pixels(oiio.ROI(), img)
                
                in_cs = self.core.loader.ocio_input_cs
                out_cs = self.core.loader.ocio_output_cs
                cfg_path = self.core.loader.ocio_config_path or ""
                
                res_buf = oiio.ImageBufAlgo.colorconvert(buf, in_cs, out_cs, False, cfg_path)
                if not res_buf.has_error:
                    raw = res_buf.get_pixels(oiio.TypeFloat)
                    img = np.array(raw, dtype=np.float32).reshape((h, w, c))
            except Exception as e:
                print(f"OCIO color conversion failed in export: {e}")

        # Apply gain/gamma adjustments
        if self.apply_grade:
            if self.exposure != 0.0:
                img *= pow(2.0, self.exposure)
            if self.gamma != 1.0 and abs(self.gamma) > 0.01:
                np.clip(img, 0.0, None, out=img)
                img = np.power(img, 1.0 / self.gamma)

        # Clamp and cast to uint8
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

        # 1. Top Left: Studio Name
        studio = self.burnin_options.get('studio', '').strip()
        if studio:
            self._draw_text(img_uint8, studio, "top_left", font, font_scale, font_thickness, margin, bg_alpha)

        # 2. Top Center: Shot Name
        shot = self.burnin_options.get('shot', '').strip()
        if shot:
            self._draw_text(img_uint8, shot, "top_center", font, font_scale, font_thickness, margin, bg_alpha)

        # 3. Top Right: Task Name
        task = self.burnin_options.get('task', '').strip()
        if task:
            self._draw_text(img_uint8, task, "top_right", font, font_scale, font_thickness, margin, bg_alpha)

        # 4. Bottom Left: Date (YYYY-MM-DD)
        date_str = datetime.date.today().strftime('%Y-%m-%d')
        self._draw_text(img_uint8, date_str, "bottom_left", font, font_scale, font_thickness, margin, bg_alpha)

        # 5. Bottom Center: Project Code
        proj_code = self.burnin_options.get('proj_code', '').strip()
        if proj_code:
            self._draw_text(img_uint8, proj_code, "bottom_center", font, font_scale, font_thickness, margin, bg_alpha)

        # 6. Bottom Right: Start Frame - Current Frame - End Frame
        user_start_frame = self.burnin_options.get('start_frame_val', 0)
        curr_frame_val = user_start_frame + (frame_idx - self.start_frame)
        total_frames = self.end_frame - self.start_frame + 1
        user_end_frame = user_start_frame + total_frames - 1

        # Use parsed file digits if sequence number mode is available
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
            frame_str = f"{user_start_frame} - {curr_frame_val} - {user_end_frame}"
        
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
        self.format_combo.addItem("MOV (ProRes 422 HQ)", "prores_hq")
        self.format_combo.addItem("MOV (ProRes 422 Standard)", "prores_std")
        self.format_combo.addItem("MOV (ProRes 4444)", "prores_4444")
        self.format_combo.addItem("MOV (DNxHR HQ)", "dnxhr_hq")
        self.format_combo.currentIndexChanged.connect(self._format_changed)
        fr_grid.addWidget(self.format_combo, 0, 1)

        # Col 2, 3: Frame Range
        fr_grid.addWidget(QtWidgets.QLabel("Frame Range:"), 0, 2)
        self.range_combo = QtWidgets.QComboBox()
        self.range_combo.addItem("Entire Sequence", "full")
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

        self.burn_chk = QtWidgets.QCheckBox("Enable Burn-ins")
        self.burn_chk.setChecked(True)
        self.burn_chk.stateChanged.connect(self._toggle_burn_inputs)
        burn_layout.addWidget(self.burn_chk)

        # Form grid for text field entries (Studio Name, Shot, Task, Project Code, Logo)
        fields_grid = QtWidgets.QGridLayout()
        fields_grid.setSpacing(6)

        fields_grid.addWidget(QtWidgets.QLabel("Studio Name:"), 0, 0)
        self.studio_edit = QtWidgets.QLineEdit("Knack Studios")
        fields_grid.addWidget(self.studio_edit, 0, 1)

        fields_grid.addWidget(QtWidgets.QLabel("Task Name:"), 0, 2)
        self.task_edit = QtWidgets.QLineEdit("Edit")
        fields_grid.addWidget(self.task_edit, 0, 3)

        fields_grid.addWidget(QtWidgets.QLabel("Shot Name:"), 1, 0)
        self.shot_edit = QtWidgets.QLineEdit("fhgcn")
        if self.core.media:
            self.shot_edit.setText(os.path.basename(self.core.media.path))
        fields_grid.addWidget(self.shot_edit, 1, 1)

        fields_grid.addWidget(QtWidgets.QLabel("Project Code:"), 1, 2)
        self.proj_edit = QtWidgets.QLineEdit("KNK")
        fields_grid.addWidget(self.proj_edit, 1, 3)

        # Logo Watermark selection row
        fields_grid.addWidget(QtWidgets.QLabel("Logo Watermark:"), 2, 0)
        logo_lay = QtWidgets.QHBoxLayout()
        self.logo_path_edit = QtWidgets.QLineEdit()
        self.logo_path_edit.setPlaceholderText("Select logo image to bake in center...")
        self.logo_browse = QtWidgets.QPushButton("...")
        self.logo_browse.setFixedWidth(24)
        self.logo_browse.clicked.connect(self._browse_logo)
        logo_lay.addWidget(self.logo_path_edit)
        logo_lay.addWidget(self.logo_browse)
        fields_grid.addLayout(logo_lay, 2, 1, 1, 3)

        burn_layout.addLayout(fields_grid)

        # Style adjusters grid (2-row grid instead of single squished row)
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
        self.layout.addWidget(burn_group)

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
        enabled = (state == 2)
        self.studio_edit.setEnabled(enabled)
        self.task_edit.setEnabled(enabled)
        self.shot_edit.setEnabled(enabled)
        self.proj_edit.setEnabled(enabled)
        self.logo_path_edit.setEnabled(enabled)
        self.logo_browse.setEnabled(enabled)
        self.font_combo.setEnabled(enabled)
        self.scale_slider.setEnabled(enabled)
        self.thick_spin.setEnabled(enabled)
        self.opacity_slider.setEnabled(enabled)
        self.logo_op_slider.setEnabled(enabled)

    def _format_changed(self):
        preset = self.format_combo.currentData()
        path = self.path_edit.text().strip()
        if not path:
            return
            
        base, ext = os.path.splitext(path)
        new_ext = ".mp4" if preset == 'mp4' else ".mov"
        self.path_edit.setText(base + new_ext)

    def _range_changed(self):
        mode = self.range_combo.currentData()
        if mode == 'full':
            self.start_spin.setValue(0)
            self.end_spin.setValue(self.core.frame_count() - 1)
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
        preset = self.format_combo.currentData()
        filt = "MP4 Video (*.mp4)" if preset == 'mp4' else "MOV Video (*.mov)"
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
            'font_name': self.font_combo.currentData(),
            'font_scale': self.scale_slider.value() / 10.0,
            'font_thickness': self.thick_spin.value(),
            'bg_alpha': self.opacity_slider.value() / 10.0,
            'studio': self.studio_edit.text().strip(),
            'task': self.task_edit.text().strip(),
            'shot': self.shot_edit.text().strip(),
            'proj_code': self.proj_edit.text().strip(),
            'start_frame_val': first_frame_val,
            'logo_path': self.logo_path_edit.text().strip(),
            'logo_opacity': self.logo_op_slider.value() / 10.0,
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
            gamma=getattr(self.parent(), 'gamma', 1.0)
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
        
        self.export_btn.setEnabled(enabled)
        if enabled:
            self.cancel_btn.setText("Stop Export")
        else:
            self.cancel_btn.setText("Stop Export")
