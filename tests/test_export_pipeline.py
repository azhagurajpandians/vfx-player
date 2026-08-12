print("STARTING TEST SCRIPT")
import os
import sys
import unittest
import numpy as np
import cv2

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from main import setup_ocio_runtime
setup_ocio_runtime()

print("Importing PyQt6...")
from PyQt6 import QtWidgets
print("Initializing QApplication...")
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

try:
    print("Importing player_core...")
    from core.player_core import PlayerCore, _find_ffmpeg
    print("Importing export_dialog...")
    from gui.export_dialog import ExportWorker
    print("Imports completed successfully!")
except BaseException as e:
    import traceback
    print("IMPORT ERROR:")
    traceback.print_exc()
    sys.exit(1)

class TestExportPipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        print("setUpClass: defining test_dir...")
        cls.test_dir = os.path.join(os.path.dirname(__file__), 'test_export_seq')
        print("setUpClass: creating test_dir...")
        os.makedirs(cls.test_dir, exist_ok=True)
        
        print("setUpClass: importing OpenImageIO...")
        import OpenImageIO as oiio
        print("setUpClass: OpenImageIO imported successfully!")
        
        cls.exr_path = os.path.join(cls.test_dir, 'export_test.0001.exr')
        
        try:
            td = oiio.BASETYPE.FLOAT
        except AttributeError:
            td = oiio.FLOAT
            
        print("setUpClass: creating ImageSpec...")
        spec = oiio.ImageSpec(80, 60, 3, td)
        spec.attribute("compression", "piz")
        spec.attribute("camera", "Red V-Raptor")
        spec.attribute("lens", "50mm anamorphic")
        
        print("setUpClass: creating ImageOutput...")
        out = oiio.ImageOutput.create(cls.exr_path)
        print(f"setUpClass: ImageOutput created: {out}")
        if out:
            print("setUpClass: opening ImageOutput...")
            out.open(cls.exr_path, spec)
            print("setUpClass: writing image pixels...")
            pixels = np.zeros((60, 80, 3), dtype=np.float32)
            out.write_image(pixels)
            print("setUpClass: closing ImageOutput...")
            out.close()
            cls.exr_created = True
        else:
            cls.exr_created = False
        print("setUpClass: completed successfully!")

    @classmethod
    def tearDownClass(cls):
        import shutil
        try:
            shutil.rmtree(cls.test_dir)
        except:
            pass

    def test_timecode_calculations(self):
        """Test timecode to frames and vice versa."""
        core = PlayerCore()
        worker = ExportWorker(
            core=core, output_path="dummy.mov", start_frame=0, end_frame=10,
            format_preset="mp4", width=640, height=360, aspect_mode="fill", fps=24.0,
            apply_ocio=False, apply_grade=False, burnin_options={},
            include_audio=True
        )
        
        # 1. frames to tc
        tc1 = worker._frames_to_tc(0, 24.0)
        self.assertEqual(tc1, "00:00:00:00")
        
        tc2 = worker._frames_to_tc(24, 24.0)
        self.assertEqual(tc2, "00:00:01:00")
        
        tc3 = worker._frames_to_tc(3661 * 24 + 12, 24.0)
        self.assertEqual(tc3, "01:01:01:12")
        
        # 2. tc to frames
        f1 = worker._tc_to_frames("00:00:00:00", 24.0)
        self.assertEqual(f1, 0)
        
        f2 = worker._tc_to_frames("00:00:01:00", 24.0)
        self.assertEqual(f2, 24)
        
        f3 = worker._tc_to_frames("01:01:01:12", 24.0)
        self.assertEqual(f3, 3661 * 24 + 12)
        
        core.loader.stop()

    def test_metadata_retrieval_and_caching(self):
        """Test that get_metadata_for_frame extracts correctly and is cached."""
        if not self.exr_created:
            self.skipTest("OIIO could not write test EXR")
            
        core = PlayerCore()
        core.load(self.exr_path)
        
        # Verify metadata is loaded
        meta1 = core.get_metadata_for_frame(0)
        self.assertIn("camera", meta1)
        self.assertEqual(meta1["camera"], "Red V-Raptor")
        self.assertEqual(meta1["lens"], "50mm anamorphic")
        
        # Check cache state
        self.assertIn(0, core._frame_metadata_cache)
        
        # Modify cache entry manually and ensure it uses cached one
        core._frame_metadata_cache[0]["camera"] = "Arri Alexa"
        meta2 = core.get_metadata_for_frame(0)
        self.assertEqual(meta2["camera"], "Arri Alexa")
        
        core.loader.stop()

    def test_burnin_drawing(self):
        """Test drawing text helper overlays onto a mock frame."""
        core = PlayerCore()
        worker = ExportWorker(
            core=core, output_path="dummy.mov", start_frame=0, end_frame=1,
            format_preset="mp4", width=640, height=360, aspect_mode="fill", fps=24.0,
            apply_ocio=False, apply_grade=False, burnin_options={},
            include_audio=True
        )
        
        frame = np.zeros((360, 640, 3), dtype=np.uint8)
        
        # Test draw_text does not raise exception
        font = cv2.FONT_HERSHEY_SIMPLEX
        worker._draw_text(frame, "TEST HEADING", "top_left", font, 1.0, 2, 20, 0.4)
        worker._draw_text(frame, "CENTER", "bottom_center", font, 1.0, 2, 20, 0.4)
        
        # Make sure pixel values modified (i.e. text actually drawn)
        self.assertTrue(np.any(frame > 0))
        
        core.loader.stop()

def run_tests_manually():
    print("RUNNING TESTS MANUALLY...")
    suite = TestExportPipeline()
    try:
        print("Running setUpClass...")
        TestExportPipeline.setUpClass()
        
        print("Running test_timecode_calculations...")
        suite.test_timecode_calculations()
        print(" -> test_timecode_calculations PASSED")
        
        print("Running test_metadata_retrieval_and_caching...")
        suite.test_metadata_retrieval_and_caching()
        print(" -> test_metadata_retrieval_and_caching PASSED")
        
        print("Running test_burnin_drawing...")
        suite.test_burnin_drawing()
        print(" -> test_burnin_drawing PASSED")
        
        print("Running tearDownClass...")
        TestExportPipeline.tearDownClass()
        print("ALL TESTS PASSED MANUALLY!")
        sys.exit(0)
    except Exception as e:
        import traceback
        print("TEST RUN ERROR:")
        traceback.print_exc()
        try:
            TestExportPipeline.tearDownClass()
        except:
            pass
        sys.exit(1)

if __name__ == "__main__":
    run_tests_manually()
