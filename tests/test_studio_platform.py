# tests/test_studio_platform.py
"""
Unit tests for Phase 5 Studio Platform:
- False color exposure scale & clipping heatmap
- Multi-shot PlaylistService sequencing & navigation
- KitsuService shot context parser & REST client URL formatting
"""

import os
import unittest
import numpy as np
import json
from unittest.mock import patch, MagicMock

from core.color_pipeline import ColorPipeline, ColorState
from core.playlist_service import PlaylistService, PlaylistItem
from core.kitsu_service import KitsuService, kitsu_client


class TestFalseColor(unittest.TestCase):
    def setUp(self):
        self.pipeline = ColorPipeline()

    def test_false_color_zones(self):
        """Verify standard 10-zone false color mapping."""
        # Zone 9: Clipped whites (luma > 0.98) -> Red (1.0, 0.0, 0.0)
        rgb_white = np.array([[[1.0, 1.0, 1.0]]], dtype=np.float32)
        fc_white = self.pipeline.apply_false_color(rgb_white)
        self.assertAlmostEqual(fc_white[0, 0, 0], 1.0, places=2)
        self.assertAlmostEqual(fc_white[0, 0, 1], 0.0, places=2)
        self.assertAlmostEqual(fc_white[0, 0, 2], 0.0, places=2)

        # Zone 8: Near clip (0.85 - 0.98) -> Orange (1.0, 0.5, 0.0)
        rgb_near_clip = np.array([[[0.9, 0.9, 0.9]]], dtype=np.float32)
        fc_near_clip = self.pipeline.apply_false_color(rgb_near_clip)
        self.assertAlmostEqual(fc_near_clip[0, 0, 0], 1.0, places=2)
        self.assertAlmostEqual(fc_near_clip[0, 0, 1], 0.5, places=2)
        self.assertAlmostEqual(fc_near_clip[0, 0, 2], 0.0, places=2)

        # Zone 4: 18% Middle Gray (0.38 - 0.45) -> Green (0.1, 0.85, 0.2)
        rgb_midgray = np.array([[[0.4, 0.4, 0.4]]], dtype=np.float32)
        fc_midgray = self.pipeline.apply_false_color(rgb_midgray)
        self.assertAlmostEqual(fc_midgray[0, 0, 0], 0.1, places=2)
        self.assertAlmostEqual(fc_midgray[0, 0, 1], 0.85, places=2)
        self.assertAlmostEqual(fc_midgray[0, 0, 2], 0.2, places=2)

        # Zone 0: Crushed blacks (< 0.02) -> Purple (0.5, 0.0, 0.5)
        rgb_black = np.array([[[0.01, 0.01, 0.01]]], dtype=np.float32)
        fc_black = self.pipeline.apply_false_color(rgb_black)
        self.assertAlmostEqual(fc_black[0, 0, 0], 0.5, places=2)
        self.assertAlmostEqual(fc_black[0, 0, 1], 0.0, places=2)
        self.assertAlmostEqual(fc_black[0, 0, 2], 0.5, places=2)

    def test_pipeline_false_color_toggle(self):
        """Verify pipeline processes image through false color when state.false_color is enabled."""
        self.pipeline.state.false_color = False
        img = np.full((10, 10, 3), 1.0, dtype=np.float32)
        out_normal = self.pipeline.process_image(img.copy(), to_uint8=False)
        # Normal image with no grading or false color stays white
        np.testing.assert_allclose(out_normal[0, 0], [1.0, 1.0, 1.0], atol=0.01)

        self.pipeline.state.false_color = True
        out_fc = self.pipeline.process_image(img.copy(), to_uint8=False)
        # Blown white in false color becomes red
        np.testing.assert_allclose(out_fc[0, 0], [1.0, 0.0, 0.0], atol=0.01)

    def test_false_color_snapshot(self):
        """Verify snapshot and load_snapshot preserves false_color boolean."""
        self.pipeline.state.false_color = True
        snap = self.pipeline.snapshot()
        self.assertTrue(snap.get("false_color"))

        pipe2 = ColorPipeline()
        self.assertFalse(pipe2.state.false_color)
        pipe2.load_snapshot(snap)
        self.assertTrue(pipe2.state.false_color)


