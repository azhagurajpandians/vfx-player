"""
TimelineService: Frame-accurate media timeline and SMPTE timecode engine.

Handles rational timebase conversions (avoiding float drift on 23.976, 29.97, 59.94 fps),
deterministic PTS <-> frame mapping, and standard SMPTE 12M Timecode generation and parsing.
"""

from fractions import Fraction
import math
import re
from typing import Tuple, Optional, Union

# Common VFX / Broadcast frame rates as exact rational fractions
STANDARD_FPS_RATIONALS = {
    23.976: Fraction(24000, 1001),
    23.98:  Fraction(24000, 1001),
    24.0:   Fraction(24, 1),
    25.0:   Fraction(25, 1),
    29.97:  Fraction(30000, 1001),
    30.0:   Fraction(30, 1),
    47.952: Fraction(48000, 1001),
    48.0:   Fraction(48, 1),
    50.0:   Fraction(50, 1),
    59.94:  Fraction(60000, 1001),
    60.0:   Fraction(60, 1),
}


def to_rational_fps(fps: Union[float, int, str, Fraction]) -> Fraction:
    """Convert any FPS representation to an authoritative rational Fraction."""
    if isinstance(fps, Fraction):
        return fps
    if isinstance(fps, int):
        return Fraction(fps, 1)
    if isinstance(fps, str):
        if '/' in fps:
            parts = fps.split('/')
            return Fraction(int(parts[0]), int(parts[1]))
        try:
            fps_val = float(fps)
        except ValueError:
            return Fraction(24, 1)
    else:
        fps_val = float(fps)

    # Check for close standard rates within 0.005 tolerance
    for std_rate, rat in STANDARD_FPS_RATIONALS.items():
        if abs(fps_val - std_rate) < 0.005:
            return rat

    return Fraction(fps_val).limit_denominator(10000)


def is_drop_frame_rate(fps: Union[float, Fraction]) -> bool:
    """Return True if rate is typically drop-frame (29.97 or 59.94)."""
    f = float(fps)
    return abs(f - 29.97) < 0.01 or abs(f - 59.94) < 0.01


