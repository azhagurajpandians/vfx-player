from __future__ import annotations

import os
import json
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union


class AnnotationService:
    """Authoritative service for serialising, deserialising, and managing

    persistent VFX review annotations and metadata (.review.json sidecars).
    """

    CACHE_DIR = Path.home() / ".vfxplayer" / "annotations"

    @classmethod
    def get_sidecar_path(cls, media_path: str) -> Path:
        """Compute the canonical sidecar path for a given media file or sequence.

        Format: `<media_stem>.review.json` in the same directory as the media.
        """
        p = Path(media_path)
        if "%" in p.name:
            # Image sequence pattern like shot.%04d.exr -> shot.review.json
            prefix = p.name.split("%")[0].rstrip("._-")
            if not prefix:
                prefix = p.parent.name
            return p.parent / f"{prefix}.review.json"
        
        # Regular file: e.g. /path/to/shot010_v001.mov -> /path/to/shot010_v001.review.json
        stem = p.stem
        # If stem itself has dot (e.g. shot.1001), strip frame number if present
        parts = stem.split(".")
        if len(parts) > 1 and parts[-1].isdigit():
            stem = ".".join(parts[:-1])
            
        return p.parent / f"{stem}.review.json"

    @classmethod
    def get_cache_fallback_path(cls, media_path: str) -> Path:
        """Fallback path in user cache directory when media directory is read-only."""
        cls.CACHE_DIR.mkdir(parents=True, exist_ok=True)
        norm_path = os.path.normpath(os.path.abspath(media_path))
        path_hash = hashlib.sha256(norm_path.encode("utf-8")).hexdigest()[:16]
        base_name = Path(media_path).stem[:32]
        return cls.CACHE_DIR / f"{base_name}_{path_hash}.review.json"

    @classmethod
    def save_sidecar(
        cls,
        media_path: str,
        annotations: Dict[int, List[Dict[str, Any]]],
        bookmarks: Optional[Union[List[int], Set[int]]] = None,
        in_point: Optional[int] = None,
        out_point: Optional[int] = None,
        notes: Optional[Dict[str, Any]] = None,
        target_path: Optional[str] = None,
    ) -> str:
        """Save annotations and review metadata to a sidecar JSON file.

        Attempts to write alongside the media first, falling back to user cache.
        """
        payload: Dict[str, Any] = {
            "schema_version": "1.0",
            "media_path": str(media_path),
            "saved_at": datetime.now().isoformat(),
            "annotations": {str(k): v for k, v in annotations.items() if v},
            "bookmarks": sorted(list(bookmarks)) if bookmarks else [],
            "in_point": in_point,
            "out_point": out_point,
            "notes": notes or {},
        }

        save_path = Path(target_path) if target_path else cls.get_sidecar_path(media_path)
        try:
            save_path.parent.mkdir(parents=True, exist_ok=True)
            with open(save_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
            return str(save_path)
        except (OSError, PermissionError):
            # Fallback to local user cache
            fallback = cls.get_cache_fallback_path(media_path)
            with open(fallback, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
            return str(fallback)

    @classmethod
    def load_sidecar(cls, media_path: str, source_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Load annotations and review metadata from a sidecar JSON file.

        Checks explicit source_path, canonical sidecar location, and user cache.
        """
        candidate_paths: List[Path] = []
        if source_path:
            candidate_paths.append(Path(source_path))
        candidate_paths.append(cls.get_sidecar_path(media_path))
        candidate_paths.append(cls.get_cache_fallback_path(media_path))

        for path in candidate_paths:
            if path.is_file():
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    
                    # Normalise annotations dict to int keys
                    raw_annots = data.get("annotations", {})
                    normalised_annots = {int(k): v for k, v in raw_annots.items()}

                    return {
                        "path": str(path),
                        "schema_version": data.get("schema_version", "1.0"),
                        "media_path": data.get("media_path", media_path),
                        "saved_at": data.get("saved_at"),
                        "annotations": normalised_annots,
                        "bookmarks": data.get("bookmarks", []),
                        "in_point": data.get("in_point"),
                        "out_point": data.get("out_point"),
                        "notes": data.get("notes", {}),
                    }
                except Exception:
                    continue

        return None
