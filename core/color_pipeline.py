"""
ColorPipeline: Authoritative color transform and grading coordinator.

Ensures deterministic, 100% consistent color reproduction across:
  - VisPy GPU Viewport (GLSL)
  - Video/MOV/MP4 Exporter (FFmpeg pipeline)
  - Review frame snapshots & thumbnails
"""

import os
import math
import numpy as np
from dataclasses import dataclass, field
from typing import Tuple, Optional, Dict, Any

try:
    import OpenImageIO as oiio
except ImportError:
    oiio = None

try:
    import PyOpenColorIO as ocio
except ImportError:
    try:
        import OpenColorIO as ocio
    except ImportError:
        ocio = None


@dataclass
class ColorState:
    """Complete serializable snapshot of the color pipeline state."""
    exposure: float = 0.0
    gamma: float = 1.0
    slope: Tuple[float, float, float] = (1.0, 1.0, 1.0)
    offset: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    power: Tuple[float, float, float] = (1.0, 1.0, 1.0)
    saturation: float = 1.0
    channel_mode: str = 'RGB'      # 'RGB', 'R', 'G', 'B', 'A', 'Luma'
    alpha_mode: str = 'RGB'        # 'RGB', 'Alpha', 'Checkerboard', 'Black', 'White'
    false_color: bool = False
    ocio_enabled: bool = True
    input_cs: Optional[str] = None
    output_cs: Optional[str] = None
    ocio_config_path: Optional[str] = None


