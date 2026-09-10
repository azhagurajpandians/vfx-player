import unittest
import os
import shutil
import tempfile
from pathlib import Path
import numpy as np

from PyQt6 import QtWidgets
from core.annotation_service import AnnotationService
from core.version_detector import VersionDetector, VersionGroup, VersionInfo
from gui.scopes_dialog import ScopeCanvas

_app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


class TestReviewPlatform(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="vfx_test_review_")

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    # --- 1. AnnotationService Tests ---

    def test_sidecar_path_derivation(self):
        # Regular video file
        vid_p = "/renders/ep01/sh010_comp_v001.mov"
        sidecar = AnnotationService.get_sidecar_path(vid_p)
        self.assertEqual(sidecar.name, "sh010_comp_v001.review.json")

        # Image sequence pattern
        seq_p = "/renders/ep01/seq/sh010_lighting_v002.%04d.exr"
        sidecar_seq = AnnotationService.get_sidecar_path(seq_p)
        self.assertEqual(sidecar_seq.name, "sh010_lighting_v002.review.json")

        # File with frame number in stem
        frame_p = "/renders/ep01/seq/sh010_v03.1001.exr"
        sidecar_frame = AnnotationService.get_sidecar_path(frame_p)
        self.assertEqual(sidecar_frame.name, "sh010_v03.review.json")

    def test_sidecar_save_and_load(self):
        media_path = os.path.join(self.test_dir, "shot020_comp_v001.mov")
        with open(media_path, "w") as f:
            f.write("dummy")

        annotations = {
            10: [{"tool": "pen", "color": [1.0, 0.0, 0.0, 1.0], "width": 3, "points": [[100, 100], [120, 120]]}],
            45: [{"tool": "text", "color": [1.0, 1.0, 0.0, 1.0], "text": "Check roto edge", "points": [[200, 300]]}],
        }
        bookmarks = {10, 45, 90}
        in_point = 5
        out_point = 85
        notes = {"45": {"status": "In Progress", "priority": "High"}}

        saved_path = AnnotationService.save_sidecar(
            media_path,
            annotations,
            bookmarks=bookmarks,
            in_point=in_point,
            out_point=out_point,
            notes=notes,
        )

        self.assertTrue(os.path.isfile(saved_path))
        self.assertTrue(saved_path.endswith(".review.json"))

        # Load sidecar back
        loaded = AnnotationService.load_sidecar(media_path)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["in_point"], 5)
        self.assertEqual(loaded["out_point"], 85)
        self.assertEqual(set(loaded["bookmarks"]), {10, 45, 90})
        self.assertIn(10, loaded["annotations"])
        self.assertIn(45, loaded["annotations"])
        self.assertEqual(len(loaded["annotations"][10]), 1)
        self.assertEqual(loaded["annotations"][10][0]["tool"], "pen")

    def test_load_nonexistent_sidecar(self):
        missing = AnnotationService.load_sidecar("/path/to/completely_missing_asset.mov")
        self.assertIsNone(missing)

    # --- 2. VersionDetector Tests ---

    def test_parse_path(self):
        p1 = "/shows/vfx/shot010_comp_v003.mov"
        parsed = VersionDetector.parse_path(p1)
        self.assertIsNotNone(parsed)
        prefix, delim, ver_int, pad, ext = parsed
        self.assertTrue(prefix.endswith("shot010_comp"))
        self.assertEqual(delim, "_")
        self.assertEqual(ver_int, 3)
        self.assertEqual(pad, 3)
        self.assertEqual(ext, ".mov")

        # Different padding and casing
        p2 = "/shows/vfx/sh02-V12.mp4"
        parsed2 = VersionDetector.parse_path(p2)
        self.assertIsNotNone(parsed2)
        self.assertEqual(parsed2[2], 12)
        self.assertEqual(parsed2[3], 2)

    def test_version_group_navigation(self):
        v1 = VersionInfo(1, "v001", "/path/shot_v001.mov", "shot_v001.mov")
        v2 = VersionInfo(2, "v002", "/path/shot_v002.mov", "shot_v002.mov")
        v4 = VersionInfo(4, "v004", "/path/shot_v004.mov", "shot_v004.mov")

        group = VersionGroup(
            shot_name="shot",
            current_version=2,
            current_path="/path/shot_v002.mov",
            versions=[v1, v2, v4],
        )

        self.assertEqual(group.latest_version.version_number, 4)
        self.assertEqual(group.get_next_version(2).version_number, 4)
        self.assertEqual(group.get_prev_version(2).version_number, 1)
        self.assertIsNone(group.get_prev_version(1))
        self.assertIsNone(group.get_next_version(4))
        # Missing v003 detected
        self.assertEqual(group.missing_versions, [3])

    def test_scan_directory_versions(self):
        # Create dummy version files in test_dir
        for v in ["v001", "v002", "v003"]:
            fn = f"sq01_sh010_comp_{v}.mov"
            with open(os.path.join(self.test_dir, fn), "w") as f:
                f.write("dummy")

        cur = os.path.join(self.test_dir, "sq01_sh010_comp_v002.mov")
        group = VersionDetector.find_versions(cur)
        self.assertIsNotNone(group)
        self.assertEqual(len(group.versions), 3)
        self.assertEqual(group.current_version, 2)
        self.assertEqual(group.latest_version.version_number, 3)

    # --- 3. Scopes Calculation Tests ---

    def test_scope_canvas_histogram(self):
        canvas = ScopeCanvas()
        
        # Test empty frame
        canvas.update_frame(None)
        self.assertIsNone(canvas._hist_r)

        # Test valid RGB gradient image
        img = np.zeros((100, 100, 3), dtype=np.float32)
        img[..., 0] = np.linspace(0.0, 1.0, 100)[:, None]  # Red ramp
        img[..., 1] = 0.5                                  # Green flat
        img[..., 2] = 0.2                                  # Blue flat

        canvas.set_mode("histogram")
        canvas.update_frame(img)

        self.assertIsNotNone(canvas._hist_r)
        self.assertIsNotNone(canvas._hist_g)
        self.assertIsNotNone(canvas._hist_b)
        self.assertEqual(len(canvas._hist_r), 256)
        # Verify normalized between 0 and 1
        global_max = max(np.max(canvas._hist_r), np.max(canvas._hist_g), np.max(canvas._hist_b))
        self.assertAlmostEqual(global_max, 1.0, places=4)


if __name__ == "__main__":
    unittest.main()
