from __future__ import annotations

import os
import re
import json
import mimetypes
import uuid
import tempfile
import hashlib
import urllib.request
import urllib.parse
import urllib.error
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple


class LoginResult(dict):
    """Result of login, acting as both a dictionary and string token for backwards compatibility."""
    def __str__(self):
        return self.get("access_token") or self.get("token") or ""

    def __eq__(self, other):
        if isinstance(other, str):
            return str(self) == other
        return super().__eq__(other)

    def __hash__(self):
        return hash(str(self))


class KitsuService:
    """Zero-dependency Kitsu / Zou REST API client and VFX shot context parser."""

    def __init__(self, host_url: str = "http://localhost:8080", auth_token: Optional[str] = None):
        self.host_url = host_url.rstrip("/") if host_url else "http://localhost:8080"
        self.auth_token = auth_token

    def is_authenticated(self) -> bool:
        return bool(self.auth_token)

    @staticmethod
    def parse_shot_context(path_str: str) -> Dict[str, str]:
        """Parse standard VFX naming conventions into project, sequence, shot, task, version."""
        p = Path(path_str)
        filename = p.stem

        result: Dict[str, str] = {
            "show": "",
            "project": "",
            "sequence": "",
            "shot": "",
            "task": "",
            "version": "",
        }

        # Check full path parts for standard show/sequences/shots hierarchy
        parts_all = list(p.parts)
        for i, part in enumerate(parts_all):
            lower_part = part.lower()
            if lower_part in ("shows", "projects", "jobs") and i + 1 < len(parts_all):
                result["show"] = parts_all[i + 1]
                result["project"] = parts_all[i + 1]
            elif lower_part in ("sequences", "seq", "scenes") and i + 1 < len(parts_all):
                result["sequence"] = parts_all[i + 1]
            elif lower_part in ("shots", "shot") and i + 1 < len(parts_all):
                nxt = parts_all[i + 1]
                if re.match(r'^(sq|seq)\d+', nxt, re.IGNORECASE):
                    result["sequence"] = nxt
                    if i + 2 < len(parts_all):
                        result["shot"] = parts_all[i + 2]
                else:
                    result["shot"] = nxt

        # Extract tokens from filename (filename has highest precedence for shot/version)
        tokens = re.split(r'[_.-]', filename)
        for t in tokens:
            if re.match(r'^[vV]\d+$', t):
                result["version"] = t
            elif re.match(r'^(sq|seq)\d+', t, re.IGNORECASE):
                result["sequence"] = t
            elif re.match(r'^(sh|shot)\d+', t, re.IGNORECASE):
                result["shot"] = t
            elif t.lower() in ('comp', 'lighting', 'anim', 'fx', 'roto', 'paint', 'layout', 'matchmove', 'cleanup'):
                result["task"] = t

        # If project/sequence/shot still missing, extract from path tokens
        if not result["shot"]:
            for parent in reversed(p.parents):
                if re.match(r'^(sh|shot)\d+', parent.name, re.IGNORECASE):
                    result["shot"] = parent.name
                    break

        if not result["sequence"]:
            for parent in reversed(p.parents):
                if re.match(r'^(sq|seq)\d+', parent.name, re.IGNORECASE):
                    result["sequence"] = parent.name
                    break

        if not result["show"] and not result["project"]:
            for parent in p.parents:
                if parent.name.lower() in ("projects", "jobs", "shows"):
                    idx = p.parts.index(parent.name)
                    if idx + 1 < len(p.parts):
                        result["show"] = p.parts[idx + 1]
                        result["project"] = p.parts[idx + 1]
                        break

        # Fallback to filename parts
        if not result["show"] and tokens:
            result["show"] = tokens[0]
            result["project"] = tokens[0]

        return result

    def build_shot_url(self, shot_id: str, project_id: Optional[str] = None) -> str:
        """Construct direct Kitsu browser URL for a shot."""
        host = getattr(self, "host_url", "http://localhost:8080").rstrip("/")
        if not shot_id:
            return f"{host}/productions"
        if project_id:
            return f"{host}/productions/{project_id}/shots/{shot_id}"
        return f"{host}/productions/shots/{shot_id}"

    def build_task_url(self, task_id: str, project_id: Optional[str] = None) -> str:
        """Construct direct Kitsu browser URL for a specific task."""
        host = getattr(self, "host_url", "http://localhost:8080").rstrip("/")
        if not task_id:
            return f"{host}/productions"
        if project_id:
            return f"{host}/productions/{project_id}/tasks/{task_id}"
        return f"{host}/productions/tasks/{task_id}"

    # ─────────────────────────────────────────────────────────────────
    # REST API Client Methods
    # ─────────────────────────────────────────────────────────────────

    def _api_request(
        self,
        endpoint: str,
        host: Optional[str] = None,
        token: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None,
        method: str = "GET"
    ) -> Any:
        """Send JSON HTTP request to Kitsu backend."""
        host_to_use = (host or getattr(self, "host_url", "http://localhost:8080")).rstrip("/")
        token_to_use = token or getattr(self, "auth_token", None)
        url = f"{host_to_use}/api{endpoint}"

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "VFXPlayer-ReviewPlatform/1.0",
        }
        if token_to_use:
            headers["Authorization"] = f"Bearer {token_to_use}"

        req_data = json.dumps(data).encode("utf-8") if data is not None else None
        req = urllib.request.Request(url, data=req_data, headers=headers, method=method)

        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                resp_text = response.read().decode("utf-8")
                return json.loads(resp_text) if resp_text else {}
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            try:
                err_json = json.loads(err_body)
                msg = err_json.get("message", err_body)
            except Exception:
                msg = err_body
            raise RuntimeError(f"Kitsu API error ({e.code}): {msg}")
        except Exception as e:
            raise RuntimeError(f"Failed to connect to Kitsu at {host_to_use}: {e}")

    def _perform_login(self, email: str, password: str) -> Dict[str, Any]:
        payload = {"email": email, "password": password}
        res = self._api_request("/auth/login", data=payload, method="POST")
        token = res.get("access_token") or res.get("token") or ""
        self.auth_token = token
        return LoginResult({"access_token": token, "token": token, "user": res.get("user", {})})

    def login(self_or_cls, *args, **kwargs) -> Dict[str, Any]:
        """
        Authenticate user against Kitsu and store access token.
        Supports both:
          kitsu_client.login(email, password, host=None)
          KitsuService.login(host, email, password)
        """
        if isinstance(self_or_cls, str):
            # Called as KitsuService.login(host, email, password)
            inst = kitsu_client
            inst.host_url = self_or_cls.rstrip("/")
            email = args[0] if len(args) > 0 else kwargs.get("email", "")
            pwd = args[1] if len(args) > 1 else kwargs.get("password", "")
            return inst._perform_login(email, pwd)
        else:
            # Called on instance
            self = self_or_cls if isinstance(self_or_cls, KitsuService) else kitsu_client
            host = kwargs.get("host")
            if args and len(args) == 3 and isinstance(args[0], str) and args[0].startswith("http"):
                # KitsuService.login(kitsu_client, host, email, pwd)
                self.host_url = args[0].rstrip("/")
                email = args[1]
                pwd = args[2]
            else:
                email = args[0] if len(args) > 0 else kwargs.get("email", "")
                pwd = args[1] if len(args) > 1 else kwargs.get("password", "")
                if host:
                    self.host_url = host.rstrip("/")
            return self._perform_login(email, pwd)

    def get_projects(self_or_cls, *args, **kwargs) -> List[Dict[str, Any]]:
        """Fetch all production projects."""
        if isinstance(self_or_cls, str):
            inst = kitsu_client
            host = self_or_cls
            token = args[0] if len(args) > 0 else kwargs.get("token")
        else:
            inst = self_or_cls if isinstance(self_or_cls, KitsuService) else kitsu_client
            host = args[0] if len(args) > 0 else kwargs.get("host")
            token = args[1] if len(args) > 1 else kwargs.get("token")
        return inst._api_request("/data/projects", host=host, token=token, method="GET")

    def get_playlists(self_or_cls, *args, **kwargs) -> List[Dict[str, Any]]:
        """Fetch review playlists for a given project."""
        project_id = kwargs.get("project_id")
        host = kwargs.get("host")
        token = kwargs.get("token")

        if isinstance(self_or_cls, str):
            inst = kitsu_client
            host = self_or_cls
            token = args[0] if len(args) > 0 else token
            if len(args) > 1:
                project_id = args[1]
        else:
            inst = self_or_cls if isinstance(self_or_cls, KitsuService) else kitsu_client
            if args:
                if len(args) == 1:
                    project_id = args[0]
                elif len(args) >= 2:
                    if isinstance(args[0], str) and args[0].startswith("http"):
                        host = args[0]
                        token = args[1]
                        if len(args) > 2:
                            project_id = args[2]
                    else:
                        project_id = args[0]

        endpoint = f"/data/projects/{project_id}/playlists" if project_id else "/data/playlists"
        return inst._api_request(endpoint, host=host, token=token, method="GET")

    def get_playlist_shots(self_or_cls, *args, **kwargs) -> List[Dict[str, Any]]:
        """Fetch all shot entries contained within a Kitsu review playlist."""
        playlist_id = kwargs.get("playlist_id")
        host = kwargs.get("host")
        token = kwargs.get("token")

        if isinstance(self_or_cls, str):
            inst = kitsu_client
            host = self_or_cls
            token = args[0] if len(args) > 0 else token
            if len(args) > 1:
                playlist_id = args[1]
        else:
            inst = self_or_cls if isinstance(self_or_cls, KitsuService) else kitsu_client
            if args:
                if len(args) == 1:
                    playlist_id = args[0]
                elif len(args) >= 2:
                    if isinstance(args[0], str) and args[0].startswith("http"):
                        host = args[0]
                        token = args[1]
                        if len(args) > 2:
                            playlist_id = args[2]
                    else:
                        playlist_id = args[0]
                        if len(args) > 1:
                            host = args[1]
                        if len(args) > 2:
                            token = args[2]

        if not playlist_id:
            return []

        # 1. Primary standard Zou endpoint: GET /data/playlists/{playlist_id}
        # In Zou/Kitsu, this returns the playlist object containing the "shots" list
        try:
            pl_data = inst._api_request(f"/data/playlists/{playlist_id}", host=host, token=token, method="GET")
            if isinstance(pl_data, dict):
                shots = pl_data.get("shots") or pl_data.get("entities") or pl_data.get("items")
                if isinstance(shots, list):
                    resolved = []
                    for item in shots:
                        if isinstance(item, dict):
                            resolved_item = dict(item)
                            entity_id = item.get("entity_id") or item.get("id") or item.get("shot_id")
                            if entity_id:
                                resolved_item["id"] = entity_id
                                # If shot name or details missing (standard Zou playlist entries {"entity_id", "preview_file_id"})
                                if not resolved_item.get("name") or resolved_item.get("name") == "Shot":
                                    try:
                                        s_data = inst._api_request(f"/data/shots/{entity_id}", host=host, token=token, method="GET")
                                        if isinstance(s_data, dict):
                                            for k, v in s_data.items():
                                                if k not in resolved_item or not resolved_item[k]:
                                                    resolved_item[k] = v
                                    except Exception:
                                        try:
                                            e_data = inst._api_request(f"/data/entities/{entity_id}", host=host, token=token, method="GET")
                                            if isinstance(e_data, dict):
                                                for k, v in e_data.items():
                                                    if k not in resolved_item or not resolved_item[k]:
                                                        resolved_item[k] = v
                                        except Exception:
                                            pass

                                # Resolve sequence name if missing
                                seq_id = resolved_item.get("sequence_id") or resolved_item.get("parent_id")
                                if seq_id and not resolved_item.get("sequence_name"):
                                    try:
                                        seq_data = inst._api_request(f"/data/sequences/{seq_id}", host=host, token=token, method="GET")
                                        if isinstance(seq_data, dict) and seq_data.get("name"):
                                            resolved_item["sequence_name"] = seq_data.get("name")
                                    except Exception:
                                        pass

                            resolved.append(resolved_item)
                        elif isinstance(item, str):
                            # It's an ID string, attempt to resolve shot metadata
                            resolved_entry = {"id": item, "name": f"Shot {item[:6]}"}
                            try:
                                s_data = inst._api_request(f"/data/shots/{item}", host=host, token=token, method="GET")
                                if isinstance(s_data, dict):
                                    resolved_entry = s_data
                                else:
                                    e_data = inst._api_request(f"/data/entities/{item}", host=host, token=token, method="GET")
                                    if isinstance(e_data, dict):
                                        resolved_entry = e_data
                            except Exception:
                                pass
                            resolved.append(resolved_entry)
                    return resolved
            elif isinstance(pl_data, list):
                return pl_data
        except Exception:
            pass

        # 2. Fallbacks for custom server setups or alternative API endpoints
        for subpath in (f"/data/playlists/{playlist_id}/shots", f"/data/playlists/{playlist_id}/entities"):
            try:
                sub_res = inst._api_request(subpath, host=host, token=token, method="GET")
                if isinstance(sub_res, list):
                    return sub_res
                elif isinstance(sub_res, dict) and "shots" in sub_res and isinstance(sub_res["shots"], list):
                    return sub_res["shots"]
            except Exception:
                continue

        return []

    def get_task_types(self_or_cls, *args, **kwargs) -> List[Dict[str, Any]]:
        inst = self_or_cls if isinstance(self_or_cls, KitsuService) else kitsu_client
        return inst._api_request("/data/task-types", method="GET")

    def get_task_statuses(self_or_cls, *args, **kwargs) -> List[Dict[str, Any]]:
        inst = self_or_cls if isinstance(self_or_cls, KitsuService) else kitsu_client
        return inst._api_request("/data/task-status", method="GET")

    def get_shot_by_name(self_or_cls, name: str, host: Optional[str] = None, token: Optional[str] = None) -> Optional[Dict[str, Any]]:
        inst = self_or_cls if isinstance(self_or_cls, KitsuService) else kitsu_client
        shots = inst._api_request(f"/data/shots?name={urllib.parse.quote(name)}", host=host, token=token, method="GET")
        if isinstance(shots, list) and shots:
            return shots[0]
        return None

    def get_task_comments(
        self_or_cls,
        task_id: str,
        host: Optional[str] = None,
        token: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        inst = self_or_cls if isinstance(self_or_cls, KitsuService) else kitsu_client
        res = inst._api_request(f"/data/tasks/{task_id}/comments", host=host, token=token, method="GET")
        return res if isinstance(res, list) else []

    def post_task_comment(
        self_or_cls,
        task_id: str,
        comment: str,
        task_status_id: Optional[str] = None,
        host: Optional[str] = None,
        token: Optional[str] = None
    ) -> Dict[str, Any]:
        inst = self_or_cls if isinstance(self_or_cls, KitsuService) else kitsu_client
        payload: Dict[str, Any] = {"comment": comment}
        if task_status_id:
            payload["task_status_id"] = task_status_id
        return inst._api_request(f"/actions/tasks/{task_id}/comment", host=host, token=token, data=payload, method="POST")

    def upload_comment_preview(
        self_or_cls,
        comment_id: str,
        image_path: str,
        host: Optional[str] = None,
        token: Optional[str] = None
    ) -> Dict[str, Any]:
        inst = self_or_cls if isinstance(self_or_cls, KitsuService) else kitsu_client
        host_to_use = (host or getattr(inst, "host_url", "http://localhost:8080")).rstrip("/")
        token_to_use = token or getattr(inst, "auth_token", None)
        url = f"{host_to_use}/api/data/comments/{comment_id}/preview-file"

        boundary = f"----WebKitFormBoundary{uuid.uuid4().hex}"
        filename = os.path.basename(image_path)
        mime_type = mimetypes.guess_type(image_path)[0] or "image/png"

        with open(image_path, "rb") as f:
            file_bytes = f.read()

        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            f"Content-Type: {mime_type}\r\n\r\n"
        ).encode("utf-8") + file_bytes + f"\r\n--{boundary}--\r\n".encode("utf-8")

        headers = {
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Content-Length": str(len(body)),
            "Authorization": f"Bearer {token_to_use}",
            "User-Agent": "VFXPlayer-ReviewPlatform/1.0",
        }

        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=15) as response:
                resp_text = response.read().decode("utf-8")
                return json.loads(resp_text) if resp_text else {}
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Preview upload failed ({e.code}): {err_body}")
        except Exception as e:
            raise RuntimeError(f"Error uploading preview to Kitsu: {e}")

    def download_preview_file(
        self_or_cls,
        preview_file_id: Optional[str] = None,
        media_url: Optional[str] = None,
        host: Optional[str] = None,
        token: Optional[str] = None,
        dest_path: Optional[str] = None
    ) -> Optional[str]:
        """
        Download preview media from Kitsu to local cache and return local file path.
        Uses authenticated HTTP GET with Authorization Bearer header.
        Caches file so repeated requests return immediately.
        """
        inst = self_or_cls if isinstance(self_or_cls, KitsuService) else kitsu_client
        host_to_use = (host or getattr(inst, "host_url", "http://localhost:8080")).rstrip("/")
        token_to_use = token or getattr(inst, "auth_token", None)

        cache_dir = os.path.join(tempfile.gettempdir(), "vfxplayer_kitsu_cache")
        os.makedirs(cache_dir, exist_ok=True)

        if not preview_file_id and media_url:
            m = re.search(r'preview-files/([a-f0-9\-]+)', media_url, re.IGNORECASE)
            if m:
                preview_file_id = m.group(1)

        cache_key = preview_file_id or (hashlib.md5(media_url.encode()).hexdigest() if media_url else "unknown")

        # Check existing cached files (both .mp4 and .png / .jpg)
        for ext in (".mp4", ".mov", ".png", ".jpg", ".jpeg"):
            candidate = os.path.join(cache_dir, f"{cache_key}{ext}")
            if os.path.exists(candidate) and os.path.getsize(candidate) > 0:
                return candidate

        urls_to_try = []
        if media_url:
            urls_to_try.append(media_url if media_url.startswith("http") else f"{host_to_use}{media_url}")

        if preview_file_id:
            urls_to_try.extend([
                f"{host_to_use}/api/movies/originals/preview-files/{preview_file_id}.mp4",
                f"{host_to_use}/api/movies/low/preview-files/{preview_file_id}.mp4",
                f"{host_to_use}/api/movies/originals/preview-files/{preview_file_id}/download",
                f"{host_to_use}/api/pictures/originals/preview-files/{preview_file_id}.png",
                f"{host_to_use}/api/pictures/originals/preview-files/{preview_file_id}/download",
                f"{host_to_use}/api/pictures/previews/preview-files/{preview_file_id}.png",
                f"{host_to_use}/api/data/previews/{preview_file_id}/media-file",
            ])

        headers = {
            "User-Agent": "VFXPlayer-ReviewPlatform/1.0",
        }
        if token_to_use:
            headers["Authorization"] = f"Bearer {token_to_use}"

        for url in urls_to_try:
            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=30) as resp:
                    if resp.status in (200, 206):
                        ctype = resp.headers.get("Content-Type", "")
                        ext = ".mp4"
                        if "png" in ctype:
                            ext = ".png"
                        elif "jpeg" in ctype or "jpg" in ctype:
                            ext = ".jpg"
                        elif url.endswith(".png"):
                            ext = ".png"
                        elif url.endswith(".jpg") or url.endswith(".jpeg"):
                            ext = ".jpg"
                        elif url.endswith(".mov"):
                            ext = ".mov"

                        out_path = dest_path or os.path.join(cache_dir, f"{cache_key}{ext}")
                        with open(out_path, "wb") as out_f:
                            while True:
                                chunk = resp.read(65536)
                                if not chunk:
                                    break
                                out_f.write(chunk)
                        if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
                            return out_path
            except Exception:
                continue

        return None

    def download_thumbnail(
        self_or_cls,
        preview_file_id: str,
        host: Optional[str] = None,
        token: Optional[str] = None,
    ) -> Optional[str]:
        """Download preview thumbnail image from Kitsu and return local cached path."""
        if not preview_file_id:
            return None
        inst = self_or_cls if isinstance(self_or_cls, KitsuService) else kitsu_client
        host_to_use = (host or getattr(inst, "host_url", "http://localhost:8080")).rstrip("/")
        token_to_use = token or getattr(inst, "auth_token", None)

        cache_dir = os.path.join(tempfile.gettempdir(), "vfxplayer_kitsu_cache", "thumbs")
        os.makedirs(cache_dir, exist_ok=True)
        cached_file = os.path.join(cache_dir, f"{preview_file_id}.png")
        if os.path.exists(cached_file) and os.path.getsize(cached_file) > 0:
            return cached_file

        urls_to_try = [
            f"{host_to_use}/api/pictures/thumbnails/preview-files/{preview_file_id}.png",
            f"{host_to_use}/api/pictures/low/preview-files/{preview_file_id}.png",
            f"{host_to_use}/api/pictures/originals/preview-files/{preview_file_id}.png",
        ]
        headers = {"User-Agent": "VFXPlayer/1.0"}
        if token_to_use:
            headers["Authorization"] = f"Bearer {token_to_use}"

        for url in urls_to_try:
            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=10) as resp:
                    if resp.status in (200, 206):
                        with open(cached_file, "wb") as f:
                            f.write(resp.read())
                        if os.path.exists(cached_file) and os.path.getsize(cached_file) > 0:
                            return cached_file
            except Exception:
                continue
        return None

    def get_tasks_for_shot(
        self_or_cls,
        shot_id: str,
        host: Optional[str] = None,
        token: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Fetch all tasks belonging to a shot."""
        if not shot_id:
            return []
        inst = self_or_cls if isinstance(self_or_cls, KitsuService) else kitsu_client
        try:
            tasks = inst._api_request(f"/data/shots/{shot_id}/tasks", host=host, token=token, method="GET")
            if isinstance(tasks, list):
                return tasks
        except Exception:
            pass
        try:
            tasks = inst._api_request(f"/data/tasks?entity_id={shot_id}", host=host, token=token, method="GET")
            if isinstance(tasks, list):
                return tasks
        except Exception:
            pass
        return []

    def get_shot_versions_and_tasks(
        self_or_cls,
        shot_id: str,
        host: Optional[str] = None,
        token: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Fetch all tasks and version history for a shot.
        Returns list of version items across tasks (e.g. edit, comp, lighting, anim).
        """
        inst = self_or_cls if isinstance(self_or_cls, KitsuService) else kitsu_client
        tasks = inst.get_tasks_for_shot(shot_id, host=host, token=token)
        try:
            task_types_raw = inst.get_task_types(host=host, token=token)
            task_types = {t["id"]: t.get("name", "Task") for t in task_types_raw if isinstance(t, dict) and "id" in t}
        except Exception:
            task_types = {}
        try:
            task_statuses_raw = inst.get_task_statuses(host=host, token=token)
            task_statuses = {s["id"]: s.get("name", "Status") for s in task_statuses_raw if isinstance(s, dict) and "id" in s}
        except Exception:
            task_statuses = {}

        versions = []
        for task in tasks:
            t_id = task.get("id")
            t_type_name = task.get("task_type_name") or task_types.get(task.get("task_type_id"), task.get("name", "Task"))
            t_status_name = task.get("task_status_name") or task_statuses.get(task.get("task_status_id"), "")

            try:
                comments = inst.get_task_comments(t_id, host=host, token=token)
            except Exception:
                comments = []
            preview_comments = [c for c in comments if c.get("preview_file_id")]

            if preview_comments:
                for v_idx, c in enumerate(preview_comments):
                    p_id = c.get("preview_file_id")
                    author = c.get("person_name") or (c.get("person", {}).get("first_name", "") if isinstance(c.get("person"), dict) else "")
                    versions.append({
                        "task_id": t_id,
                        "task_name": t_type_name,
                        "version_num": v_idx + 1,
                        "version_label": f"{t_type_name} v{v_idx + 1:03d}" + (" (Latest)" if v_idx == len(preview_comments) - 1 else ""),
                        "preview_file_id": p_id,
                        "status": c.get("task_status_name") or t_status_name,
                        "author": author,
                        "created_at": c.get("created_at", "")[:10] if c.get("created_at") else "",
                        "comment": c.get("text", "") or c.get("comment", ""),
                    })
            elif task.get("preview_file_id"):
                versions.append({
                    "task_id": t_id,
                    "task_name": t_type_name,
                    "version_num": 1,
                    "version_label": f"{t_type_name} v001 (Current)",
                    "preview_file_id": task.get("preview_file_id"),
                    "status": t_status_name,
                    "author": "",
                    "created_at": task.get("updated_at", "")[:10] if task.get("updated_at") else "",
                    "comment": "",
                })

        return versions

    def get_cache_dir(self_or_cls) -> str:
        """Return path to local Kitsu media and thumbnail cache directory."""
        return os.path.join(tempfile.gettempdir(), "vfxplayer_kitsu_cache")

    def get_cache_size(self_or_cls) -> int:
        """Return total size in bytes of local Kitsu media cache."""
        cache_dir = os.path.join(tempfile.gettempdir(), "vfxplayer_kitsu_cache")
        if not os.path.exists(cache_dir):
            return 0
        total = 0
        for root, _, files in os.walk(cache_dir):
            for f in files:
                fp = os.path.join(root, f)
                try:
                    total += os.path.getsize(fp)
                except OSError:
                    pass
        return total

    def clear_cache(self_or_cls) -> Tuple[int, int]:
        """
        Delete all cached Kitsu media and preview thumbnails.
        Returns (files_removed, bytes_freed).
        """
        cache_dir = os.path.join(tempfile.gettempdir(), "vfxplayer_kitsu_cache")
        if not os.path.exists(cache_dir):
            return (0, 0)
        files_removed = 0
        bytes_freed = 0
        for root, dirs, files in os.walk(cache_dir, topdown=False):
            for f in files:
                fp = os.path.join(root, f)
                try:
                    sz = os.path.getsize(fp)
                    os.remove(fp)
                    files_removed += 1
                    bytes_freed += sz
                except OSError:
                    pass
            for d in dirs:
                dp = os.path.join(root, d)
                try:
                    os.rmdir(dp)
                except OSError:
                    pass
        return (files_removed, bytes_freed)


# Global default instance
kitsu_client = KitsuService()
