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
    # Netflix delivery template fields
    template: str = "standard"  # "standard" or "netflix"
    submitting_for: str = "SAMPLE"
    version_name: str = ""
    shot_types: str = "2d comp"
    shot_description: str = ""
    scope_of_work: str = ""
    submission_note: str = ""
    episode: str = ""
    scene: str = ""
    media_color: str = ""
    vendor_logo_path: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SlateConfig':
        if not data:
            return cls()
        fields_set = {f for f in cls.__dataclass_fields__}
        filtered = {k: v for k, v in data.items() if k in fields_set}
        return cls(**filtered)


def _draw_wrapped_text(
    img: np.ndarray,
    text: str,
    x: int,
    y: int,
    max_w: int,
    font: int,
    font_scale: float,
    color: Tuple[int, int, int],
    line_spacing: int,
    thickness: int = 1
) -> int:
    """Draws multiline text wrapped to max_w, returning the final baseline y."""
    if not text:
        return y
    words = text.split(' ')
    current_line = []
    curr_y = y

    for word in words:
        test_line = ' '.join(current_line + [word])
        w = cv2.getTextSize(test_line, font, font_scale, thickness)[0][0]
        if w <= max_w:
            current_line.append(word)
        else:
            if current_line:
                line_str = ' '.join(current_line)
                cv2.putText(img, line_str, (x, curr_y), font, font_scale, color, thickness, cv2.LINE_AA)
                curr_y += line_spacing
                current_line = [word]
            else:
                cv2.putText(img, word, (x, curr_y), font, font_scale, color, thickness, cv2.LINE_AA)
                curr_y += line_spacing
                current_line = []

    if current_line:
        line_str = ' '.join(current_line)
        cv2.putText(img, line_str, (x, curr_y), font, font_scale, color, thickness, cv2.LINE_AA)
        curr_y += line_spacing

    return curr_y


