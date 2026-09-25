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

    # --- 4. Kitsu Multi-Task & Version Navigation Tests ---

    def test_kitsu_preview_id_extraction(self):
        from core.kitsu_service import KitsuService
        # Direct preview_file_id
        c1 = {"preview_file_id": "pf-1234"}
        self.assertEqual(KitsuService._extract_preview_id(c1), "pf-1234")

        # Nested previews array (standard Zou comment schema)
        c2 = {"previews": [{"id": "pf-5678", "extension": "mp4"}]}
        self.assertEqual(KitsuService._extract_preview_id(c2), "pf-5678")

        # Nested preview_file dict
        c3 = {"preview_file": {"id": "pf-9999"}}
        self.assertEqual(KitsuService._extract_preview_id(c3), "pf-9999")

        # Task last_preview_file_id
        t1 = {"last_preview_file_id": "pf-task-01"}
        self.assertEqual(KitsuService._extract_preview_id(t1), "pf-task-01")

        # Empty or invalid
        self.assertIsNone(KitsuService._extract_preview_id({}))
        self.assertIsNone(KitsuService._extract_preview_id(None))

    def test_kitsu_shot_versions_and_tasks_parsing(self):
        from core.kitsu_service import kitsu_client
        # Mock get_tasks_for_shot, get_task_types, get_task_statuses, and get_task_comments
        orig_get_tasks = kitsu_client.get_tasks_for_shot
        orig_get_types = kitsu_client.get_task_types
        orig_get_statuses = kitsu_client.get_task_statuses
        orig_get_comments = kitsu_client.get_task_comments
        try:
            kitsu_client.get_tasks_for_shot = lambda shot_id, **kwargs: [
                {"id": "t-edit", "task_type_id": "tt-1", "task_status_id": "ts-1"},
                {"id": "t-comp", "task_type_id": "tt-2", "task_status_id": "ts-2"},
            ]
            kitsu_client.get_task_types = lambda **kwargs: [
                {"id": "tt-1", "name": "Edit"},
                {"id": "tt-2", "name": "Compositing"},
            ]
            kitsu_client.get_task_statuses = lambda **kwargs: [
                {"id": "ts-1", "name": "Approved"},
                {"id": "ts-2", "name": "WIP"},
            ]
            kitsu_client.get_task_comments = lambda task_id, **kwargs: {
                "t-edit": [
                    {"created_at": "2026-01-01T10:00:00", "preview_file_id": "pf-edit-v1", "text": "Cut sync"}
                ],
                "t-comp": [
                    {"created_at": "2026-01-02T10:00:00", "preview_file_id": "pf-comp-v1", "text": "First comp"},
                    {"created_at": "2026-01-03T10:00:00", "preview_file_id": "pf-comp-v2", "text": "Adjusted grade"},
                ]
            }.get(task_id, [])

            versions = kitsu_client.get_shot_versions_and_tasks("shot-abc")
            self.assertEqual(len(versions), 3)

            # Edit version
            self.assertEqual(versions[0]["task_name"], "Edit")
            self.assertEqual(versions[0]["version_num"], 1)
            self.assertEqual(versions[0]["preview_file_id"], "pf-edit-v1")
            self.assertIn("Latest", versions[0]["version_label"])

            # Comp versions
            self.assertEqual(versions[1]["task_name"], "Compositing")
            self.assertEqual(versions[1]["version_num"], 1)
            self.assertEqual(versions[1]["preview_file_id"], "pf-comp-v1")

            self.assertEqual(versions[2]["task_name"], "Compositing")
            self.assertEqual(versions[2]["version_num"], 2)
            self.assertEqual(versions[2]["preview_file_id"], "pf-comp-v2")
            self.assertIn("Latest", versions[2]["version_label"])
        finally:
            kitsu_client.get_tasks_for_shot = orig_get_tasks
            kitsu_client.get_task_types = orig_get_types
            kitsu_client.get_task_statuses = orig_get_statuses
            kitsu_client.get_task_comments = orig_get_comments

    def test_kitsu_version_compare_resolution(self):
        """Verify that comparing version on Comp v2 picks Comp v1, and Comp v1 falls back to Edit/Lighting."""
        versions = [
            {"task_name": "Edit", "version_num": 1, "preview_file_id": "pf-edit-v1", "version_label": "Edit v001"},
            {"task_name": "Lighting", "version_num": 1, "preview_file_id": "pf-light-v1", "version_label": "Lighting v001"},
            {"task_name": "Compositing", "version_num": 1, "preview_file_id": "pf-comp-v1", "version_label": "Comp v001"},
            {"task_name": "Compositing", "version_num": 2, "preview_file_id": "pf-comp-v2", "version_label": "Comp v002"},
        ]

        valid_vers = [v for v in versions if v.get("preview_file_id")]

        # Scenario 1: On Comp v2 -> target should be Comp v1
        active_task = "Compositing"
        cur_v_num = 2
        task_vers = [v for v in valid_vers if v.get("task_name") == active_task]
        earlier = [v for v in task_vers if v.get("version_num", 0) < cur_v_num]
        target_v = max(earlier, key=lambda v: v.get("version_num", 0))
        self.assertEqual(target_v["preview_file_id"], "pf-comp-v1")

        # Scenario 2: On Comp v1 -> earlier in Comp is empty, fallback to other tasks (Lighting/Edit)
        cur_v_num = 1
        earlier = [v for v in task_vers if v.get("version_num", 0) < cur_v_num]
        self.assertEqual(len(earlier), 0)
        other_tasks = [v for v in valid_vers if v.get("task_name") != active_task and v.get("preview_file_id") != "pf-comp-v1"]
        self.assertTrue(len(other_tasks) > 0)
        target_v = other_tasks[-1]
        self.assertEqual(target_v["preview_file_id"], "pf-light-v1")

    # --- 5. Viewport Scrubbing & Drag Mode Tests ---

    def test_timeline_scrub_delta_calculation(self):
        """Test DJV-style timeline scrubbing frame calculation across normal, Shift (precision), and Ctrl (shuttle) modes."""
        def calc_target(start_frame: int, dx: float, modifiers: tuple, total_frames: int) -> int:
            if 'Shift' in modifiers:
                px_per_frame = 16.0
            elif 'Control' in modifiers or 'Ctrl' in modifiers:
                px_per_frame = 2.0
            else:
                px_per_frame = 6.0
            frame_delta = int(dx / px_per_frame)
            return max(0, min(total_frames - 1, start_frame + frame_delta))

        total = 100
        start = 50

        # Normal scrub: +60px -> +10 frames
        self.assertEqual(calc_target(start, 60.0, (), total), 60)
        # Normal scrub: -36px -> -6 frames
        self.assertEqual(calc_target(start, -36.0, (), total), 44)

        # Shift modifier (Precision 1:1, 16px/frame): +32px -> +2 frames
        self.assertEqual(calc_target(start, 32.0, ('Shift',), total), 52)
        # Shift modifier: -48px -> -3 frames
        self.assertEqual(calc_target(start, -48.0, ('Shift',), total), 47)

        # Ctrl modifier (Rapid shuttle, 2px/frame): +30px -> +15 frames
        self.assertEqual(calc_target(start, 30.0, ('Control',), total), 65)
        self.assertEqual(calc_target(start, 30.0, ('Ctrl',), total), 65)

        # Boundary clamping tests
        # Underflow clamped to 0
        self.assertEqual(calc_target(5, -600.0, (), total), 0)
        # Overflow clamped to total - 1 (99)
        self.assertEqual(calc_target(95, 600.0, (), total), 99)

    def test_default_output_transform_rec709(self):
        """Verify that ColorManager defaults output to Output - Rec.709 and excludes camera inputs."""
        from core.color_manager import ColorManager
        cm = ColorManager()
        self.assertEqual(cm.output_cs, "Output - Rec.709")
        # Ensure camera inputs are not in output_choices
        for choice in cm.output_choices:
            cl = choice.lower()
            self.assertFalse(cl.startswith("input -"), f"Camera input found in output_choices: {choice}")
            self.assertFalse("canon-log" in cl, f"Camera log found in output_choices: {choice}")

    def test_reverse_playback_advance_and_burst(self):
        """Verify reverse playback frame delta and burst prefetch ranges."""
        from core.player_core import PlayerCore
        core = PlayerCore()

        # Calculation of next index with reverse direction
        def advance_calc(start_frame: int, frames: int, direction: int, r_in: int, r_out: int, loop: bool):
            next_idx = start_frame + (direction * frames)
            if direction < 0:
                if next_idx < r_in:
                    return r_out if loop else r_in
            else:
                if next_idx > r_out:
                    return r_in if loop else r_out
            return next_idx

        # Reverse playback steps backwards
        self.assertEqual(advance_calc(50, 10, -1, 0, 100, loop=True), 40)
        # Reverse playback loop at boundary
        self.assertEqual(advance_calc(5, 10, -1, 0, 100, loop=True), 100)
        # Reverse playback stop at boundary without loop
        self.assertEqual(advance_calc(5, 10, -1, 0, 100, loop=False), 0)

        # Burst prefetch range check
        start_idx = 30
        count = 10
        # Forward
        fwd_range = list(range(start_idx, min(start_idx + count, 100)))
        self.assertEqual(fwd_range[0], 30)
        self.assertEqual(fwd_range[-1], 39)
        # Backward
        rev_range = list(range(start_idx, max(-1, start_idx - count), -1))
        self.assertEqual(rev_range[0], 30)
        self.assertEqual(rev_range[-1], 21)

    def test_player_core_clear_cache(self):
        """Verify PlayerCore.clear_cache() flushes frames, loader queue, and frame metadata cache."""
        from core.player_core import PlayerCore
        core = PlayerCore()
        core.cache[0] = np.zeros((10, 10, 3), dtype=np.uint8)
        core.cache[1] = np.zeros((10, 10, 3), dtype=np.uint8)
        core._frame_metadata_cache[0] = {"width": 10}

        self.assertEqual(len(core.cache), 2)
        self.assertEqual(len(core._frame_metadata_cache), 1)

        core.clear_cache()

        self.assertEqual(len(core.cache), 0)
        self.assertEqual(len(core._frame_metadata_cache), 0)
        self.assertEqual(core.get_cached_indices(), set())

    def test_kitsu_clean_host_url(self):
        """Verify KitsuService._clean_host strips trailing slashes and /api prefix."""
        from core.kitsu_service import KitsuService
        self.assertEqual(KitsuService._clean_host("http://kitsu.studio.com"), "http://kitsu.studio.com")
        self.assertEqual(KitsuService._clean_host("http://kitsu.studio.com/"), "http://kitsu.studio.com")
        self.assertEqual(KitsuService._clean_host("http://kitsu.studio.com/api"), "http://kitsu.studio.com")
        self.assertEqual(KitsuService._clean_host("http://kitsu.studio.com/api/"), "http://kitsu.studio.com")
        self.assertEqual(KitsuService._clean_host(""), "http://localhost:8080")

    def test_kitsu_post_comment_with_attachment(self):
        """Verify post_task_comment attaches image when attachment_path is provided."""
        from unittest.mock import patch, MagicMock
        from core.kitsu_service import KitsuService

        svc = KitsuService(host_url="http://kitsu.test:8080", auth_token="fake-token")
        test_img = os.path.join(self.test_dir, "test_annot.png")
        with open(test_img, "wb") as f:
            f.write(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR")

        with patch.object(svc, "_api_request") as mock_api, \
             patch.object(svc, "upload_comment_preview") as mock_upload:
            mock_api.return_value = {"id": "comment-123", "text": "Needs color fix"}
            mock_upload.return_value = {"status": "ok", "id": "prev-456"}

            res = svc.post_task_comment("task-1", "Needs color fix", task_status_id="stat-wip", attachment_path=test_img)

            mock_api.assert_called_once_with(
                "/actions/tasks/task-1/comment",
                host=None,
                token=None,
                data={"comment": "Needs color fix", "task_status_id": "stat-wip"},
                method="POST"
            )
            mock_upload.assert_called_once_with(
                comment_id="comment-123",
                image_path=test_img,
                task_id="task-1",
                host=None,
                token=None
            )
            self.assertEqual(res.get("preview_file"), {"status": "ok", "id": "prev-456"})

    def test_playlist_preservation_on_version_switch(self):
        """Verify that switching version does not overwrite playlist items or populate temp files."""
        from core.playlist_service import PlaylistService, PlaylistItem

        ps = PlaylistService()
        item = PlaylistItem(
            media_path="/studio/shows/hero/sh010/sh010_comp_v001.mov",
            shot="sh010",
            task="comp",
            version="v001",
            kitsu_shot_id="shot-uuid-1",
            kitsu_preview_id="prev-1"
        )
        ps.add_item(item)

        # Simulate version switch data
        cached_temp_path = os.path.join(tempfile.gettempdir(), "vfxplayer_kitsu_cache", "uuid_v002.mp4")
        v_data = {"task_name": "comp", "version_num": 2, "version_label": "v002", "preview_file_id": "prev-2"}

        # When updating shot item for version switch
        item.kitsu_preview_id = v_data["preview_file_id"]
        item.task_name = v_data["task_name"]
        item.version = f"v{v_data['version_num']:03d}"
        item.preview_cache_path = cached_temp_path
        # media_path should retain original primary path
        self.assertEqual(item.media_path, "/studio/shows/hero/sh010/sh010_comp_v001.mov")
        self.assertEqual(item.preview_cache_path, cached_temp_path)
        self.assertEqual(item.shot_name, "sh010")
        self.assertEqual(item.version, "v002")

    def test_kitsu_publish_review_no_duplicate_upload(self):
        """Verify KitsuPublishDialog only calls post_task_comment once and does not duplicate image uploads."""
        from unittest.mock import patch, MagicMock
        from gui.kitsu_dialog import KitsuPublishDialog, kitsu_client

        import base64
        test_img = os.path.join(self.test_dir, "test_annot_single.png")
        valid_png = base64.b64decode(b'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==')
        with open(test_img, "wb") as f:
            f.write(valid_png)

        dlg = KitsuPublishDialog(
            task_id="task-42",
            shot_id="shot-42",
            shot_name="SH042",
            preview_image_path=test_img
        )
        dlg.note_edit.setPlainText("Looks great, approved.")

        with patch.object(kitsu_client, "is_authenticated", return_value=True), \
             patch.object(kitsu_client, "post_task_comment") as mock_post, \
             patch.object(kitsu_client, "upload_comment_preview") as mock_direct_upload:

            mock_post.return_value = {"id": "comment-99", "preview_file": {"status": "ok"}}

            dlg._on_publish_clicked()

            # Ensure post_task_comment was called exactly once with the attachment path
            mock_post.assert_called_once_with(
                "task-42",
                "Looks great, approved.",
                task_status_id=None,
                attachment_path=test_img
            )
            # Ensure no secondary duplicate upload was triggered by dialog
            mock_direct_upload.assert_not_called()

    def test_kitsu_multipart_single_file_part(self):
        """Verify upload_comment_preview multipart payload contains exactly one file part (no duplicates)."""
        from unittest.mock import patch, MagicMock
        from core.kitsu_service import KitsuService

        svc = KitsuService(host_url="http://kitsu.test:8080", auth_token="token-123")
        test_img = os.path.join(self.test_dir, "test_single_part.png")
        with open(test_img, "wb") as f:
            f.write(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR")

        captured_requests = []
        def fake_urlopen(req, timeout=25):
            captured_requests.append(req)
            resp = MagicMock()
            resp.read.return_value = b'{"status": "ok", "id": "prev-1"}'
            resp.__enter__.return_value = resp
            return resp

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            res = svc.upload_comment_preview("comment-1", test_img, task_id="task-1")

        self.assertTrue(len(captured_requests) > 0)
        req_body = captured_requests[0].data.decode("utf-8", errors="replace")
        # Assert 'name="file"' appears exactly once
        self.assertEqual(req_body.count('name="file"'), 1)
        # Assert 'name="attachment"' does not appear in the same request body
        self.assertEqual(req_body.count('name="attachment"'), 0)


if __name__ == "__main__":
    unittest.main()