def frame_to_timecode(
    frame: int,
    fps: Union[float, Fraction] = 24.0,
    drop_frame: Optional[bool] = None,
    start_frame: int = 0,
    start_timecode: str = "00:00:00:00"
) -> str:
    """
    Format frame number as standard SMPTE timecode (HH:MM:SS:FF or HH:MM:SS;FF for drop-frame).
    
    Adheres strictly to SMPTE 12M specifications.
    """
    fps_rat = to_rational_fps(fps)
    fps_val = float(fps_rat)
    if fps_val <= 0:
        return "--:--:--:--"

    nominal_fps = round(fps_val)
    if drop_frame is None:
        drop_frame = is_drop_frame_rate(fps_rat)

    # Offset by sequence start frame and start timecode if provided
    offset_frames = 0
    if start_timecode and start_timecode != "00:00:00:00":
        offset_frames = timecode_to_frame(start_timecode, fps_rat, drop_frame)

    total_frame = (frame - start_frame) + offset_frames
    if total_frame < 0:
        total_frame = 0

    if not drop_frame or nominal_fps not in (30, 60):
        # Non-drop frame calculation
        total_seconds = total_frame // nominal_fps
        ff = total_frame % nominal_fps
        ss = total_seconds % 60
        mm = (total_seconds // 60) % 60
        hh = (total_seconds // 3600) % 24
        return f"{hh:02d}:{mm:02d}:{ss:02d}:{ff:02d}"

    # --- SMPTE 12M Drop-Frame Algorithm ---
    # At 29.97 fps, 2 frames are dropped every minute except minutes ending in 0.
    # At 59.94 fps, 4 frames are dropped every minute except minutes ending in 0.
    drop_frames = 2 if nominal_fps == 30 else 4
    frames_per_minute = nominal_fps * 60 - drop_frames
    frames_per_10_minutes = frames_per_minute * 10 + drop_frames

    d = total_frame // frames_per_10_minutes
    m = total_frame % frames_per_10_minutes

    if m > drop_frames:
        total_frame += (drop_frames * 9 * d) + drop_frames * ((m - drop_frames) // frames_per_minute)
    else:
        total_frame += drop_frames * 9 * d

    ff = total_frame % nominal_fps
    total_seconds = total_frame // nominal_fps
    ss = total_seconds % 60
    mm = (total_seconds // 60) % 60
    hh = (total_seconds // 3600) % 24

    return f"{hh:02d}:{mm:02d}:{ss:02d};{ff:02d}"


def timecode_to_frame(
    tc: str,
    fps: Union[float, Fraction] = 24.0,
    drop_frame: Optional[bool] = None,
    start_frame: int = 0
) -> int:
    """
    Parse standard SMPTE timecode (HH:MM:SS:FF or HH:MM:SS;FF) back to zero-based frame index.
    """
    fps_rat = to_rational_fps(fps)
    fps_val = float(fps_rat)
    nominal_fps = round(fps_val)

    if drop_frame is None:
        drop_frame = ';' in tc or is_drop_frame_rate(fps_rat)

    # Match timecode parts
    m = re.match(r'^(\d{2})[:;](\d{2})[:;](\d{2})[:;](\d{2})$', tc.strip())
    if not m:
        return 0

    hh, mm, ss, ff = [int(p) for p in m.groups()]

    if not drop_frame or nominal_fps not in (30, 60):
        total_seconds = hh * 3600 + mm * 60 + ss
        return (total_seconds * nominal_fps + ff) + start_frame

    # Drop frame reverse calculation
    drop_frames = 2 if nominal_fps == 30 else 4
    total_minutes = 60 * hh + mm
    total_frame = (
        (nominal_fps * 60 * 60 * hh)
        + (nominal_fps * 60 * mm)
        + (nominal_fps * ss)
        + ff
        - drop_frames * (total_minutes - (total_minutes // 10))
    )
    return total_frame + start_frame


class TimelineService:
    """
    Authoritative media timeline and timebase coordinator.
    
    Provides rational PTS <-> frame conversions, avoiding floating-point
    drift during seeks and long playback on non-integer frame rates.
    """

    def __init__(
        self,
        fps: Union[float, int, str, Fraction] = 24.0,
        time_base: Union[float, str, Fraction, None] = None,
        start_pts: int = 0,
        frame_count: int = 0,
        start_timecode: str = "00:00:00:00",
        drop_frame: Optional[bool] = None
    ):
        self.fps = to_rational_fps(fps)
        self.time_base = to_rational_fps(time_base) if time_base else Fraction(1, int(round(float(self.fps) * 1000)))
        self.start_pts = start_pts
        self.frame_count = frame_count
        self.start_timecode = start_timecode
        self.drop_frame = drop_frame if drop_frame is not None else is_drop_frame_rate(self.fps)

    def frame_to_pts(self, frame_index: int) -> int:
        """
        Convert frame index to exact container PTS using rational arithmetic:
        pts = start_pts + (frame_index / fps) / time_base
        """
        if self.time_base == 0:
            return 0
        # Rational: frame_index * (1 / fps) * (1 / time_base)
        pts_fraction = Fraction(frame_index, 1) / (self.fps * self.time_base)
        return self.start_pts + int(round(float(pts_fraction)))

    def pts_to_frame(self, pts: int) -> int:
        """
        Convert container PTS to frame index using rational arithmetic:
        frame_index = (pts - start_pts) * time_base * fps
        """
        pts_rel = pts - self.start_pts
        frame_fraction = Fraction(pts_rel, 1) * self.time_base * self.fps
        return max(0, int(round(float(frame_fraction))))

    def frame_to_seconds(self, frame_index: int) -> float:
        """Return presentation time in seconds for a given frame."""
        return float(Fraction(frame_index, 1) / self.fps)

    def seconds_to_frame(self, seconds: float) -> int:
        """Return frame index for a given presentation time in seconds."""
        return max(0, int(round(float(Fraction(str(round(seconds, 6))) * self.fps))))

    def format_timecode(self, frame_index: int) -> str:
        """Format frame index using timeline's configuration and SMPTE standard."""
        return frame_to_timecode(
            frame=frame_index,
            fps=self.fps,
            drop_frame=self.drop_frame,
            start_timecode=self.start_timecode
        )

    def parse_timecode(self, tc_str: str) -> int:
        """Parse timecode string into a frame index."""
        return timecode_to_frame(
            tc=tc_str,
            fps=self.fps,
            drop_frame=self.drop_frame
        )

    # Static utility bindings
    frame_to_timecode = staticmethod(frame_to_timecode)
    timecode_to_frame = staticmethod(timecode_to_frame)
    to_rational_fps = staticmethod(to_rational_fps)
