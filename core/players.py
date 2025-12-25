from __future__ import annotations

import re
from typing import Optional

from .rcon_client import RconClient


def parse_player_count(response: str) -> Optional[int]:
    if not response:
        return None

    match = re.search(r"Players connected\s*\((\d+)\)", response, re.IGNORECASE)
    if match:
        return int(match.group(1))

    lines = response.splitlines()
    listed = [line for line in lines if line.strip().startswith("-")]
    if listed:
        return len(listed)

    return None


def get_player_count(rcon: RconClient, command: str) -> Optional[int]:
    response = rcon.send_command(command)
    return parse_player_count(response)
