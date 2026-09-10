from __future__ import annotations

import os
import json
import uuid
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any


@dataclass
class PlaylistItem:
    """Represents a single media item/shot in a review playlist."""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = ""
    media_path: str = ""
    sequence: str = ""
    shot: str = ""
    task: str = ""
    version: str = ""
    fps: float = 24.0
    frame_count: int = 0
    status: str = ""
    kitsu_url: str = ""
    kitsu_project_id: Optional[str] = None
    kitsu_shot_id: Optional[str] = None
    kitsu_task_id: Optional[str] = None
    kitsu_preview_url: Optional[str] = None
    kitsu_preview_id: Optional[str] = None

    def __init__(
        self,
        media_path: str = "",
        name: str = "",
        sequence: str = "",
        sequence_name: str = "",
        shot: str = "",
        shot_name: str = "",
        task: str = "",
        task_name: str = "",
        version: str = "",
        fps: float = 24.0,
        frame_count: int = 0,
        status: str = "",
        kitsu_url: str = "",
        kitsu_project_id: Optional[str] = None,
        kitsu_shot_id: Optional[str] = None,
        kitsu_task_id: Optional[str] = None,
        kitsu_preview_url: Optional[str] = None,
        kitsu_preview_id: Optional[str] = None,
        id: Optional[str] = None,
    ):
        self.id = id or str(uuid.uuid4())[:8]
        self.media_path = media_path
        self.name = name or os.path.basename(media_path)
        self.sequence = sequence or sequence_name
        self.shot = shot or shot_name
        self.task = task or task_name
        self.version = version
        self.fps = fps
        self.frame_count = frame_count
        self.status = status
        self.kitsu_url = kitsu_url
        self.kitsu_project_id = kitsu_project_id
        self.kitsu_shot_id = kitsu_shot_id
        self.kitsu_task_id = kitsu_task_id
        self.kitsu_preview_url = kitsu_preview_url
        self.kitsu_preview_id = kitsu_preview_id

    @property
    def shot_name(self) -> str:
        return self.shot

    @shot_name.setter
    def shot_name(self, val: str):
        self.shot = val

    @property
    def sequence_name(self) -> str:
        return self.sequence

    @sequence_name.setter
    def sequence_name(self, val: str):
        self.sequence = val

    @property
    def task_name(self) -> str:
        return self.task

    @task_name.setter
    def task_name(self, val: str):
        self.task = val

    @property
    def task_id(self) -> Optional[str]:
        return self.kitsu_task_id

    @property
    def shot_id(self) -> Optional[str]:
        return self.kitsu_shot_id

    @property
    def project_id(self) -> Optional[str]:
        return self.kitsu_project_id

    @property
    def preview_id(self) -> Optional[str]:
        return self.kitsu_preview_id

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "media_path": self.media_path,
            "sequence": self.sequence,
            "shot": self.shot,
            "shot_name": self.shot,
            "sequence_name": self.sequence,
            "task": self.task,
            "task_name": self.task,
            "version": self.version,
            "fps": self.fps,
            "frame_count": self.frame_count,
            "status": self.status,
            "kitsu_url": self.kitsu_url,
            "kitsu_project_id": self.kitsu_project_id,
            "kitsu_shot_id": self.kitsu_shot_id,
            "kitsu_task_id": self.kitsu_task_id,
            "kitsu_preview_url": self.kitsu_preview_url,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> PlaylistItem:
        return cls(
            id=data.get("id", str(uuid.uuid4())[:8]),
            name=data.get("name", ""),
            media_path=data.get("media_path", ""),
            sequence=data.get("sequence") or data.get("sequence_name", ""),
            shot=data.get("shot") or data.get("shot_name", ""),
            task=data.get("task") or data.get("task_name", ""),
            version=data.get("version", ""),
            fps=float(data.get("fps", 24.0)),
            frame_count=int(data.get("frame_count", 0)),
            status=data.get("status", ""),
            kitsu_url=data.get("kitsu_url", ""),
            kitsu_project_id=data.get("kitsu_project_id"),
            kitsu_shot_id=data.get("kitsu_shot_id"),
            kitsu_task_id=data.get("kitsu_task_id"),
            kitsu_preview_url=data.get("kitsu_preview_url"),
        )


