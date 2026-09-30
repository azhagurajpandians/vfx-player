import os
import sys
import unittest
import numpy as np

try:
    import OpenImageIO as oiio
except ImportError:
    oiio = None

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.player_core import PlayerCore

def create_test_exr_with_metadata(path):
    if oiio is None:
        return False
    try:
        td = oiio.BASETYPE.FLOAT
    except AttributeError:
        td = oiio.FLOAT
        
    spec = oiio.ImageSpec(100, 50, 3, td)
    spec.attribute("compression", "piz")
    spec.attribute("comment", "Testing metadata extraction")
    spec.attribute("test_int", 42)
    spec.attribute("test_float", 3.14)
    
    out = oiio.ImageOutput.create(path)
    if not out:
        return False
    out.open(path, spec)
    pixels = np.zeros((50, 100, 3), dtype=np.float32)
    out.write_image(pixels)
    out.close()
    return True

class TestMetadataExtraction(unittest.TestCase):
    def test_metadata_extraction(self):
        if oiio is None:
            self.skipTest("OpenImageIO not installed in environment")

        test_dir = os.path.join(os.path.dirname(__file__), 'test_metadata_seq')
        os.makedirs(test_dir, exist_ok=True)
        
        exr_path = os.path.join(test_dir, 'metadata_test.0001.exr')
        self.assertTrue(create_test_exr_with_metadata(exr_path), "Failed to create test EXR")

        core = PlayerCore()
        core.load(exr_path)
        
        media = core.media
        self.assertIsNotNone(media, "Error: MediaInfo not populated")
        
        self.assertEqual(media.size, (100, 50))
        self.assertEqual(media.codec, "piz")
        self.assertEqual(media.metadata.get("comment"), "Testing metadata extraction")
        self.assertEqual(media.metadata.get("test_int"), 42)

        # Cleanup
        try:
            core.loader.stop()
            import shutil
            shutil.rmtree(test_dir)
        except Exception:
            pass

if __name__ == "__main__":
    unittest.main()
