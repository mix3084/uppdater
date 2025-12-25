from __future__ import annotations

from pathlib import Path
from typing import Optional

from .utils import now_str


class Logger:
    def __init__(self, log_path: Optional[Path]) -> None:
        self._log_path = log_path
        if self._log_path:
            self._log_path.parent.mkdir(parents=True, exist_ok=True)

    def log(self, message: str) -> None:
        line = f"[{now_str()}] {message}"
        print(line)
        if not self._log_path:
            return
        with self._log_path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
