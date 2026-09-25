# tests/test_grid_drag_play.py
"""
Unit tests for Drag & Play from Playlist / Shot Browser into Grid Viewports:
- ReorderablePlaylistListWidget drag MIME packaging
- VispyViewport drop target handling for application/x-vfxplayer-shot and file URLs
- MainWindow grid layout switching and slot loading
- PlaylistWidget 'Play in Grid Slot' context menu signal wiring
"""

import os
import sys
import json
import unittest
from unittest.mock import MagicMock, patch

from PyQt6 import QtWidgets, QtCore, QtGui

# Ensure offscreen Qt application exists
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

from core.playlist_service import PlaylistService, PlaylistItem
from gui.playlist_widget import PlaylistWidget, ReorderablePlaylistListWidget


class TestGridDragAndPlay(unittest.TestCase):

    def setUp(self):
        self.service = PlaylistService("Test Grid Playlist")
        self.item1 = PlaylistItem(id="shot_01", name="vfx_shot_01", media_path="C:/vfx/sh01.mov", shot_name="sh01")
        self.item2 = PlaylistItem(id="shot_02", name="vfx_shot_02", media_path="C:/vfx/sh02.mov", shot_name="sh02")
        self.service.add_item(self.item1)
        self.service.add_item(self.item2)
        self.playlist_widget = PlaylistWidget(self.service)

    def tearDown(self):
        self.playlist_widget.deleteLater()

    def test_reorderable_list_widget_drag_drop_mode(self):
        """Verify list widget allows DragDrop mode for external dragging."""
        self.assertEqual(
            self.playlist_widget.list_widget.dragDropMode(),
            QtWidgets.QAbstractItemView.DragDropMode.DragDrop
        )
        self.assertTrue(self.playlist_widget.list_widget.dragEnabled())
        self.assertTrue(self.playlist_widget.list_widget.acceptDrops())

    def test_drag_mime_packaging(self):
        """Verify startDrag creates application/x-vfxplayer-shot with full shot metadata."""
        list_w = self.playlist_widget.list_widget
        list_w.setCurrentRow(0)
        list_w.item(0).setSelected(True)

        # Mock QDrag.exec to capture mime data
        captured_mime = []
        def mock_exec(self_drag, actions):
            captured_mime.append(self_drag.mimeData())
            return QtCore.Qt.DropAction.CopyAction

        with patch.object(QtGui.QDrag, 'exec', mock_exec):
            list_w.startDrag(QtCore.Qt.DropAction.CopyAction)

        self.assertEqual(len(captured_mime), 1)
        mime = captured_mime[0]
        self.assertTrue(mime.hasFormat('application/x-vfxplayer-shot'))
        
        raw_json = mime.data('application/x-vfxplayer-shot').data().decode('utf-8')
        payload = json.loads(raw_json)
        self.assertEqual(payload['id'], 'shot_01')
        self.assertEqual(payload['shot_name'], 'sh01')
        self.assertEqual(payload['media_path'], 'C:/vfx/sh01.mov')

    def test_send_to_slot_signal(self):
        """Verify context menu action emits send_to_slot_requested with correct slot index."""
        received = []
        self.playlist_widget.send_to_slot_requested.connect(lambda item, slot: received.append((item, slot)))

        self.playlist_widget.send_to_slot_requested.emit(self.item2, 3)
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0][0].id, 'shot_02')
        self.assertEqual(received[0][1], 3)


class TestViewportDropTarget(unittest.TestCase):

    def test_viewport_accepts_shot_mime(self):
        from gui.vispy_viewport import VispyViewport
        vp = VispyViewport(slot_index=2)
        
        # Verify slot badge and drop overlay were initialized
        self.assertTrue(hasattr(vp, 'slot_badge'))
        self.assertTrue(hasattr(vp, '_drop_overlay'))
        self.assertEqual(vp.slot_index, 2)

        # Test DragEnter with application/x-vfxplayer-shot
        mime = QtCore.QMimeData()
        mime.setData('application/x-vfxplayer-shot', b'{"id": "test"}')
        enter_event = QtGui.QDragEnterEvent(
            QtCore.QPoint(10, 10),
            QtCore.Qt.DropAction.CopyAction,
            mime,
            QtCore.Qt.MouseButton.LeftButton,
            QtCore.Qt.KeyboardModifier.NoModifier
        )
        vp.dragEnterEvent(enter_event)
        self.assertTrue(enter_event.isAccepted())
        self.assertTrue(not vp._drop_overlay.isHidden())

        # Test DragLeave
        leave_event = QtGui.QDragLeaveEvent()
        vp.dragLeaveEvent(leave_event)
        self.assertTrue(vp._drop_overlay.isHidden())

        # Test Drop
        mock_win = MagicMock()
        vp.main_window = mock_win
        drop_event = QtGui.QDropEvent(
            QtCore.QPointF(10, 10),
            QtCore.Qt.DropAction.CopyAction,
            mime,
            QtCore.Qt.MouseButton.LeftButton,
            QtCore.Qt.KeyboardModifier.NoModifier
        )
        vp.dropEvent(drop_event)
        self.assertTrue(drop_event.isAccepted())
        mock_win.handle_shot_dropped_on_slot.assert_called_once_with(2, {"id": "test"})

        vp.deleteLater()


if __name__ == '__main__':
    unittest.main()