class TestPlaylistService(unittest.TestCase):
    def setUp(self):
        self.service = PlaylistService()
        self.items = [
            PlaylistItem(media_path="/show/seq01/sh010/sh010.mov", shot_name="sh010", sequence_name="seq01", frame_count=100),
            PlaylistItem(media_path="/show/seq01/sh020/sh020.mov", shot_name="sh020", sequence_name="seq01", frame_count=120),
            PlaylistItem(media_path="/show/seq01/sh030/sh030.mov", shot_name="sh030", sequence_name="seq01", frame_count=80),
        ]
        for item in self.items:
            self.service.add_item(item)

    def test_playlist_navigation_linear(self):
        self.service.loop = False
        self.assertEqual(self.service.current_index, 0)
        self.assertEqual(self.service.current_item().shot_name, "sh010")

        # Advance to shot 2
        item = self.service.next_item()
        self.assertEqual(self.service.current_index, 1)
        self.assertEqual(item.shot_name, "sh020")

        # Advance to shot 3
        item = self.service.next_item()
        self.assertEqual(self.service.current_index, 2)
        self.assertEqual(item.shot_name, "sh030")

        # Advance beyond last shot (linear mode -> should return None and stay on last shot)
        item = self.service.next_item()
        self.assertIsNone(item)
        self.assertEqual(self.service.current_index, 2)

        # Previous back to shot 2
        item = self.service.prev_item()
        self.assertEqual(self.service.current_index, 1)
        self.assertEqual(item.shot_name, "sh020")

    def test_playlist_looping(self):
        self.service.loop = True
        self.service.set_current_index(2)

        # Next from last wraps to first
        item = self.service.next_item()
        self.assertEqual(self.service.current_index, 0)
        self.assertEqual(item.shot_name, "sh010")

        # Prev from first wraps to last
        item = self.service.prev_item()
        self.assertEqual(self.service.current_index, 2)
        self.assertEqual(item.shot_name, "sh030")

    def test_playlist_json_serialization(self):
        json_str = self.service.to_json()
        data = json.loads(json_str)
        self.assertEqual(len(data), 3)
        self.assertEqual(data[0]["shot_name"], "sh010")

        new_service = PlaylistService()
        new_service.from_json(json_str)
        self.assertEqual(len(new_service.items), 3)
        self.assertEqual(new_service.items[1].shot_name, "sh020")
        self.assertEqual(new_service.items[1].frame_count, 120)


