from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

from .utils import read_text


def load_kv_file(path: Path) -> Dict[str, str]:
    data: Dict[str, str] = {}
    if not path.exists():
        return data

    for raw_line in read_text(path).splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith(";"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = value.strip()
    return data


def _as_int(value: Optional[str], default: int) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _as_float(value: Optional[str], default: float) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _resolve_path(value: str, base_dir: Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return (base_dir / path).resolve()


def _optional_path(value: Optional[str], base_dir: Path) -> Optional[Path]:
    if value is None:
        return None
    raw = value.strip()
    if not raw:
        return None
    if raw.lower() in ("none", "off", "false"):
        return None
    return _resolve_path(raw, base_dir)


@dataclass
class MonitorConfig:
    ini_path: Path
    steamapps_dir: Path
    steamcmd_path: Path
    steam_branch: str
    check_interval_sec: int
    restart_delay_sec: int
    warn_1_min_sec: int
    countdown_sec: int
    rcon_host: str
    rcon_port: int
    rcon_password: str
    rcon_timeout_sec: float
    steam_api_timeout_sec: int
    steamcmd_timeout_sec: int
    steamcmd_dump_path: Optional[Path]
    msg_restart_5min: str
    msg_restart_1min: str
    msg_countdown: str
    save_command: str
    quit_command: str
    players_command: str
    log_path: Optional[Path]


def load_config(
    config_path: Path,
    rcon_path: Optional[Path],
    overrides: Optional[Dict[str, str]] = None,
) -> MonitorConfig:
    config_path = config_path.resolve()
    base_dir = config_path.parent

    data: Dict[str, str] = {}
    if rcon_path:
        data.update(load_kv_file(rcon_path))
    data.update(load_kv_file(config_path))
    if overrides:
        data.update({k: str(v) for k, v in overrides.items() if v is not None})

    ini_path = _resolve_path(
        data.get("IniPath", r"Zomboid\Server\servertest.ini"),
        base_dir,
    )
    steamapps_dir = _resolve_path(
        data.get("SteamappsDir", r"serverfiles\steamapps"),
        base_dir,
    )
    steamcmd_path = _resolve_path(
        data.get("SteamcmdPath", r"C:\steam_server\bin\steamcmd\steamcmd.exe"),
        base_dir,
    )

    log_path = _optional_path(data.get("LogPath", "monitor.log"), base_dir)
    steamcmd_dump_path = _optional_path(
        data.get("SteamcmdDumpPath", "steamcmd_appinfo_380870.txt"),
        base_dir,
    )

    return MonitorConfig(
        ini_path=ini_path,
        steamapps_dir=steamapps_dir,
        steamcmd_path=steamcmd_path,
        steam_branch=data.get("SteamBranch", "unstable"),
        check_interval_sec=_as_int(data.get("CheckIntervalSec"), 300),
        restart_delay_sec=_as_int(data.get("RestartDelaySec"), 300),
        warn_1_min_sec=_as_int(data.get("Warn1MinSec"), 60),
        countdown_sec=_as_int(data.get("CountdownSec"), 10),
        rcon_host=data.get("RCONHost", "127.0.0.1"),
        rcon_port=_as_int(data.get("RCONPort"), 27015),
        rcon_password=data.get("RCONPassword", ""),
        rcon_timeout_sec=_as_float(data.get("RCONTimeoutSec"), 5.0),
        steam_api_timeout_sec=_as_int(data.get("SteamApiTimeoutSec"), 25),
        steamcmd_timeout_sec=_as_int(data.get("SteamcmdTimeoutSec"), 180),
        steamcmd_dump_path=steamcmd_dump_path,
        msg_restart_5min=data.get(
            "MsgRestart5Min", "Server will restart in 5 minutes."
        ),
        msg_restart_1min=data.get(
            "MsgRestart1Min", "Server will restart in 1 minute."
        ),
        msg_countdown=data.get(
            "MsgCountdown", "Restart in {seconds} seconds."
        ),
        save_command=data.get("SaveCommand", "save"),
        quit_command=data.get("QuitCommand", "quit"),
        players_command=data.get("PlayersCommand", "players"),
        log_path=log_path,
    )
