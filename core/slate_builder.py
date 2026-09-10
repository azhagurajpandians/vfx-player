"""
Authoritative Slate Frame Generator for VFX Review and Media Delivery.

Generates industry-standard, high-fidelity slate frames at any target resolution
with metadata blocks, alignment guidelines, studio branding, and optional logo overlays.
"""

import os
import cv2
import datetime
import numpy as np
from dataclasses import dataclass, field, asdict
from typing import Optional, Tuple, Dict, Any

@dataclass
class SlateConfig:
    show: str = ""
    sequence: str = ""
    shot: str = ""
    version: str = "v001"
    artist: str = ""
    department: str = "Comp / VFX"
    date_str: str = ""
    frame_range: str = "1001 - 1100"
    fps: str = "24.0"
    resolution: str = ""
    colorspace: str = "ACEScg"
    notes: str = ""
    studio: str = "VFX Studio"
    logo_path: str = ""
    custom_fields: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SlateConfig':
        if not data:
            return cls()
        fields_set = {f for f in cls.__dataclass_fields__}
        filtered = {k: v for k, v in data.items() if k in fields_set}
        return cls(**filtered)


class SlateBuilder:
    """Builds professional delivery slates formatted for client review or dailies."""

    @staticmethod
    def create_slate(
        width: int = 1920,
        height: int = 1080,
        config: Optional[SlateConfig] = None
    ) -> np.ndarray:
        if config is None:
            config = SlateConfig()

        # Canvas: Dark neutral background (BGR: 22, 24, 28)
        img = np.full((height, width, 3), (28, 24, 22), dtype=np.uint8)

        scale = height / 1080.0
        margin_x = int(90 * scale)
        margin_y = int(70 * scale)
        inner_w = width - 2 * margin_x
        inner_h = height - 2 * margin_y

        # 1. Subtle Outer Tech Border & Corner Accents
        cv2.rectangle(
            img,
            (margin_x, margin_y),
            (width - margin_x, height - margin_y),
            (55, 50, 48),
            max(1, int(1 * scale)),
            lineType=cv2.LINE_AA
        )

        corner_len = int(24 * scale)
        bracket_color = (220, 140, 50) # Vibrant studio cyan/amber BGR: (50, 140, 220) -> Amber BGR is (50, 140, 220)
        thickness = max(2, int(2 * scale))

        # Top-left corner
        cv2.line(img, (margin_x, margin_y), (margin_x + corner_len, margin_y), bracket_color, thickness)
        cv2.line(img, (margin_x, margin_y), (margin_x, margin_y + corner_len), bracket_color, thickness)
        # Top-right corner
        cv2.line(img, (width - margin_x, margin_y), (width - margin_x - corner_len, margin_y), bracket_color, thickness)
        cv2.line(img, (width - margin_x, margin_y), (width - margin_x, margin_y + corner_len), bracket_color, thickness)
        # Bottom-left corner
        cv2.line(img, (margin_x, height - margin_y), (margin_x + corner_len, height - margin_y), bracket_color, thickness)
        cv2.line(img, (margin_x, height - margin_y), (margin_x, height - margin_y - corner_len), bracket_color, thickness)
        # Bottom-right corner
        cv2.line(img, (width - margin_x, height - margin_y), (width - margin_x - corner_len, height - margin_y), bracket_color, thickness)
        cv2.line(img, (width - margin_x, height - margin_y), (width - margin_x, height - margin_y - corner_len), bracket_color, thickness)

        # 2. Header Area: Studio / Show
        header_y = margin_y + int(45 * scale)
        studio_txt = (config.studio or "VFX STUDIO").upper()
        cv2.putText(
            img,
            studio_txt,
            (margin_x + int(30 * scale), header_y),
            cv2.FONT_HERSHEY_DUPLEX,
            0.8 * scale,
            (160, 160, 160),
            max(1, int(1 * scale)),
            lineType=cv2.LINE_AA
        )

        date_val = config.date_str or datetime.date.today().strftime("%Y-%m-%d")
        d_size = cv2.getTextSize(date_val, cv2.FONT_HERSHEY_SIMPLEX, 0.65 * scale, max(1, int(1 * scale)))[0]
        cv2.putText(
            img,
            date_val,
            (width - margin_x - int(30 * scale) - d_size[0], header_y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65 * scale,
            (140, 140, 140),
            max(1, int(1 * scale)),
            lineType=cv2.LINE_AA
        )

        # Separator Line
        sep1_y = header_y + int(25 * scale)
        cv2.line(img, (margin_x + int(30 * scale), sep1_y), (width - margin_x - int(30 * scale), sep1_y), (50, 48, 45), 1)

        # 3. Hero Shot & Version Banner
        hero_y = sep1_y + int(90 * scale)
        show_str = (config.show or "PRODUCTION").upper()
        cv2.putText(
            img,
            show_str,
            (margin_x + int(40 * scale), hero_y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.85 * scale,
            (50, 140, 220), # Amber
            max(1, int(2 * scale)),
            lineType=cv2.LINE_AA
        )

        shot_version = f"{config.shot or 'SHOT_010'}  |  {config.version or 'v001'}"
        hero_shot_y = hero_y + int(65 * scale)
        cv2.putText(
            img,
            shot_version,
            (margin_x + int(40 * scale), hero_shot_y),
            cv2.FONT_HERSHEY_DUPLEX,
            1.6 * scale,
            (245, 245, 245),
            max(2, int(2 * scale)),
            lineType=cv2.LINE_AA
        )

        # Secondary separator
        sep2_y = hero_shot_y + int(45 * scale)
        cv2.line(img, (margin_x + int(30 * scale), sep2_y), (width - margin_x - int(30 * scale), sep2_y), (50, 48, 45), 1)

        # 4. Metadata Grid: 2 columns
        col1_x = margin_x + int(50 * scale)
        col2_x = width // 2 + int(30 * scale)
        row_start_y = sep2_y + int(60 * scale)
        row_spacing = int(48 * scale)

        res_str = config.resolution or f"{width} x {height}"

        col1_items = [
            ("SEQUENCE", config.sequence or "SEQ01"),
            ("ARTIST", config.artist or "Lead Compositor"),
            ("DEPARTMENT", config.department or "VFX"),
            ("FRAME RANGE", config.frame_range or "1001 - 1100"),
        ]

        col2_items = [
            ("FPS", str(config.fps or "24.0")),
            ("RESOLUTION", res_str),
            ("COLORSPACE", config.colorspace or "ACEScg"),
            ("NOTES", config.notes or "Review Delivery"),
        ]

        # Draw Column 1
        for i, (label, val) in enumerate(col1_items):
            y_pos = row_start_y + i * row_spacing
            cv2.putText(img, f"{label}:", (col1_x, y_pos), cv2.FONT_HERSHEY_SIMPLEX, 0.65 * scale, (130, 130, 130), max(1, int(1 * scale)), lineType=cv2.LINE_AA)
            val_x = col1_x + int(190 * scale)
            cv2.putText(img, str(val), (val_x, y_pos), cv2.FONT_HERSHEY_SIMPLEX, 0.7 * scale, (230, 230, 230), max(1, int(1 * scale)), lineType=cv2.LINE_AA)

        # Draw Column 2
        for i, (label, val) in enumerate(col2_items):
            y_pos = row_start_y + i * row_spacing
            cv2.putText(img, f"{label}:", (col2_x, y_pos), cv2.FONT_HERSHEY_SIMPLEX, 0.65 * scale, (130, 130, 130), max(1, int(1 * scale)), lineType=cv2.LINE_AA)
            val_x = col2_x + int(190 * scale)
            cv2.putText(img, str(val), (val_x, y_pos), cv2.FONT_HERSHEY_SIMPLEX, 0.7 * scale, (230, 230, 230), max(1, int(1 * scale)), lineType=cv2.LINE_AA)

        # 5. Optional Studio Logo in Top-Right or Bottom-Right
        if config.logo_path and os.path.isfile(config.logo_path):
            try:
                logo = cv2.imread(config.logo_path, cv2.IMREAD_UNCHANGED)
                if logo is not None:
                    max_logo_h = int(80 * scale)
                    max_logo_w = int(240 * scale)
                    lh, lw = logo.shape[:2]
                    aspect = lw / float(lh)
                    if lh > max_logo_h or lw > max_logo_w:
                        if aspect > (max_logo_w / max_logo_h):
                            new_w = max_logo_w
                            new_h = int(new_w / aspect)
                        else:
                            new_h = max_logo_h
                            new_w = int(new_h * aspect)
                        logo = cv2.resize(logo, (new_w, new_h), interpolation=cv2.INTER_AREA)

                    lh, lw = logo.shape[:2]
                    lx = width - margin_x - int(40 * scale) - lw
                    ly = margin_y + int(70 * scale)

                    if ly + lh < height and lx + lw < width:
                        if logo.shape[2] == 4:
                            alpha = logo[:, :, 3:4].astype(np.float32) / 255.0
                            bgr = logo[:, :, :3]
                            roi = img[ly:ly+lh, lx:lx+lw].astype(np.float32)
                            composite = roi * (1.0 - alpha) + bgr * alpha
                            img[ly:ly+lh, lx:lx+lw] = np.clip(composite, 0, 255).astype(np.uint8)
                        else:
                            img[ly:ly+lh, lx:lx+lw] = logo[:, :, :3]
            except Exception:
                pass

        # 6. Bottom Status Footer
        footer_y = height - margin_y - int(25 * scale)
        confidential_str = "CONFIDENTIAL  |  STRICTLY FOR DIRECT REVIEW ONLY"
        c_size = cv2.getTextSize(confidential_str, cv2.FONT_HERSHEY_SIMPLEX, 0.5 * scale, 1)[0]
        cv2.putText(
            img,
            confidential_str,
            ((width - c_size[0]) // 2, footer_y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5 * scale,
            (90, 90, 90),
            1,
            lineType=cv2.LINE_AA
        )

        # Convert from OpenCV BGR to RGB for standard image pipelines
        return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
