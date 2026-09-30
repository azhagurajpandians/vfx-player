import os
import sys
import time
import unittest
import numpy as np

try:
    import OpenImageIO as oiio
except ImportError:
    oiio = None

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.player_core import PlayerCore

def create_test_exr(path):
    if oiio is None:
        return False
    try:
        td = oiio.TypeFloat
    except AttributeError:
        td = oiio.TypeDesc(oiio.FLOAT)
        
    spec = oiio.ImageSpec(100, 50, 3, td)
    out = oiio.ImageOutput.create(path)
    if not out:
        return False
    out.open(path, spec)
    pixels = np.zeros((50, 100, 3), dtype=np.float32)
    for y in range(50):
        for x in range(100):
            pixels[y, x, 0] = x / 100.0
            pixels[y, x, 1] = y / 50.0
            pixels[y, x, 2] = 0.5
    out.write_image(pixels)
    out.close()
    return True

class TestOiioCore(unittest.TestCase):
    def test_loading(self):
        if oiio is None:
            self.skipTest("OpenImageIO not installed in environment")

        test_dir = os.path.join(os.path.dirname(__file__), 'test_seq')
        os.makedirs(test_dir, exist_ok=True)
        
        seq_path = os.path.join(test_dir, 'test.0001.exr')
        self.assertTrue(create_test_exr(seq_path), "Failed to create test EXR")

        core = PlayerCore(cache_capacity=10)
        core.load(seq_path)
        
        self.assertGreater(core.frame_count(), 0, "No frames loaded")

        # Async wait
        frame = None
        for i in range(20):
            frame = core.get_frame(0)
            if frame is not None:
                break
            time.sleep(0.1)

        self.assertIsNotNone(frame, "Timeout waiting for frame 0")
        self.assertEqual(len(frame.shape), 3)

        # Cleanup
        try:
            core.loader.stop()
            import shutil
            shutil.rmtree(test_dir)
        except Exception:
            pass

if __name__ == "__main__":
    unittest.main()
