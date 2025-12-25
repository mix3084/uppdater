from __future__ import annotations

import json
import re
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from .utils import read_text


WORKSHOP_APP_ID = 108600


@dataclass
class ModRemoteInfo:
    workshop_id: str
    title: Optional[str]
    time_updated: Optional[int]
    result: Optional[int]


@dataclass
class ModStatus:
    workshop_id: str
    local_mtime: Optional[int]
    remote_time_updated: Optional[int]
    remote_title: Optional[str]

    @property
    def is_outdated(self) -> bool:
        if self.remote_time_updated is None:
            return False
        if self.local_mtime is None:
            return True
        return self.remote_time_updated > self.local_mtime


def parse_workshop_ids_from_ini(ini_path: Path) -> List[str]:
    if not ini_path.exists():
        raise FileNotFoundError(f"Missing ini file: {ini_path}")

    content = read_text(ini_path)
    match = re.search(r"(?im)^\s*WorkshopItems\s*=\s*(.+?)\s*$", content)
    if not match:
        return []

    raw = match.group(1).strip()
    parts = [p.strip() for p in raw.split(";") if p.strip()]
    seen = set()
    out: List[str] = []
    for part in parts:
        if part.isdigit() and part not in seen:
            seen.add(part)
            out.append(part)
    return out


def _urlencode(value: str) -> str:
    from urllib.parse import quote_plus

    return quote_plus(str(value))


def fetch_published_details(workshop_ids: List[str], timeout: int = 25) -> Dict[str, ModRemoteInfo]:
    if not workshop_ids:
        return {}

    url = "https://api.steampowered.com/ISteamRemoteStorage/GetPublishedFileDetails/v1/"
    form_pairs = [("itemcount", str(len(workshop_ids)))]
    for i, wid in enumerate(workshop_ids):
        form_pairs.append((f"publishedfileids[{i}]", wid))

    data = "&".join(
        [f"{_urlencode(k)}={_urlencode(v)}" for k, v in form_pairs]
    ).encode("utf-8")

    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded; charset=UTF-8")

    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
        payload = json.loads(raw)

    out: Dict[str, ModRemoteInfo] = {}
    items = payload.get("response", {}).get("publishedfiledetails", [])
    for item in items:
        wid = str(item.get("publishedfileid", "")).strip()
        if not wid:
            continue
        result = int(item.get("result", 0) or 0)
        if result != 1:
            out[wid] = ModRemoteInfo(
                workshop_id=wid,
                title=None,
                time_updated=None,
                result=result,
            )
            continue
        out[wid] = ModRemoteInfo(
            workshop_id=wid,
            title=item.get("title"),
            time_updated=int(item.get("time_updated") or 0) or None,
            result=result,
        )
    return out


def get_local_mod_mtime(steamapps_dir: Path, workshop_id: str) -> Optional[int]:
    base = steamapps_dir / "workshop" / "content" / str(WORKSHOP_APP_ID) / workshop_id
    mods_dir = base / "mods"
    mtimes: List[int] = []

    if mods_dir.exists():
        for mod_folder in mods_dir.iterdir():
            if not mod_folder.is_dir():
                continue
            mod_info = mod_folder / "mod.info"
            if mod_info.exists():
                mtimes.append(int(mod_info.stat().st_mtime))
            else:
                mtimes.append(int(mod_folder.stat().st_mtime))

    if mtimes:
        return max(mtimes)
    if base.exists():
        return int(base.stat().st_mtime)
    return None


def build_mod_statuses(
    ini_path: Path,
    steamapps_dir: Path,
    timeout: int,
) -> List[ModStatus]:
    workshop_ids = parse_workshop_ids_from_ini(ini_path)
    remote_map = fetch_published_details(workshop_ids, timeout=timeout)

    statuses: List[ModStatus] = []
    for wid in workshop_ids:
        remote = remote_map.get(wid)
        local_mtime = get_local_mod_mtime(steamapps_dir, wid)
        statuses.append(
            ModStatus(
                workshop_id=wid,
                local_mtime=local_mtime,
                remote_time_updated=remote.time_updated if remote else None,
                remote_title=remote.title if remote else None,
            )
        )
    return statuses
