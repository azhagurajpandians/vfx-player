import unittest
import numpy as np
from core.color_pipeline import ColorPipeline, ColorState
from core.color_manager import ColorManager

class TestColorPipeline(unittest.TestCase):
    def setUp(self):
        self.pipeline = ColorPipeline()
        # Create a test gradient image [0.0, 1.0], RGBA float32
        h, w = 16, 16
        y, x = np.mgrid[0:h, 0:w]
        r = (x / (w - 1)).astype(np.float32)
        g = (y / (h - 1)).astype(np.float32)
        b = np.full((h, w), 0.5, dtype=np.float32)
        a = (0.5 * (r + g)).astype(np.float32)
        self.test_img = np.stack([r, g, b, a], axis=-1)

    def test_exposure(self):
        self.pipeline.set_grade_params(exposure=1.0) # 1 stop up = 2x multiplier
        processed = self.pipeline.process_image(self.test_img)
        self.assertEqual(processed.dtype, np.uint8)
        # 0.5 * 2.0 = 1.0 -> 255
        mid_val = processed[8, 8, 2] # Blue channel was 0.5
        self.assertAlmostEqual(mid_val, 255, delta=3)

    def test_gamma(self):
        self.pipeline.set_grade_params(gamma=2.2)
        processed = self.pipeline.process_image(self.test_img)
        self.assertEqual(processed.dtype, np.uint8)
        # 0.5 ** (1/2.2) approx 0.7297 -> ~186 in uint8
        mid_val = processed[8, 8, 2]
        expected = int(round((0.5 ** (1.0 / 2.2)) * 255.0))
        self.assertAlmostEqual(mid_val, expected, delta=3)

    def test_cdl(self):
        # Slope = 2.0 on Red, 1.0 on G, B
        self.pipeline.set_cdl_params(
            slope=(2.0, 1.0, 1.0),
            offset=(0.0, 0.0, 0.0),
            power=(1.0, 1.0, 1.0),
            saturation=1.0
        )
        processed = self.pipeline.process_image(self.test_img)
        # Red channel was x / 15. At x = 8, r = 8/15 ~ 0.5333 * 2 = 1.0667 -> clamped to 255
        self.assertEqual(processed[8, 8, 0], 255)

    def test_channel_isolation(self):
        # R channel mode should duplicate R to all RGB channels
        self.pipeline.set_channel_mode('R')
        processed = self.pipeline.process_image(self.test_img)
        r = processed[..., 0]
        g = processed[..., 1]
        b = processed[..., 2]
        np.testing.assert_array_equal(r, g)
        np.testing.assert_array_equal(r, b)

    def test_alpha_modes(self):
        # Mode: 'Alpha' should duplicate Alpha matte to RGB
        self.pipeline.set_alpha_mode('Alpha')
        processed = self.pipeline.process_image(self.test_img)
        r = processed[..., 0]
        g = processed[..., 1]
        b = processed[..., 2]
        np.testing.assert_array_equal(r, g)
        np.testing.assert_array_equal(r, b)

        # Mode: 'Black' background composite
        self.pipeline.set_alpha_mode('Black')
        proc_black = self.pipeline.process_image(self.test_img)
        self.assertEqual(proc_black.shape, (16, 16, 4))

        # Mode: 'Checkerboard'
        self.pipeline.set_alpha_mode('Checkerboard')
        proc_chk = self.pipeline.process_image(self.test_img)
        self.assertEqual(proc_chk.shape, (16, 16, 4))

    def test_snapshot_restore(self):
        self.pipeline.set_grade_params(exposure=1.5, gamma=1.8)
        self.pipeline.set_channel_mode('G')
        self.pipeline.set_alpha_mode('Checkerboard')
        self.pipeline.set_cdl_params(
            slope=(1.1, 1.2, 1.3),
            offset=(0.01, 0.02, 0.03),
            power=(0.9, 1.0, 1.1),
            saturation=1.2
        )
        snap = self.pipeline.snapshot()
        self.assertEqual(snap['exposure'], 1.5)
        self.assertEqual(snap['gamma'], 1.8)
        self.assertEqual(snap['channel_mode'], 'G')
        self.assertEqual(snap['alpha_mode'], 'Checkerboard')
        self.assertEqual(snap['saturation'], 1.2)

        new_pipe = ColorPipeline.from_snapshot(snap)
        self.assertEqual(new_pipe.state.exposure, 1.5)
        self.assertEqual(new_pipe.state.channel_mode, 'G')
        self.assertEqual(new_pipe.state.slope, (1.1, 1.2, 1.3))

        mutated_pipe = ColorPipeline()
        mutated_pipe.load_snapshot(snap)
        self.assertEqual(mutated_pipe.state.exposure, 1.5)
        self.assertEqual(mutated_pipe.state.channel_mode, 'G')
        self.assertEqual(mutated_pipe.state.slope, (1.1, 1.2, 1.3))

    def test_set_ocio_params(self):
        self.pipeline.set_ocio_params(
            enabled=True,
            input_cs="ACEScg",
            output_cs="sRGB",
            config_path="/configs/config.ocio"
        )
        self.assertTrue(self.pipeline.state.ocio_enabled)
        self.assertEqual(self.pipeline.state.input_cs, "ACEScg")
        self.assertEqual(self.pipeline.state.output_cs, "sRGB")
        self.assertEqual(self.pipeline.state.ocio_config_path, "/configs/config.ocio")

class TestColorManagerInspection(unittest.TestCase):
    def test_get_config_info(self):
        cm = ColorManager()
        info = cm.get_config_info()
        self.assertIn("loaded", info)
        self.assertIn("config_path", info)
        self.assertIn("total_colorspaces", info)
        self.assertIn("input_colorspaces", info)
        self.assertIn("output_colorspaces", info)
        self.assertIn("ocio_enabled", info)

    def test_set_config_path_invalid(self):
        cm = ColorManager()
        res = cm.set_config_path("/non/existent/path/config.ocio")
        self.assertFalse(res)

if __name__ == '__main__':
    unittest.main()
