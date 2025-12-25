from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Optional, Tuple

from .utils import read_text


SERVER_APP_ID = 380870


def parse_appmanifest_build_info(appmanifest_path: Path) -> Tuple[Optional[str], Optional[int]]:
    if not appmanifest_path.exists():
        return None, None

    text = read_text(appmanifest_path)
    buildid = None
    lastupdated = None

    build_match = re.search(r'(?m)^\s*"buildid"\s*"(\d+)"\s*$', text)
    if build_match:
        buildid = build_match.group(1)

    updated_match = re.search(r'(?m)^\s*"LastUpdated"\s*"(\d+)"\s*$', text)
    if updated_match:
        lastupdated = int(updated_match.group(1))

    return buildid, lastupdated


def _extract_named_block(text: str, name: str) -> Optional[str]:
    pos = text.find(f'"{name}"')
    if pos == -1:
        return None

    start = text.find("{", pos)
    if start == -1:
        return None

    depth = 0
    for i in range(start, len(text)):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def _extract_branch_block(text: str, branch_name: str) -> Optional[str]:
    branches_block = _extract_named_block(text, "branches")
    if not branches_block:
        return None

    pos = branches_block.find(f'"{branch_name}"')
    if pos == -1:
        return None

    start = branches_block.find("{", pos)
    if start == -1:
        return None

    depth = 0
    for i in range(start, len(branches_block)):
        ch = branches_block[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return branches_block[start : i + 1]
    return None


def _parse_buildid(text: str) -> Optional[str]:
    match = re.search(r'(?im)^\s*"buildid"\s*"(\d+)"\s*$', text)
    if match:
        return match.group(1)
    return None


def steamcmd_get_buildid(
    steamcmd_path: Path,
    app_id: int,
    branch: str,
    timeout: int,
    dump_path: Optional[Path],
) -> Tuple[Optional[str], Optional[str]]:
    steamcmd_path = steamcmd_path.resolve()
    if not steamcmd_path.exists():
        return None, f"steamcmd not found: {steamcmd_path}"

    cmd = [
        str(steamcmd_path),
        "+login",
        "anonymous",
        "+app_info_update",
        "1",
        "+app_info_print",
        str(app_id),
        "+quit",
    ]

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
    except Exception as exc:
        return None, f"steamcmd failed: {exc}"

    output = (proc.stdout or "") + "\n" + (proc.stderr or "")

    if dump_path:
        try:
            dump_path.parent.mkdir(parents=True, exist_ok=True)
            dump_path.write_text(
                f"ReturnCode: {proc.returncode}\nCommand: {' '.join(cmd)}\n\n{output}",
                encoding="utf-8",
                errors="replace",
            )
        except Exception:
            pass

    branch_block = _extract_branch_block(output, branch_name=branch)
    if branch_block:
        buildid = _parse_buildid(branch_block)
        if buildid:
            return buildid, None

    buildid = _parse_buildid(output)
    if buildid:
        return buildid, None

    return None, "buildid not found in steamcmd output"