class TestKitsuService(unittest.TestCase):
    def setUp(self):
        self.kitsu = KitsuService(host_url="http://kitsu.vfxstudio.internal")

    def test_parse_shot_context(self):
        # Linux standard VFX path
        p1 = "/mnt/projects/Avatar3/sequences/seq010/sh0020/comp/v004/Avatar3_seq010_sh0020_comp_v004.1001.exr"
        ctx1 = self.kitsu.parse_shot_context(p1)
        self.assertEqual(ctx1["show"], "Avatar3")
        self.assertEqual(ctx1["sequence"], "seq010")
        self.assertEqual(ctx1["shot"], "sh0020")
        self.assertEqual(ctx1["task"], "comp")
        self.assertEqual(ctx1["version"], "v004")

        # Windows style path
        p2 = r"D:\Shows\StarWars\shots\sq100\shot050\lighting\StarWars_shot050_v012.mov"
        ctx2 = self.kitsu.parse_shot_context(p2)
        self.assertEqual(ctx2["shot"], "shot050")
        self.assertEqual(ctx2["version"], "v012")

    def test_build_urls(self):
        url = self.kitsu.build_shot_url("shot-uuid-1234")
        self.assertEqual(url, "http://kitsu.vfxstudio.internal/productions/shots/shot-uuid-1234")

        task_url = self.kitsu.build_task_url("task-uuid-5678")
        self.assertEqual(task_url, "http://kitsu.vfxstudio.internal/productions/tasks/task-uuid-5678")

    @patch("urllib.request.urlopen")
    def test_kitsu_login(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({"access_token": "mock-token-abc"}).encode("utf-8")
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        token = self.kitsu.login("supervisor@studio.com", "secret")
        self.assertEqual(token, "mock-token-abc")
        self.assertTrue(self.kitsu.is_authenticated())
        self.assertEqual(self.kitsu.auth_token, "mock-token-abc")

    @patch("urllib.request.urlopen")
    def test_kitsu_get_playlists(self, mock_urlopen):
        self.kitsu.auth_token = "valid-token"
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps([
            {"id": "pl-1", "name": "Dailies 2026-09-09", "project_id": "proj-1"}
        ]).encode("utf-8")
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        playlists = self.kitsu.get_playlists(project_id="proj-1")
        self.assertEqual(len(playlists), 1)
        self.assertEqual(playlists[0]["name"], "Dailies 2026-09-09")

    @patch("urllib.request.urlopen")
    def test_kitsu_static_calling_resilience(self, mock_urlopen):
        """Ensure calling KitsuService.login(host, email, pwd) statically succeeds with 0 errors."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({"access_token": "token-xyz"}).encode("utf-8")
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        # Call on class directly: KitsuService.login(host, email, pwd)
        res = KitsuService.login("http://10.10.6.82", "artist@studio.com", "pass123")
        self.assertEqual(res.get("access_token"), "token-xyz")
        self.assertEqual(str(res), "token-xyz")
        self.assertTrue(kitsu_client.is_authenticated())

        # Call get_projects statically
        mock_response.read.return_value = json.dumps([{"id": "p1", "name": "Avatar"}]).encode("utf-8")
        projects = KitsuService.get_projects("http://10.10.6.82", "token-xyz")
        self.assertEqual(len(projects), 1)
        self.assertEqual(projects[0]["name"], "Avatar")

        # Call get_playlist_shots statically with (host, token, playlist_id)
        mock_response.read.return_value = json.dumps([{"id": "s1", "name": "shot010"}]).encode("utf-8")
        shots = KitsuService.get_playlist_shots("http://10.10.6.82", "token-xyz", "pl-1")
        self.assertEqual(len(shots), 1)
        self.assertEqual(shots[0]["name"], "shot010")

    @patch("urllib.request.urlopen")
    def test_kitsu_get_task_comments(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps([
            {"id": "c1", "text": "v1 note", "preview_file_id": "pf-101"},
            {"id": "c2", "text": "v2 note", "preview_file_id": "pf-102"}
        ]).encode("utf-8")
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        comments = self.kitsu.get_task_comments("task-001")
        self.assertEqual(len(comments), 2)
        self.assertEqual(comments[1]["preview_file_id"], "pf-102")

    @patch("urllib.request.urlopen")
    def test_kitsu_get_playlist_shots_zou_format(self, mock_urlopen):
        """Verify Zou/Kitsu GET /data/playlists/{id} returning a dict with shots list."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "id": "pl-100",
            "name": "Daily Review",
            "shots": [
                {"id": "sh-1", "name": "sh010", "sequence_name": "sq01", "preview_file_url": "/api/data/previews/p1.mp4"},
                {"id": "sh-2", "name": "sh020", "sequence_name": "sq01", "preview_file_id": "pf-99"}
            ]
        }).encode("utf-8")
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        shots = self.kitsu.get_playlist_shots("pl-100")
        self.assertEqual(len(shots), 2)
        self.assertEqual(shots[0]["name"], "sh010")
        self.assertEqual(shots[1]["preview_file_id"], "pf-99")

    @patch("urllib.request.urlopen")
    def test_kitsu_get_playlist_shots_entity_id_resolution(self, mock_urlopen):
        """Verify that playlist entries containing only {entity_id, preview_file_id} resolve shot names."""
        # 1st call: GET /data/playlists/pl-200 returns entity_id
        # 2nd call: GET /data/shots/sh-uuid-1 returns full metadata
        def side_effect(req, *args, **kwargs):
            url = req.full_url if hasattr(req, "full_url") else str(req)
            resp = MagicMock()
            if "/data/playlists/pl-200" in url:
                resp.read.return_value = json.dumps({
                    "id": "pl-200",
                    "shots": [{"entity_id": "sh-uuid-1", "preview_file_id": "pf-uuid-1"}]
                }).encode("utf-8")
            elif "/data/shots/sh-uuid-1" in url:
                resp.read.return_value = json.dumps({
                    "id": "sh-uuid-1",
                    "name": "sh0050",
                    "sequence_name": "seq02",
                    "task_id": "t-1"
                }).encode("utf-8")
            resp.__enter__.return_value = resp
            return resp

        mock_urlopen.side_effect = side_effect
        shots = self.kitsu.get_playlist_shots("pl-200")
        self.assertEqual(len(shots), 1)
        self.assertEqual(shots[0]["name"], "sh0050")
        self.assertEqual(shots[0]["sequence_name"], "seq02")
        self.assertEqual(shots[0]["preview_file_id"], "pf-uuid-1")

    @patch("urllib.request.urlopen")
    def test_download_preview_file(self, mock_urlopen):
        """Verify download_preview_file downloads and caches preview media."""
        resp = MagicMock()
        resp.status = 200
        resp.headers = {"Content-Type": "video/mp4"}
        resp.read.side_effect = [b"fake_mp4_bytes", b""]
        resp.__enter__.return_value = resp
        mock_urlopen.return_value = resp

        path = self.kitsu.download_preview_file(preview_file_id="test-prev-123")
        self.assertIsNotNone(path)
        self.assertTrue(path.endswith(".mp4"))
        import os
        self.assertTrue(os.path.exists(path))


