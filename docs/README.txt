Project Zomboid update monitor

Usage:
  python main.py
  python main.py --once
  python main.py --config monitor.conf --rcon config\rcon.conf

Notes:
  - RCONHost/Port/Password are read from config\rcon.conf by default.
  - Logs are written to logs\monitor.log (created automatically).
  - MsgCountdown supports {seconds} placeholder.
  - Restart flow: 5 min warning, 1 min warning, 10 sec countdown, then save + quit.
