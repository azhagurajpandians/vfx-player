import unittest
from fractions import Fraction
from core.timeline_service import TimelineService, frame_to_timecode, timecode_to_frame, to_rational_fps
from core.player_core import scan_missing_frames, MediaInfo, PlayerCore

class TestTimelineAndDelivery(unittest.TestCase):
    def test_rational_fps(self):
        self.assertEqual(to_rational_fps(23.976), Fraction(24000, 1001))
        self.assertEqual(to_rational_fps(29.97), Fraction(30000, 1001))
        self.assertEqual(to_rational_fps(59.94), Fraction(60000, 1001))
        self.assertEqual(to_rational_fps(24), Fraction(24, 1))
        self.assertEqual(to_rational_fps(25), Fraction(25, 1))
        self.assertEqual(to_rational_fps(30), Fraction(30, 1))

    def test_smpte_non_drop_frame(self):
        self.assertEqual(frame_to_timecode(0, 24), "00:00:00:00")
        self.assertEqual(frame_to_timecode(24, 24), "00:00:01:00")
        self.assertEqual(frame_to_timecode(1440, 24), "00:01:00:00")
        self.assertEqual(frame_to_timecode(86400, 24), "01:00:00:00")
        self.assertEqual(timecode_to_frame("01:00:00:00", 24), 86400)

    def test_smpte_drop_frame_roundtrip(self):
        # SMPTE 12M drop-frame at 29.97
        for f in [0, 1, 29, 30, 1799, 1800, 1801, 3597, 3598, 17981, 17982, 107892]:
            tc = frame_to_timecode(f, 29.97, drop_frame=True)
            self.assertIn(";", tc)
            rev = timecode_to_frame(tc, 29.97, drop_frame=True)
            self.assertEqual(f, rev)

    def test_timeline_service_pts(self):
        tls = TimelineService(fps=23.976, time_base=Fraction(1, 24000))
        pts_100 = tls.frame_to_pts(100)
        self.assertEqual(pts_100, 100100)
        self.assertEqual(tls.pts_to_frame(pts_100), 100)

    def test_scan_missing_frames(self):
        paths = [
            "/renders/shot.1001.exr",
            "/renders/shot.1002.exr",
            "/renders/shot.1004.exr",
            "/renders/shot.1006.exr",
        ]
        missing, start, end = scan_missing_frames(paths)
        self.assertEqual(start, 1001)
        self.assertEqual(end, 1006)
        self.assertEqual(missing, [1003, 1005])

    def test_no_missing_frames(self):
        paths = [
            "/renders/shot.0100.exr",
            "/renders/shot.0101.exr",
            "/renders/shot.0102.exr",
        ]
        missing, start, end = scan_missing_frames(paths)
        self.assertEqual(start, 100)
        self.assertEqual(end, 102)
        self.assertEqual(missing, [])

    def test_slate_builder_resolutions(self):
        from core.slate_builder import SlateBuilder, SlateConfig
        import numpy as np

        cfg = SlateConfig(
            show="MY SHOW",
            sequence="SQ01",
            shot="SH010",
            version="v002",
            artist="Alice",
            department="Compositing",
            colorspace="ACEScg",
            frame_range="1001 - 1150"
        )
        # Test standard 1080p
        slate_1080 = SlateBuilder.create_slate(1920, 1080, cfg)
        self.assertEqual(slate_1080.shape, (1080, 1920, 3))
        self.assertEqual(slate_1080.dtype, np.uint8)

        # Test 720p
        slate_720 = SlateBuilder.create_slate(1280, 720, cfg)
        self.assertEqual(slate_720.shape, (720, 1280, 3))

        # Test 4K UHD
        slate_4k = SlateBuilder.create_slate(3840, 2160, cfg)
        self.assertEqual(slate_4k.shape, (2160, 3840, 3))

    def test_slate_config_serialization(self):
        from core.slate_builder import SlateConfig

        cfg = SlateConfig(
            show="AVATAR",
            sequence="SEQ42",
            shot="SH999",
            version="v042",
            artist="Bob",
            department="FX",
            date_str="2026-09-09",
            fps="24.0",
            colorspace="ACEScg"
        )
        d = cfg.to_dict()
        self.assertEqual(d["show"], "AVATAR")
        self.assertEqual(d["shot"], "SH999")
        self.assertEqual(d["version"], "v042")

        reconstructed = SlateConfig.from_dict(d)
        self.assertEqual(reconstructed.show, "AVATAR")
        self.assertEqual(reconstructed.artist, "Bob")
        self.assertEqual(reconstructed.colorspace, "ACEScg")

    def test_netflix_slate(self):
        from core.slate_builder import SlateBuilder, SlateConfig
        import numpy as np

        # Create dummy thumbnail (1920x1080)
        thumb = np.zeros((1080, 1920, 3), dtype=np.uint8)
        thumb[:, :, 0] = 120 # bluish test frame

        cfg = SlateConfig(
            template="netflix",
            show="Stranger Things VFX",
            submitting_for="FINAL",
            sequence="SQ101",
            shot="SH0010",
            version="v001",
            version_name="st_101_001_0010_comp_v001",
            artist="Lead Artist",
            department="Comp",
            shot_types="2d comp / cleanup",
            episode="101",
            scene="001",
            media_color="rec709 with show lut",
            shot_description="Extensive background cleanup and screen replacement.",
            scope_of_work="All comp elements and monitor graphics inserted.",
            submission_note="Ready for client sign-off.",
            studio="VFX Studio",
            fps="24.0",
            frame_range="1001 - 1080"
        )
        slate = SlateBuilder.create_slate(1920, 1080, cfg, thumbnail=thumb)
        self.assertEqual(slate.shape, (1080, 1920, 3))
        self.assertEqual(slate.dtype, np.uint8)

        # Test with transparent vendor logo RGBA
        import tempfile, cv2, os
        with tempfile.TemporaryDirectory() as tmpdir:
            logo_path = os.path.join(tmpdir, "logo.png")
            logo_img = np.zeros((100, 200, 4), dtype=np.uint8)
            logo_img[:, :, 2] = 255 # red
            logo_img[:, :, 3] = 255 # opaque alpha
            cv2.imwrite(logo_path, logo_img)

            cfg.vendor_logo_path = logo_path
            slate_with_logo = SlateBuilder.create_slate(1920, 1080, cfg, thumbnail=thumb)
            self.assertEqual(slate_with_logo.shape, (1080, 1920, 3))

    def test_netflix_burnin(self):
        from gui.export_dialog import ExportWorker
        from core.player_core import PlayerCore
        import numpy as np

        core = PlayerCore()
        worker = ExportWorker(
            core=core, output_path="dummy.mp4", start_frame=1001, end_frame=1100,
            format_preset="mp4", width=1920, height=1080, aspect_mode="fill", fps=24.0,
            apply_ocio=False, apply_grade=False,
            burnin_options={
                'enabled': True,
                'preset': 'netflix',
                'studio': 'VFX Studio',
                'show': 'Stranger Things',
                'version_name': 'st_101_001_0010_comp_v001',
                'font_scale': 0.6,
                'font_thickness': 1,
                'bg_alpha': 0.6,
                'start_frame_val': 1001,
            },
            include_audio=False
        )
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        worker._draw_burnins(frame, 1050)
        self.assertEqual(frame.shape, (1080, 1920, 3))
        self.assertTrue(np.any(frame > 0))
        core.loader.stop()

    def test_network_path_detection(self):
        from core.player_core import is_network_path
        self.assertTrue(is_network_path(r"\\server\share\render.exr"))
        self.assertTrue(is_network_path("//nas/volume/shot.mov"))
        self.assertFalse(is_network_path(r"C:\local\shot.mov"))

    def test_short_video_loop_bounds(self):
        """Verify short video (< 50 frames) cache prefetch and burst bounds."""
        import tempfile, cv2, numpy as np, os
        from core.player_core import PlayerCore

        with tempfile.TemporaryDirectory() as tmpdir:
            mp4_path = os.path.join(tmpdir, "short_30.mp4")
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            out = cv2.VideoWriter(mp4_path, fourcc, 24.0, (160, 120))
            for i in range(30):
                out.write(np.full((120, 160, 3), i * 4, dtype=np.uint8))
            out.release()

            core = PlayerCore()
            core.load(mp4_path)
            self.assertEqual(core.frame_count(), 30)

            # Prefetch from beginning
            core.burst_prefetch(0, count=48, direction=1)
            # Fetch all frames
            import time
            time.sleep(0.1)
            for i in range(30):
                f = core.get_frame(i)

            # Verify looping back to 0 does not fail or crash
            core.burst_prefetch(0, count=48, direction=1)
            time.sleep(0.05)
            f0 = core.get_frame(0)
            self.assertIsNotNone(f0)
            core.loader.stop()
            del core
            time.sleep(0.05)

if __name__ == '__main__':
    unittest.main()

