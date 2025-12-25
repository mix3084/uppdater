from __future__ import annotations

import argparse
import time
from pathlib import Path
from typing import Tuple

from .config import load_config
from .logger import Logger
from .players import get_player_count
from .rcon_client import RconClient, RconError
from .restart import run_restart_sequence
from .updates import check_updates
from .utils import format_ts


def _default_paths() -> Tuple[Path, Path]:
    base_dir = Path(__file__).resolve().parent.parent
    config_path = base_dir / "monitor.conf"
    rcon_path = base_dir / "config" / "rcon.conf"
    return config_path, rcon_path


def _log_update_result(cfg, result, logger: Logger) -> None:
    total_mods = len(result.mod_statuses)
    outdated_mods = [m for m in result.mod_statuses if m.is_outdated]

    if total_mods == 0:
        logger.log("No WorkshopItems found in ini.")
    else:
        logger.log(f"Workshop mods: total={total_mods} outdated={len(outdated_mods)}")

    for status in outdated_mods:
        logger.log(
            "Mod outdated "
            f"id={status.workshop_id} "
            f"local={format_ts(status.local_mtime)} "
            f"remote={format_ts(status.remote_time_updated)} "
            f"title={status.remote_title or 'n/a'}"
        )

    logger.log(
        "Server buildid "
        f"local={result.local_buildid or 'n/a'} "
        f"remote={result.remote_buildid or 'n/a'} "
        f"branch={cfg.steam_branch}"
    )
    if result.steamcmd_error:
        logger.log(f"steamcmd error: {result.steamcmd_error}")


def run_once(cfg, logger: Logger) -> None:
    logger.log("Starting update check.")
    try:
        result = check_updates(
            ini_path=cfg.ini_path,
            steamapps_dir=cfg.steamapps_dir,
            steamcmd_path=cfg.steamcmd_path,
            steam_branch=cfg.steam_branch,
            steam_api_timeout_sec=cfg.steam_api_timeout_sec,
            steamcmd_timeout_sec=cfg.steamcmd_timeout_sec,
            steamcmd_dump_path=cfg.steamcmd_dump_path,
        )
    except Exception as exc:
        logger.log(f"Update check failed: {exc}")
        return

    _log_update_result(cfg, result, logger)

    if not result.any_outdated:
        logger.log("No updates detected.")
        return

    if not cfg.rcon_password:
        logger.log("RCON password missing. Set RCONPassword in config/rcon.conf or monitor.conf.")
        return

    rcon = RconClient(
        host=cfg.rcon_host,
        port=cfg.rcon_port,
        password=cfg.rcon_password,
        timeout=cfg.rcon_timeout_sec,
    )

    try:
        player_count = get_player_count(rcon, cfg.players_command)
    except (OSError, RconError) as exc:
        logger.log(f"RCON error while checking players: {exc}")
        return

    if player_count is None:
        logger.log("Player count unknown. Using restart timer.")
    else:
        logger.log(f"Players connected: {player_count}")

    immediate = player_count == 0

    try:
        run_restart_sequence(rcon, cfg, logger, immediate=immediate)
    except (OSError, RconError) as exc:
        logger.log(f"RCON error during restart sequence: {exc}")


def main() -> int:
    default_config, default_rcon = _default_paths()

    parser = argparse.ArgumentParser(description="Project Zomboid update monitor.")
    parser.add_argument(
        "--config",
        default=str(default_config),
        help="Path to monitor.conf",
    )
    parser.add_argument(
        "--rcon",
        default=str(default_rcon),
        help="Path to rcon.conf (default: config/rcon.conf)",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single check and exit.",
    )
    args = parser.parse_args()

    cfg = load_config(Path(args.config), Path(args.rcon))
    logger = Logger(cfg.log_path)

    logger.log("Monitor started.")
    while True:
        run_once(cfg, logger)
        if args.once:
            break
        time.sleep(cfg.check_interval_sec)

    logger.log("Monitor stopped.")
    return 0
