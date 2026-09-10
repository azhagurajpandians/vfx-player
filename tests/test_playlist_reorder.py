import os
import unittest
from core.playlist_service import PlaylistService, PlaylistItem


class TestPlaylistReorderAndMultiSelect(unittest.TestCase):
    def setUp(self):
        self.service = PlaylistService("Test Review Playlist")
        for i in range(5):
            self.service.add_item(PlaylistItem(
                name=f"shot_{i+1:02d}",
                media_path=f"C:/vfx/shot_{i+1:02d}.mov",
                shot=f"shot_{i+1:02d}"
            ))

    def test_initial_state(self):
        self.assertEqual(self.service.count(), 5)
        self.assertEqual(self.service.active_index, 0)
        self.assertEqual(self.service.get_item(0).shot, "shot_01")
        self.assertEqual(self.service.get_item(4).shot, "shot_05")

    def test_remove_indices(self):
        # Remove shots at indices 1 and 3 (shot_02 and shot_04)
        removed = self.service.remove_indices([1, 3])
        self.assertEqual(len(removed), 2)
        self.assertEqual(self.service.count(), 3)
        remaining_shots = [item.shot for item in self.service.items]
        self.assertEqual(remaining_shots, ["shot_01", "shot_03", "shot_05"])

    def test_remove_indices_out_of_order_and_duplicates(self):
        # Removing with duplicate and out-of-order indices
        removed = self.service.remove_indices([4, 0, 4, 2])
        self.assertEqual(len(removed), 3)
        self.assertEqual(self.service.count(), 2)
        remaining_shots = [item.shot for item in self.service.items]
        self.assertEqual(remaining_shots, ["shot_02", "shot_04"])

    def test_move_item_forward(self):
        # Move shot_01 (index 0) to index 2
        success = self.service.move_item(0, 2)
        self.assertTrue(success)
        remaining_shots = [item.shot for item in self.service.items]
        self.assertEqual(remaining_shots, ["shot_02", "shot_03", "shot_01", "shot_04", "shot_05"])
        # Active index should follow shot_01 to index 2
        self.assertEqual(self.service.active_index, 2)

    def test_move_item_backward(self):
        # Move shot_04 (index 3) to index 1
        self.service.active_index = 3
        success = self.service.move_item(3, 1)
        self.assertTrue(success)
        remaining_shots = [item.shot for item in self.service.items]
        self.assertEqual(remaining_shots, ["shot_01", "shot_04", "shot_02", "shot_03", "shot_05"])
        self.assertEqual(self.service.active_index, 1)

    def test_move_item_invalid_indices(self):
        self.assertFalse(self.service.move_item(-1, 2))
        self.assertFalse(self.service.move_item(2, 99))
        self.assertTrue(self.service.move_item(2, 2))


if __name__ == '__main__':
    unittest.main()
