from __future__ import annotations

import datetime as dt
import time
from pathlib import Path
from typing import Optional


def now_str() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return path.read_text(encoding="cp1251", errors="replace")


def format_ts(ts: Optional[int]) -> str:
    if not ts:
        return "n/a"
    try:
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))
    except Exception:
        return str(ts)
