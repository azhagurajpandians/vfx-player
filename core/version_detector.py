from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple


@dataclass
class VersionInfo:
    """Represents a single detected version of a VFX asset."""
    version_number: int
    version_string: str  # e.g. "v002"
    file_path: str
    file_name: str
    is_sequence: bool = False
    padding: int = 3


@dataclass
class VersionGroup:
    """Represents a collection of versioned media files for a shot/asset."""
    shot_name: str
    current_version: int
    current_path: str
    versions: List[VersionInfo] = field(default_factory=list)

    @property
    def version_numbers(self) -> List[int]:
        return [v.version_number for v in self.versions]

    @property
    def latest_version(self) -> Optional[VersionInfo]:
        if not self.versions:
            return None
        return self.versions[-1]

    @property
    def missing_versions(self) -> List[int]:
        """Detect missing versions in the numerical sequence."""
        if not self.versions or len(self.versions) < 2:
            return []
        nums = set(self.version_numbers)
        full_range = set(range(min(nums), max(nums) + 1))
        return sorted(list(full_range - nums))

    def get_version(self, version_number: int) -> Optional[VersionInfo]:
        for v in self.versions:
            if v.version_number == version_number:
                return v
        return None

    def get_next_version(self, current: Optional[int] = None) -> Optional[VersionInfo]:
        cur = current if current is not None else self.current_version
        higher = [v for v in self.versions if v.version_number > cur]
        return higher[0] if higher else None

    def get_prev_version(self, current: Optional[int] = None) -> Optional[VersionInfo]:
        cur = current if current is not None else self.current_version
        lower = [v for v in self.versions if v.version_number < cur]
        return lower[-1] if lower else None


class VersionDetector:
    """Parser and detector for VFX shot version naming conventions.

    Supports patterns like:
      - `shot010_comp_v001.mov`
      - `TEST_SH01_v02.mp4`
      - `seq01_sh020_lighting_v1.0100.exr`
      - `plate_v003`
    """

    # Regex matching version token: e.g. _v001, .v02, -v1
    VERSION_PATTERN = re.compile(
        r'^(?P<prefix>.*?)(?P<delimiter>[._-])[vV](?P<version>\d+)(?P<suffix>.*)$'
    )

    @classmethod
    def parse_path(cls, path_str: str) -> Optional[Tuple[str, str, int, int, str]]:
        """Parse a path into (prefix, delimiter, version_num, padding, suffix).

        Returns None if no version token is found.
        """
        p = Path(path_str)
        name = p.name

        # If it is an image sequence pattern like name.%04d.exr, parse the stem before %
        if "%" in name:
            token = name.split("%")[0].rstrip("._-")
            m = cls.VERSION_PATTERN.match(token)
            if m:
                ver_int = int(m.group("version"))
                pad = len(m.group("version"))
                ext = "".join(p.suffixes)
                return m.group("prefix"), m.group("delimiter"), ver_int, pad, ext
            return None

        # Check for sequence filename with numeric frame: e.g. shot_v001.1001.exr
        parts = p.stem.split(".")
        if len(parts) > 1 and parts[-1].isdigit():
            stem_no_frame = ".".join(parts[:-1])
            m = cls.VERSION_PATTERN.match(stem_no_frame)
            if m:
                ver_int = int(m.group("version"))
                pad = len(m.group("version"))
                # Suffix retains the frame number pattern and extension
                ext = f".*.{p.suffix.lstrip('.')}"
                return m.group("prefix"), m.group("delimiter"), ver_int, pad, ext

        m = cls.VERSION_PATTERN.match(p.stem)
        if m:
            ver_int = int(m.group("version"))
            pad = len(m.group("version"))
            suffix = m.group("suffix") + p.suffix
            return m.group("prefix"), m.group("delimiter"), ver_int, pad, suffix

        return None

    @classmethod
    def find_versions(cls, current_path: str) -> Optional[VersionGroup]:
        """Scan directory of `current_path` to find all sibling versions."""
        parsed = cls.parse_path(current_path)
        if not parsed:
            return None

        prefix, delimiter, cur_ver, padding, suffix = parsed
        cur_file = Path(current_path)
        parent_dir = cur_file.parent
        if not parent_dir.exists():
            return None

        shot_name = Path(prefix).name.rstrip("._-")
        if not shot_name:
            shot_name = parent_dir.name

        versions: List[VersionInfo] = []
        seen_versions: Dict[int, VersionInfo] = {}

        # Scan files in parent directory
        try:
            entries = list(parent_dir.iterdir())
        except OSError:
            return None

        # Regex to match siblings with same prefix and suffix
        escaped_prefix = re.escape(prefix)
        escaped_delim = re.escape(delimiter)
        escaped_suffix = re.escape(suffix.replace(".*", "") if ".*" in suffix else suffix)
        
        # Sibling pattern matches: <prefix><delim>[vV](\d+)<optional_extra>
        sibling_re = re.compile(
            rf'^{escaped_prefix}{escaped_delim}[vV](?P<ver>\d+)(?P<extra>.*)$',
            re.IGNORECASE,
        )

        for entry in entries:
            # Match entry stem
            m = sibling_re.match(entry.stem)
            if not m:
                # Also try full name in case of folders
                m = sibling_re.match(entry.name)
            if m:
                ver_num = int(m.group("ver"))
                ver_str = f"v{m.group('ver')}"
                pad = len(m.group("ver"))
                is_seq = entry.is_dir() or (entry.suffix.lower() in [".exr", ".dpx", ".png", ".jpg", ".tiff"])

                info = VersionInfo(
                    version_number=ver_num,
                    version_string=ver_str,
                    file_path=str(entry.resolve()),
                    file_name=entry.name,
                    is_sequence=is_seq,
                    padding=pad,
                )
                if ver_num not in seen_versions:
                    seen_versions[ver_num] = info

        # Sort versions by version_number
        sorted_versions = sorted(seen_versions.values(), key=lambda v: v.version_number)

        return VersionGroup(
            shot_name=shot_name,
            current_version=cur_ver,
            current_path=str(Path(current_path).resolve()),
            versions=sorted_versions,
        )