class PlaylistService:
    """Service managing multi-shot review playlists, ordering, and navigation."""

    def __init__(self, name: str = "Review Playlist"):
        self.name: str = name
        self.items: List[PlaylistItem] = []
        self.active_index: int = -1
        self.loop: bool = False

    @property
    def current_index(self) -> int:
        return self.active_index

    @current_index.setter
    def current_index(self, val: int):
        self.active_index = val

    def current_item(self) -> Optional[PlaylistItem]:
        return self.get_active()

    def get_item(self, index: int) -> Optional[PlaylistItem]:
        if 0 <= index < len(self.items):
            return self.items[index]
        return None

    def has_next(self) -> bool:
        return 0 <= self.active_index < len(self.items) - 1

    def count(self) -> int:
        return len(self.items)

    def is_empty(self) -> bool:
        return len(self.items) == 0

    def add_item(self, item: PlaylistItem) -> int:
        """Add an item to the end of the playlist. Returns its index."""
        self.items.append(item)
        if self.active_index == -1:
            self.active_index = 0
        return len(self.items) - 1

    def add_media_path(self, path: str, name: Optional[str] = None) -> PlaylistItem:
        """Convenience helper to create and add a PlaylistItem from a file path."""
        item_name = name or os.path.basename(path)
        item = PlaylistItem(
            name=item_name,
            media_path=path,
        )
        self.add_item(item)
        return item

    def remove_item(self, index: int) -> bool:
        if 0 <= index < len(self.items):
            self.items.pop(index)
            if self.active_index >= len(self.items):
                self.active_index = len(self.items) - 1
            return True
        return False

    def remove_indices(self, indices: List[int]) -> List[PlaylistItem]:
        """Remove items at multiple indices cleanly."""
        removed = []
        valid_indices = sorted(set(idx for idx in indices if 0 <= idx < len(self.items)), reverse=True)
        for idx in valid_indices:
            removed.append(self.items.pop(idx))
        if self.items:
            self.active_index = max(0, min(self.active_index, len(self.items) - 1))
        else:
            self.active_index = -1
        return removed

    def move_item(self, from_idx: int, to_idx: int) -> bool:
        """Move item from from_idx to to_idx and keep active_index synchronized."""
        if not (0 <= from_idx < len(self.items) and 0 <= to_idx < len(self.items)):
            return False
        if from_idx == to_idx:
            return True
        item = self.items.pop(from_idx)
        self.items.insert(to_idx, item)
        if self.active_index == from_idx:
            self.active_index = to_idx
        elif from_idx < self.active_index <= to_idx:
            self.active_index -= 1
        elif to_idx <= self.active_index < from_idx:
            self.active_index += 1
        return True

    def clear(self):
        self.items.clear()
        self.active_index = -1

    def get_active(self) -> Optional[PlaylistItem]:
        if 0 <= self.active_index < len(self.items):
            return self.items[self.active_index]
        return None

    def set_active_index(self, index: int) -> Optional[PlaylistItem]:
        if 0 <= index < len(self.items):
            self.active_index = index
            return self.items[self.active_index]
        return None

    def set_current_index(self, index: int) -> Optional[PlaylistItem]:
        return self.set_active_index(index)

    def next_item(self, loop: Optional[bool] = None) -> Optional[PlaylistItem]:
        if loop is None:
            loop = self.loop
        if not self.items:
            return None
        if self.active_index < len(self.items) - 1:
            self.active_index += 1
            return self.items[self.active_index]
        elif loop:
            self.active_index = 0
            return self.items[self.active_index]
        return None

    def prev_item(self, loop: Optional[bool] = None) -> Optional[PlaylistItem]:
        if loop is None:
            loop = self.loop
        if not self.items:
            return None
        if self.active_index > 0:
            self.active_index -= 1
            return self.items[self.active_index]
        elif loop:
            self.active_index = len(self.items) - 1
            return self.items[self.active_index]
        return None

    def to_json(self) -> str:
        return json.dumps([item.to_dict() for item in self.items], indent=2)

    def from_json(self, json_str: str):
        data = json.loads(json_str)
        self.items = [PlaylistItem.from_dict(item_data) for item_data in data]
        self.active_index = 0 if self.items else -1

    def save_playlist(self, file_path: str):
        data = {
            "name": self.name,
            "active_index": self.active_index,
            "loop": self.loop,
            "items": [item.to_dict() for item in self.items]
        }
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def load_playlist(self, file_path: str):
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.name = data.get("name", "Review Playlist")
        self.loop = data.get("loop", False)
        self.items = [PlaylistItem.from_dict(item_data) for item_data in data.get("items", [])]
        self.active_index = data.get("active_index", 0 if self.items else -1)