class TestKitsuCredentialsPersistence(unittest.TestCase):
    def setUp(self):
        from PyQt6 import QtWidgets
        self.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def test_kitsu_dialog_credentials_load_and_save(self):
        from gui.kitsu_dialog import KitsuConnectDialog
        from PyQt6 import QtCore

        test_prefs = {
            "kitsu_host": "http://10.10.6.82",
            "kitsu_email": "raj.s@gmail.com",
            "kitsu_password": "secret_password",
            "kitsu_remember": True
        }
        dlg = KitsuConnectDialog(prefs=test_prefs)
        self.assertEqual(dlg.host_edit.text(), "http://10.10.6.82")
        self.assertEqual(dlg.email_edit.text(), "raj.s@gmail.com")
        self.assertEqual(dlg.pass_edit.text(), "secret_password")
        self.assertTrue(dlg.chk_remember.isChecked())


class TestViewportSlotIndex(unittest.TestCase):
    def test_viewport_slot_index_initialization(self):
        from gui.vispy_viewport import VispyViewport
        vp = VispyViewport(slot_index=3)
        self.assertEqual(vp.slot_index, 3)


class TestVersionCompareAndThumbnails(unittest.TestCase):
    def setUp(self):
        from PyQt6 import QtWidgets
        self.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def test_version_compare_dialog_filter_and_actions(self):
        from gui.version_dialog import VersionCompareDialog

        mock_versions = [
            {"task_name": "Edit", "version_num": 1, "version_label": "Edit v001", "media_path": "edit_v001.mov"},
            {"task_name": "Comp", "version_num": 1, "version_label": "Comp v001", "media_path": "comp_v001.mov"},
            {"task_name": "Comp", "version_num": 2, "version_label": "Comp v002 (Latest)", "media_path": "comp_v002.mov"},
            {"task_name": "Lighting", "version_num": 1, "version_label": "Lighting v001", "media_path": "light_v001.mov"},
        ]
        dlg = VersionCompareDialog(shot_name="sh0010", versions=mock_versions)
        self.assertEqual(dlg.list_widget.count(), 4)

        # Filter by Comp
        dlg.task_filter.setCurrentText("Comp")
        self.assertEqual(dlg.list_widget.count(), 2)

        # Trigger Wipe action
        triggered_action = []
        dlg.version_action_triggered.connect(lambda v, m: triggered_action.append((v, m)))
        dlg._trigger_action("wipe")
        self.assertEqual(len(triggered_action), 1)
        self.assertEqual(triggered_action[0][1], "wipe")
        self.assertEqual(triggered_action[0][0]["task_name"], "Comp")

    def test_playlist_item_widget_thumbnail_presence(self):
        from gui.playlist_widget import PlaylistItemWidget
        from core.playlist_service import PlaylistItem

        item = PlaylistItem(name="sh0020_comp_v001", shot="sh0020", sequence="sq01")
        widget = PlaylistItemWidget(item, index=0)
        self.assertTrue(hasattr(widget, "lbl_thumb"))
        self.assertEqual(widget.lbl_thumb.width(), 60)
        self.assertEqual(widget.lbl_thumb.height(), 34)

    def test_kitsu_get_shot_versions_and_tasks(self):
        from core.kitsu_service import KitsuService

        ks = KitsuService()
        mock_tasks = [
            {"id": "t1", "task_type_id": "type-edit", "name": "edit", "task_type_name": "Edit"},
            {"id": "t2", "task_type_id": "type-comp", "name": "comp", "task_type_name": "Comp"}
        ]
        mock_comments_t1 = [
            {"preview_file_id": "prev-1", "created_at": "2026-03-01T10:00:00", "person_name": "Editor", "text": "Rough cut"}
        ]
        mock_comments_t2 = [
            {"preview_file_id": "prev-2", "created_at": "2026-03-02T11:00:00", "person_name": "Compositor", "text": "First comp"},
            {"preview_file_id": "prev-3", "created_at": "2026-03-03T12:00:00", "person_name": "Compositor", "text": "Final tweaks"}
        ]

        with patch.object(ks, "get_tasks_for_shot", return_value=mock_tasks):
            with patch.object(ks, "get_task_types", return_value=[]):
                with patch.object(ks, "get_task_statuses", return_value=[]):
                    with patch.object(ks, "get_task_comments", side_effect=[mock_comments_t1, mock_comments_t2]):
                        vers = ks.get_shot_versions_and_tasks("shot-uuid-999")
                        self.assertEqual(len(vers), 3)
                        self.assertEqual(vers[0]["task_name"], "Edit")
                        self.assertEqual(vers[0]["preview_file_id"], "prev-1")
                        self.assertEqual(vers[1]["task_name"], "Comp")
                        self.assertEqual(vers[2]["task_name"], "Comp")
                        self.assertIn("Latest", vers[2]["version_label"])


    def test_kitsu_cache_management(self):
        """Test KitsuService cache size calculation and clearing."""
        from core.kitsu_service import KitsuService
        import tempfile
        ks = KitsuService()

        c_dir = ks.get_cache_dir()
        os.makedirs(c_dir, exist_ok=True)
        dummy_file = os.path.join(c_dir, "test_file.mp4")
        with open(dummy_file, "wb") as f:
            f.write(b"0" * 1024)

        self.assertGreaterEqual(ks.get_cache_size(), 1024)

        files_rem, bytes_freed = ks.clear_cache()
        self.assertGreaterEqual(files_rem, 1)
        self.assertGreaterEqual(bytes_freed, 1024)
        self.assertFalse(os.path.exists(dummy_file))

    def test_playlist_seamless_transition_methods(self):
        """Test seamless next playlist navigation and prefetch existence on MainWindow."""
        from gui.main_window import MainWindow
        self.assertTrue(hasattr(MainWindow, "_playlist_seamless_next"))
        self.assertTrue(hasattr(MainWindow, "_trigger_playlist_prefetch"))
        self.assertTrue(hasattr(MainWindow, "_on_toggle_clear_kitsu_cache_exit"))
        self.assertTrue(hasattr(MainWindow, "_on_clear_kitsu_cache_now"))


if __name__ == "__main__":
    unittest.main()

