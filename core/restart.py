from __future__ import annotations

import time

from .config import MonitorConfig
from .logger import Logger
from .rcon_client import RconClient


def _send_servermsg(rcon: RconClient, text: str) -> None:
    command = f'servermsg "{text}"'
    rcon.send_command(command)


def _sleep_seconds(total_seconds: int) -> None:
    if total_seconds <= 0:
        return
    time.sleep(total_seconds)


def run_restart_sequence(
    rcon: RconClient,
    cfg: MonitorConfig,
    logger: Logger,
    immediate: bool,
) -> None:
    if immediate:
        logger.log("No players online. Restarting immediately.")
        rcon.send_command(cfg.save_command)
        rcon.send_command(cfg.quit_command)
        return

    delay = max(cfg.restart_delay_sec, 0)
    warn_1 = min(max(cfg.warn_1_min_sec, 0), delay)
    countdown = min(max(cfg.countdown_sec, 0), warn_1)

    logger.log(f"Restart scheduled in {delay} seconds.")
    _send_servermsg(rcon, cfg.msg_restart_5min)

    _sleep_seconds(delay - warn_1)

    if warn_1 > 0:
        _send_servermsg(rcon, cfg.msg_restart_1min)

    _sleep_seconds(warn_1 - countdown)

    if countdown > 0:
        for remaining in range(countdown, 0, -1):
            try:
                message = cfg.msg_countdown.format(seconds=remaining)
            except Exception:
                message = f"Restart in {remaining} seconds."
            _send_servermsg(rcon, message)
            time.sleep(1)

    rcon.send_command(cfg.save_command)
    rcon.send_command(cfg.quit_command)
