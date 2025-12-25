from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

from .steam_app import SERVER_APP_ID, parse_appmanifest_build_info, steamcmd_get_buildid
from .workshop import ModStatus, build_mod_statuses


@dataclass
class UpdateResult:
    mods_outdated: bool
    server_outdated: bool
    mod_statuses: List[ModStatus]
    local_buildid: Optional[str]
    remote_buildid: Optional[str]
    appmanifest_path: Path
    steamcmd_error: Optional[str]

    @property
    def any_outdated(self) -> bool:
        return self.mods_outdated or self.server_outdated


def check_updates(
    ini_path: Path,
    steamapps_dir: Path,
    steamcmd_path: Path,
    steam_branch: str,
    steam_api_timeout_sec: int,
    steamcmd_timeout_sec: int,
    steamcmd_dump_path: Optional[Path],
) -> UpdateResult:
    mod_statuses = build_mod_statuses(
        ini_path=ini_path,
        steamapps_dir=steamapps_dir,
        timeout=steam_api_timeout_sec,
    )
    mods_outdated = any(status.is_outdated for status in mod_statuses)

    appmanifest_path = steamapps_dir / f"appmanifest_{SERVER_APP_ID}.acf"
    local_buildid, _ = parse_appmanifest_build_info(appmanifest_path)
    remote_buildid, steamcmd_error = steamcmd_get_buildid(
        steamcmd_path=steamcmd_path,
        app_id=SERVER_APP_ID,
        branch=steam_branch,
        timeout=steamcmd_timeout_sec,
        dump_path=steamcmd_dump_path,
    )

    server_outdated = False
    if local_buildid and remote_buildid and local_buildid != remote_buildid:
        server_outdated = True

    return UpdateResult(
        mods_outdated=mods_outdated,
        server_outdated=server_outdated,
        mod_statuses=mod_statuses,
        local_buildid=local_buildid,
        remote_buildid=remote_buildid,
        appmanifest_path=appmanifest_path,
        steamcmd_error=steamcmd_error,
    )