class SlateBuilder:
    """Builds professional delivery slates formatted for client review or dailies."""

    @staticmethod
    def create_slate(
        width: int = 1920,
        height: int = 1080,
        config: Optional[SlateConfig] = None,
        thumbnail: Optional[np.ndarray] = None
    ) -> np.ndarray:
        if config is None:
            config = SlateConfig()

        if getattr(config, 'template', 'standard') == 'netflix':
            return SlateBuilder._create_netflix_slate(width, height, config, thumbnail)
        return SlateBuilder._create_standard_slate(width, height, config)

    @staticmethod
    def _create_standard_slate(
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

    @staticmethod
    def _create_netflix_slate(
        width: int = 1920,
        height: int = 1080,
        config: Optional[SlateConfig] = None,
        thumbnail: Optional[np.ndarray] = None
    ) -> np.ndarray:
        if config is None:
            config = SlateConfig()

        # Canvas: Dark neutral charcoal matching Netflix specification (BGR: 24, 24, 24)
        img = np.full((height, width, 3), (24, 24, 24), dtype=np.uint8)

        scale = height / 1080.0
        left_margin = int(48 * scale)
        right_margin = int(48 * scale)
        col_gap = int(36 * scale)

        # 55% left column, remainder right column
        left_w = int(width * 0.54)
        right_x = left_margin + left_w + col_gap
        right_w = width - right_x - right_margin

        # -------------------------------------------------------------
        # 1. HEADER (Show & Submitting For)
        # -------------------------------------------------------------
        header_y = int(58 * scale)
        cv2.putText(img, "Show:", (left_margin, header_y), cv2.FONT_HERSHEY_SIMPLEX, 0.68 * scale, (140, 140, 140), max(1, int(1 * scale)), lineType=cv2.LINE_AA)
        show_name = config.show or "Netflix VFX Templates"
        cv2.putText(img, show_name, (left_margin + int(60 * scale), header_y), cv2.FONT_HERSHEY_DUPLEX, 0.85 * scale, (255, 255, 255), max(1, int(1.5 * scale)), lineType=cv2.LINE_AA)

        # Right side of left header: Submitting For
        submitting_label = "Submitting For:"
        sub_for_val = (config.submitting_for or "SAMPLE").upper()
        sub_val_size = cv2.getTextSize(sub_for_val, cv2.FONT_HERSHEY_DUPLEX, 0.9 * scale, max(2, int(2 * scale)))[0]
        sub_lbl_size = cv2.getTextSize(submitting_label, cv2.FONT_HERSHEY_SIMPLEX, 0.65 * scale, max(1, int(1 * scale)))[0]

        sub_val_x = left_margin + left_w - sub_val_size[0]
        sub_lbl_x = sub_val_x - sub_lbl_size[0] - int(12 * scale)

        cv2.putText(img, submitting_label, (sub_lbl_x, header_y), cv2.FONT_HERSHEY_SIMPLEX, 0.65 * scale, (140, 140, 140), max(1, int(1 * scale)), lineType=cv2.LINE_AA)
        cv2.putText(img, sub_for_val, (sub_val_x, header_y), cv2.FONT_HERSHEY_DUPLEX, 0.9 * scale, (255, 255, 255), max(2, int(2 * scale)), lineType=cv2.LINE_AA)

        # Netflix Red Divider Accent line (#E50914 -> BGR: 20, 9, 229)
        red_bar_y = header_y + int(24 * scale)
        cv2.line(img, (left_margin, red_bar_y), (left_margin + left_w, red_bar_y), (20, 9, 229), max(2, int(3 * scale)), lineType=cv2.LINE_AA)

        # -------------------------------------------------------------
        # 2. LEFT COLUMN DATA ROWS (with alternating row shading)
        # -------------------------------------------------------------
        date_str = config.date_str or datetime.date.today().strftime("%Y-%m-%d")
        version_name_str = config.version_name or config.version or "nflx_101_001_0020_slate_VND_v001"
        shot_types_str = config.shot_types or "2d comp"
        desc_str = config.shot_description or "If a description field is required, it goes on the left to provide more space."
        scope_str = config.scope_of_work or "Demo a sample slate."
        note_str = config.submission_note or (
            "Submitting as an example with all template fields filled out. "
            "As well as the additional fields; shot description, Episode, Scene, "
            "and Version # that were requested specifically by production."
        )

        rows = [
            ("Version Name:", version_name_str, True, True),       # (label, text, shaded, is_hero_bold)
            ("Date:", date_str, False, False),
            ("Shot Types:", shot_types_str, True, False),
            ("Shot\nDescription:", desc_str, False, False),
            ("VFX Scope Of\nWork:", scope_str, True, False),
            ("Submission\nNote:", note_str, False, False),
        ]

        curr_y = red_bar_y + int(14 * scale)
        label_col_w = int(145 * scale)
        text_w = left_w - label_col_w - int(20 * scale)

        for label, text, is_shaded, is_bold in rows:
            # Measure height required for text
            font_s = 0.88 * scale if is_bold else 0.72 * scale
            font_t = cv2.FONT_HERSHEY_DUPLEX if is_bold else cv2.FONT_HERSHEY_SIMPLEX
            thk = max(2, int(1.8 * scale)) if is_bold else max(1, int(1 * scale))
            line_h = int(32 * scale if is_bold else 26 * scale)

            # Split text into lines to compute block height
            words = text.split(' ') if text else []
            lines_cnt = 0
            cur_line = []
            for w in words:
                test_l = ' '.join(cur_line + [w])
                if cv2.getTextSize(test_l, font_t, font_s, thk)[0][0] <= text_w:
                    cur_line.append(w)
                else:
                    lines_cnt += 1
                    cur_line = [w]
            if cur_line or not words:
                lines_cnt += 1

            block_h = max(int(46 * scale), lines_cnt * line_h + int(18 * scale))

            # Shaded row background
            if is_shaded:
                cv2.rectangle(
                    img,
                    (left_margin, curr_y),
                    (left_margin + left_w, curr_y + block_h),
                    (34, 34, 34),
                    -1
                )

            # Draw Label (supports 2-line labels like "Shot\nDescription:")
            lbl_parts = label.split('\n')
            lbl_start_y = curr_y + int(28 * scale) if len(lbl_parts) == 1 else curr_y + int(20 * scale)
            for li, lp in enumerate(lbl_parts):
                cv2.putText(
                    img,
                    lp,
                    (left_margin + int(12 * scale), lbl_start_y + li * int(20 * scale)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6 * scale,
                    (145, 145, 145),
                    max(1, int(1 * scale)),
                    lineType=cv2.LINE_AA
                )

            # Draw Value Text (wrapped)
            val_start_y = curr_y + int(30 * scale) if is_bold else curr_y + int(26 * scale)
            _draw_wrapped_text(
                img,
                text,
                left_margin + label_col_w,
                val_start_y,
                text_w,
                font_t,
                font_s,
                (255, 255, 255) if is_bold else (230, 230, 230),
                line_h,
                thk
            )

            curr_y += block_h + int(4 * scale)

        # -------------------------------------------------------------
        # 3. RIGHT COLUMN: THUMBNAIL (16:9)
        # -------------------------------------------------------------
        thumb_y = int(45 * scale)
        thumb_h = int(right_w * 9 / 16)

        if thumbnail is not None:
            try:
                # Ensure thumbnail is 3-channel uint8
                th_img = thumbnail
                if th_img.dtype != np.uint8:
                    th_img = np.clip(th_img * 255.0, 0, 255).astype(np.uint8)
                if len(th_img.shape) == 2:
                    th_img = cv2.cvtColor(th_img, cv2.COLOR_GRAY2BGR)
                elif th_img.shape[2] == 4:
                    th_img = cv2.cvtColor(th_img, cv2.COLOR_RGBA2BGR)
                else:
                    # Input is RGB from VFXPlayer pipeline, convert to BGR for canvas
                    th_img = cv2.cvtColor(th_img, cv2.COLOR_RGB2BGR)

                th_resized = cv2.resize(th_img, (right_w, thumb_h), interpolation=cv2.INTER_AREA)
                img[thumb_y:thumb_y+thumb_h, right_x:right_x+right_w] = th_resized
            except Exception:
                cv2.rectangle(img, (right_x, thumb_y), (right_x + right_w, thumb_y + thumb_h), (38, 38, 38), -1)
        else:
            cv2.rectangle(img, (right_x, thumb_y), (right_x + right_w, thumb_y + thumb_h), (38, 38, 38), -1)
            cv2.putText(
                img,
                "PREVIEW FRAME",
                (right_x + int(right_w * 0.3), thumb_y + int(thumb_h * 0.52)),
                cv2.FONT_HERSHEY_DUPLEX,
                0.75 * scale,
                (90, 90, 90),
                1,
                lineType=cv2.LINE_AA
            )

        # Thumbnail border
        cv2.rectangle(img, (right_x, thumb_y), (right_x + right_w, thumb_y + thumb_h), (50, 50, 50), 1)

        # -------------------------------------------------------------
        # 4. SMPTE / CALIBRATION COLOR BARS STRIP
        # -------------------------------------------------------------
        bars_y = thumb_y + thumb_h + int(6 * scale)
        bars_h = int(48 * scale)
        half_h = int(bars_h * 0.5)

        # Top row: 8 color patches (18% Gray, Yellow, Cyan, Green, Magenta, Red, Blue, White)
        colors_bgr = [
            (128, 128, 128),  # 18% Gray
            (0, 230, 230),    # Yellow
            (230, 230, 0),    # Cyan
            (0, 215, 0),      # Green
            (230, 0, 230),    # Magenta
            (0, 0, 230),      # Red
            (230, 0, 0),      # Blue
            (255, 255, 255),  # White
        ]
        num_c = len(colors_bgr)
        patch_w = right_w / float(num_c)
        for i, col in enumerate(colors_bgr):
            px1 = right_x + int(i * patch_w)
            px2 = right_x + int((i + 1) * patch_w) if i < num_c - 1 else right_x + right_w
            cv2.rectangle(img, (px1, bars_y), (px2, bars_y + half_h), col, -1)

        # Bottom row: 11-step grayscale ramp (0% to 100% white)
        num_g = 11
        g_w = right_w / float(num_g)
        for i in range(num_g):
            gx1 = right_x + int(i * g_w)
            gx2 = right_x + int((i + 1) * g_w) if i < num_g - 1 else right_x + right_w
            level = int(i * 25.5)
            cv2.rectangle(img, (gx1, bars_y + half_h), (gx2, bars_y + bars_h), (level, level, level), -1)

        # Color bar border
        cv2.rectangle(img, (right_x, bars_y), (right_x + right_w, bars_y + bars_h), (60, 60, 60), 1)

        # -------------------------------------------------------------
        # 5. TECHNICAL METADATA SPECIFICATIONS TABLE
        # -------------------------------------------------------------
        table_y = bars_y + bars_h + int(24 * scale)
        row_step = int(28 * scale)

        tech_fields = [
            ("Vendor:", config.studio or "Template Team"),
            ("Shot Name:", config.shot or "nflx_101_001_0020"),
            ("Episode:", config.episode or "101"),
            ("Sequence Name:", config.sequence or "001"),
            ("Scene:", config.scene or "001"),
            ("Frames:", config.frame_range or "1000 - 1030 (30)"),
            ("Media Color:", config.media_color or config.colorspace or "rec709 with show lut"),
        ]

        for i, (k, v) in enumerate(tech_fields):
            ty = table_y + i * row_step
            cv2.putText(img, k, (right_x + int(4 * scale), ty), cv2.FONT_HERSHEY_SIMPLEX, 0.65 * scale, (140, 140, 140), max(1, int(1 * scale)), lineType=cv2.LINE_AA)
            v_size = cv2.getTextSize(v, cv2.FONT_HERSHEY_DUPLEX, 0.68 * scale, max(1, int(1 * scale)))[0]
            cv2.putText(img, v, (right_x + right_w - v_size[0] - int(4 * scale), ty), cv2.FONT_HERSHEY_DUPLEX, 0.68 * scale, (240, 240, 240), max(1, int(1 * scale)), lineType=cv2.LINE_AA)

        # -------------------------------------------------------------
        # 6. VENDOR LOGO BADGE (Bottom-Right White Box)
        # -------------------------------------------------------------
        badge_w = int(240 * scale)
        badge_h = int(95 * scale)
        badge_x = width - right_margin - badge_w
        badge_y = height - int(45 * scale) - badge_h

        # Solid pure white box matching reference
        cv2.rectangle(img, (badge_x, badge_y), (badge_x + badge_w, badge_y + badge_h), (255, 255, 255), -1)

        logo_rendered = False
        logo_candidate = config.vendor_logo_path or config.logo_path

        if logo_candidate and os.path.isfile(logo_candidate):
            try:
                vlogo = cv2.imread(logo_candidate, cv2.IMREAD_UNCHANGED)
                if vlogo is not None:
                    pad = int(10 * scale)
                    max_bw = badge_w - 2 * pad
                    max_bh = badge_h - 2 * pad
                    vh, vw = vlogo.shape[:2]
                    aspect = vw / float(vh)
                    if aspect > (max_bw / max_bh):
                        target_bw = max_bw
                        target_bh = int(target_bw / aspect)
                    else:
                        target_bh = max_bh
                        target_bw = int(target_bh * aspect)

                    vlogo_resized = cv2.resize(vlogo, (target_bw, target_bh), interpolation=cv2.INTER_AREA)

                    # Center within white badge
                    offset_x = badge_x + pad + (max_bw - target_bw) // 2
                    offset_y = badge_y + pad + (max_bh - target_bh) // 2

                    if vlogo_resized.shape[2] == 4:
                        alpha = vlogo_resized[:, :, 3:4].astype(np.float32) / 255.0
                        bgr = vlogo_resized[:, :, :3]
                        roi = img[offset_y:offset_y+target_bh, offset_x:offset_x+target_bw].astype(np.float32)
                        comp = roi * (1.0 - alpha) + bgr * alpha
                        img[offset_y:offset_y+target_bh, offset_x:offset_x+target_bw] = np.clip(comp, 0, 255).astype(np.uint8)
                    else:
                        img[offset_y:offset_y+target_bh, offset_x:offset_x+target_bw] = vlogo_resized[:, :, :3]
                    logo_rendered = True
            except Exception:
                logo_rendered = False

        if not logo_rendered:
            # Render clean professional vendor logo typography
            txt = (config.studio or "Vendor Logo")
            t_size = cv2.getTextSize(txt, cv2.FONT_HERSHEY_DUPLEX, 0.82 * scale, max(1, int(1.5 * scale)))[0]
            tx = badge_x + (badge_w - t_size[0]) // 2
            ty = badge_y + (badge_h + t_size[1]) // 2
            cv2.putText(img, txt, (tx, ty), cv2.FONT_HERSHEY_DUPLEX, 0.82 * scale, (30, 30, 30), max(1, int(1.5 * scale)), lineType=cv2.LINE_AA)

        # Convert from OpenCV BGR to RGB for VFXPlayer image pipelines
        return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