class ColorPipeline:
    """
    Authoritative Color Pipeline.
    
    Acts as the single source of truth for color grading, OCIO transformations,
    and channel/alpha isolation across both viewer display and export encoding.
    """

    def __init__(self, state: Optional[ColorState] = None):
        self.state = state or ColorState()
        self._cached_processor = None

    def snapshot(self) -> Dict[str, Any]:
        """Produce a serializable dictionary snapshot of current color parameters."""
        return {
            'exposure': float(self.state.exposure),
            'gamma': float(self.state.gamma),
            'slope': tuple(float(v) for v in self.state.slope),
            'offset': tuple(float(v) for v in self.state.offset),
            'power': tuple(float(v) for v in self.state.power),
            'saturation': float(self.state.saturation),
            'channel_mode': str(self.state.channel_mode),
            'alpha_mode': str(self.state.alpha_mode),
            'false_color': bool(self.state.false_color),
            'ocio_enabled': bool(self.state.ocio_enabled),
            'input_cs': self.state.input_cs,
            'output_cs': self.state.output_cs,
            'ocio_config_path': self.state.ocio_config_path
        }

    @classmethod
    def from_snapshot(cls, snap: Dict[str, Any]) -> 'ColorPipeline':
        """Reconstruct ColorPipeline from a serialized dictionary snapshot."""
        state = ColorState(
            exposure=float(snap.get('exposure', 0.0)),
            gamma=float(snap.get('gamma', 1.0)),
            slope=tuple(snap.get('slope', (1.0, 1.0, 1.0))),
            offset=tuple(snap.get('offset', (0.0, 0.0, 0.0))),
            power=tuple(snap.get('power', (1.0, 1.0, 1.0))),
            saturation=float(snap.get('saturation', 1.0)),
            channel_mode=snap.get('channel_mode', 'RGB'),
            alpha_mode=snap.get('alpha_mode', 'RGB'),
            false_color=bool(snap.get('false_color', False)),
            ocio_enabled=snap.get('ocio_enabled', True),
            input_cs=snap.get('input_cs'),
            output_cs=snap.get('output_cs'),
            ocio_config_path=snap.get('ocio_config_path')
        )
        return cls(state)

    def load_snapshot(self, snap: Dict[str, Any]):
        """Load state from a snapshot dictionary into this instance."""
        if not snap:
            return
        if 'exposure' in snap:
            self.state.exposure = float(snap['exposure'])
        if 'gamma' in snap:
            self.state.gamma = float(snap['gamma'])
        if 'slope' in snap:
            self.state.slope = tuple(snap['slope'])
        if 'offset' in snap:
            self.state.offset = tuple(snap['offset'])
        if 'power' in snap:
            self.state.power = tuple(snap['power'])
        if 'saturation' in snap:
            self.state.saturation = float(snap['saturation'])
        if 'channel_mode' in snap:
            self.state.channel_mode = snap['channel_mode']
        if 'alpha_mode' in snap:
            self.state.alpha_mode = snap['alpha_mode']
        if 'false_color' in snap:
            self.state.false_color = bool(snap['false_color'])
        if 'ocio_enabled' in snap:
            self.state.ocio_enabled = snap['ocio_enabled']
        if 'input_cs' in snap:
            self.state.input_cs = snap['input_cs']
        if 'output_cs' in snap:
            self.state.output_cs = snap['output_cs']
        if 'ocio_config_path' in snap:
            self.state.ocio_config_path = snap['ocio_config_path']

    def set_grade_params(
        self,
        exposure: Optional[float] = None,
        gamma: Optional[float] = None,
        slope: Optional[Tuple[float, float, float]] = None,
        offset: Optional[Tuple[float, float, float]] = None,
        power: Optional[Tuple[float, float, float]] = None,
        saturation: Optional[float] = None
    ):
        """Update ASC CDL and master grading parameters."""
        if exposure is not None:
            self.state.exposure = float(exposure)
        if gamma is not None:
            self.state.gamma = float(gamma)
        if slope is not None:
            self.state.slope = tuple(slope)
        if offset is not None:
            self.state.offset = tuple(offset)
        if power is not None:
            self.state.power = tuple(power)
        if saturation is not None:
            self.state.saturation = float(saturation)

    def set_cdl_params(
        self,
        slope: Tuple[float, float, float] = (1.0, 1.0, 1.0),
        offset: Tuple[float, float, float] = (0.0, 0.0, 0.0),
        power: Tuple[float, float, float] = (1.0, 1.0, 1.0),
        saturation: float = 1.0
    ):
        """Update ASC CDL parameters directly."""
        self.state.slope = tuple(slope)
        self.state.offset = tuple(offset)
        self.state.power = tuple(power)
        self.state.saturation = float(saturation)

    def set_ocio_params(
        self,
        enabled: bool,
        input_cs: Optional[str] = None,
        output_cs: Optional[str] = None,
        config_path: Optional[str] = None
    ):
        """Update OCIO configuration and color space mapping."""
        self.state.ocio_enabled = bool(enabled)
        if input_cs is not None:
            self.state.input_cs = input_cs
        if output_cs is not None:
            self.state.output_cs = output_cs
        if config_path is not None:
            self.state.ocio_config_path = config_path

    def set_channel_mode(self, mode: str):
        """Set channel isolation mode ('RGB', 'R', 'G', 'B', 'A', 'Luma')."""
        self.state.channel_mode = mode

    def set_alpha_mode(self, mode: str):
        """Set alpha presentation mode ('RGB', 'Alpha', 'Checkerboard', 'Black', 'White')."""
        self.state.alpha_mode = mode

    def apply_ocio(self, img_float32: np.ndarray) -> np.ndarray:
        """Apply OCIO color conversion from input_cs to output_cs."""
        if not self.state.ocio_enabled or not self.state.input_cs or not self.state.output_cs:
            return img_float32

        cfg_path = self.state.ocio_config_path or os.environ.get('OCIO', '')
        if not cfg_path or not os.path.isfile(cfg_path):
            return img_float32

        # 1. Try OpenImageIO buffer colorconvert first (fastest C++ path)
        if oiio is not None:
            try:
                h, w = img_float32.shape[:2]
                c = img_float32.shape[2] if img_float32.ndim > 2 else 1
                if not img_float32.flags['C_CONTIGUOUS']:
                    img_float32 = np.ascontiguousarray(img_float32)
                spec = oiio.ImageSpec(w, h, c, oiio.TypeFloat)
                buf = oiio.ImageBuf(spec)
                buf.set_pixels(oiio.ROI(), img_float32)

                res_buf = oiio.ImageBufAlgo.colorconvert(
                    buf, self.state.input_cs, self.state.output_cs, False, cfg_path
                )
                if not res_buf.has_error:
                    raw = res_buf.get_pixels(oiio.TypeFloat)
                    return np.array(raw, dtype=np.float32).reshape((h, w, c))
            except Exception:
                pass

        # 2. Fallback to PyOpenColorIO CPU processor
        if ocio is not None:
            try:
                if self._cached_processor is None:
                    config = ocio.Config.CreateFromFile(cfg_path)
                    self._cached_processor = config.getProcessor(self.state.input_cs, self.state.output_cs)
                cpu = self._cached_processor.getDefaultCPUProcessor()
                out = img_float32.copy()
                cpu.applyRGB(out)
                return out
            except Exception:
                pass

        return img_float32

    def apply_grading(self, img_float32: np.ndarray) -> np.ndarray:
        """
        Apply ASC CDL (Slope, Offset, Power, Saturation), Exposure, and Gamma.
        
        Mathematically matches the VisPy fragment shader:
          1. Gain = 2^exposure
          2. Slope & Offset: (rgb * slope) + offset
          3. Power: pow(max(rgb, 0), power)
          4. Saturation: luma + sat * (rgb - luma)
          5. Gamma: pow(rgb, 1/gamma)
        """
        out = img_float32.copy()

        # Split RGB and Alpha if present
        has_alpha = out.ndim > 2 and out.shape[2] >= 4
        if has_alpha:
            rgb = out[:, :, :3]
            alpha = out[:, :, 3:4]
        else:
            rgb = out[:, :, :3] if out.ndim > 2 else np.stack([out]*3, axis=-1)
            alpha = None

        # 1. Exposure (Master Gain)
        if self.state.exposure != 0.0:
            rgb *= pow(2.0, self.state.exposure)

        # 2. ASC CDL Slope & Offset
        slope = np.array(self.state.slope, dtype=np.float32)
        offset = np.array(self.state.offset, dtype=np.float32)
        rgb = (rgb * slope) + offset
        np.clip(rgb, 0.0, None, out=rgb)

        # 3. ASC CDL Power
        power = np.array(self.state.power, dtype=np.float32)
        if not np.allclose(power, [1.0, 1.0, 1.0]):
            rgb = np.power(rgb, power)

        # 4. ASC CDL Saturation
        if self.state.saturation != 1.0:
            luma = 0.2126 * rgb[:, :, 0] + 0.7152 * rgb[:, :, 1] + 0.0722 * rgb[:, :, 2]
            luma_3ch = np.stack([luma] * 3, axis=-1)
            rgb = luma_3ch + self.state.saturation * (rgb - luma_3ch)

        # 5. Gamma
        if self.state.gamma != 1.0 and abs(self.state.gamma) > 0.01:
            np.clip(rgb, 0.0, None, out=rgb)
            rgb = np.power(rgb, 1.0 / self.state.gamma)

        # 6. Channel Isolation
        ch = self.state.channel_mode
        if ch == 'R':
            rgb = np.stack([rgb[:, :, 0]] * 3, axis=-1)
        elif ch == 'G':
            rgb = np.stack([rgb[:, :, 1]] * 3, axis=-1)
        elif ch == 'B':
            rgb = np.stack([rgb[:, :, 2]] * 3, axis=-1)
        elif ch == 'A':
            if alpha is not None:
                rgb = np.stack([alpha[:, :, 0]] * 3, axis=-1)
            else:
                rgb = np.ones_like(rgb)
        elif ch == 'Luma':
            luma = 0.2126 * rgb[:, :, 0] + 0.7152 * rgb[:, :, 1] + 0.0722 * rgb[:, :, 2]
            rgb = np.stack([luma] * 3, axis=-1)

        # 7. Alpha presentation / Compositing
        if alpha is not None and self.state.alpha_mode != 'RGB':
            if self.state.alpha_mode == 'Alpha':
                rgb = np.stack([alpha[:, :, 0]] * 3, axis=-1)
            elif self.state.alpha_mode == 'Checkerboard':
                h, w = rgb.shape[:2]
                y_idx, x_idx = np.indices((h, w))
                check = ((x_idx // 16) + (y_idx // 16)) % 2
                bg = np.where(check[:, :, None] == 1, 0.28, 0.18).astype(np.float32)
                rgb = bg * (1.0 - alpha) + rgb * alpha
            elif self.state.alpha_mode == 'Black':
                rgb = rgb * alpha
            elif self.state.alpha_mode == 'White':
                rgb = (1.0 - alpha) + rgb * alpha

        # 8. False Color Exposure Heatmap
        if getattr(self.state, 'false_color', False):
            rgb = self.apply_false_color(rgb)

        np.clip(rgb, 0.0, 1.0, out=rgb)

        if has_alpha:
            return np.concatenate([rgb, alpha], axis=-1)
        return rgb

    @staticmethod
    def apply_false_color(rgb: np.ndarray) -> np.ndarray:
        """Map RGB image to 10-zone False Color exposure heatmap."""
        luma = 0.2126 * rgb[:, :, 0] + 0.7152 * rgb[:, :, 1] + 0.0722 * rgb[:, :, 2]
        out = np.zeros_like(rgb)

        # 10 zones
        # 1. Purple: Crushed blacks (< 0.02)
        m0 = luma < 0.02
        out[m0] = [0.5, 0.0, 0.5]

        # 2. Blue: Shadows (0.02 - 0.10)
        m1 = (luma >= 0.02) & (luma < 0.10)
        out[m1] = [0.0, 0.3, 1.0]

        # 3. Cyan: Low mids (0.10 - 0.25)
        m2 = (luma >= 0.10) & (luma < 0.25)
        out[m2] = [0.0, 0.8, 0.8]

        # 4. Dark Gray: Sub-mid (0.25 - 0.38)
        m3 = (luma >= 0.25) & (luma < 0.38)
        out[m3] = [0.3, 0.3, 0.3]

        # 5. Green: 18% Middle Gray (0.38 - 0.45)
        m4 = (luma >= 0.38) & (luma < 0.45)
        out[m4] = [0.1, 0.85, 0.2]

        # 6. Mid Gray (0.45 - 0.52)
        m5 = (luma >= 0.45) & (luma < 0.52)
        out[m5] = [0.5, 0.5, 0.5]

        # 7. Pink: Skin tones (0.52 - 0.58)
        m6 = (luma >= 0.52) & (luma < 0.58)
        out[m6] = [1.0, 0.55, 0.65]

        # 8. High Mids (0.58 - 0.75)
        m7 = (luma >= 0.58) & (luma < 0.75)
        out[m7] = [0.65, 0.65, 0.65]

        # 9. Yellow: High highlights (0.75 - 0.85)
        m8 = (luma >= 0.75) & (luma < 0.85)
        out[m8] = [1.0, 0.9, 0.0]

        # 10. Orange: Near clipping (0.85 - 0.98)
        m9 = (luma >= 0.85) & (luma < 0.98)
        out[m9] = [1.0, 0.5, 0.0]

        # 11. Red: Clipped highlights (>= 0.98)
        m10 = luma >= 0.98
        out[m10] = [1.0, 0.0, 0.0]

        return out.astype(np.float32)

    def process(
        self,
        img: np.ndarray,
        apply_ocio: bool = True,
        apply_grade: bool = True,
        to_uint8: bool = True
    ) -> np.ndarray:
        """
        Master processing entrypoint.
        
        Converts uint8 or float32 input through OCIO, ASC CDL, channel, and alpha modes,
        returning deterministic display or encode output.
        """
        if img is None:
            return None

        # Ensure float32 representation for math
        if img.dtype == np.uint8:
            out = img.astype(np.float32) * (1.0 / 255.0)
        elif img.dtype != np.float32:
            out = img.astype(np.float32)
        else:
            out = img.copy()

        # 1. Apply OCIO color conversion (typically on raw linear/EXR data)
        if apply_ocio:
            out = self.apply_ocio(out)

        # 2. Apply ASC CDL, exposure, gamma, channel, alpha
        if apply_grade:
            out = self.apply_grading(out)

        if to_uint8:
            return np.clip(out * 255.0 + 0.5, 0.0, 255.0).astype(np.uint8)

        return out

    # Convenience alias for tests and exporters
    process_image = process
