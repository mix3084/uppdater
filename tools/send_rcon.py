import argparse
import socket
import struct
from pathlib import Path


CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "rcon.conf"


def parse_config(path: Path) -> dict:
    """
    Load key=value pairs from rcon.conf, skipping comments and blanks.
    """
    data = {}
    if not path.exists():
        return data

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = value.strip()
    return data


def recv_exact(sock: socket.socket, length: int) -> bytes:
    chunks = []
    remaining = length
    while remaining > 0:
        chunk = sock.recv(remaining)
        if not chunk:
            raise ConnectionError("Connection closed by server")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def recv_packet(sock: socket.socket):
    raw_len = recv_exact(sock, 4)
    (length,) = struct.unpack("<i", raw_len)
    payload = recv_exact(sock, length)
    req_id, packet_type = struct.unpack("<ii", payload[:8])
    body = payload[8:-2]
    return req_id, packet_type, body


def send_packet(sock: socket.socket, req_id: int, packet_type: int, body: str) -> None:
    body_bytes = body.encode("utf-8")
    packet = struct.pack("<iii", len(body_bytes) + 10, req_id, packet_type) + body_bytes + b"\x00\x00"
    sock.sendall(packet)


def authenticate(sock: socket.socket, password: str) -> bool:
    send_packet(sock, 1, 3, password)  # 3 == SERVERDATA_AUTH
    while True:
        req_id, packet_type, _ = recv_packet(sock)
        if packet_type == 2:  # SERVERDATA_AUTH_RESPONSE
            return req_id != -1
        if req_id == -1:
            return False


def send_command(host: str, port: int, password: str, command: str, timeout: float = 5.0) -> str:
    with socket.create_connection((host, port), timeout=timeout) as sock:
        sock.settimeout(timeout)

        if not authenticate(sock, password):
            raise ConnectionError("RCON auth failed")

        send_packet(sock, 2, 2, command)  # 2 == SERVERDATA_EXECCOMMAND
        try:
            req_id, packet_type, body = recv_packet(sock)
            if packet_type not in (0, 2):
                raise ConnectionError(f"Unexpected packet type {packet_type}")
            return body.decode("utf-8", errors="replace")
        except socket.timeout:
            return ""


def main():
    parser = argparse.ArgumentParser(
        description="Send an RCON command using config/rcon.conf as defaults."
    )
    parser.add_argument("command", nargs="+", help="Command to send, e.g. servermsg \"hello\"")
    parser.add_argument("--host", help="Override host (defaults to RCONHost in config/rcon.conf)")
    parser.add_argument("--port", type=int, help="Override port (defaults to RCONPort in config/rcon.conf)")
    parser.add_argument("--password", help="Override password (defaults to RCONPassword in config/rcon.conf)")
    parser.add_argument("--timeout", type=float, default=5.0, help="Socket timeout in seconds")
    args = parser.parse_args()

    cmd = " ".join(args.command)
    cfg = parse_config(CONFIG_PATH)

    host = args.host or cfg.get("RCONHost") or "127.0.0.1"
    port = args.port or int(cfg.get("RCONPort", 27015))
    password = args.password or cfg.get("RCONPassword")

    if not password:
        parser.error("RCONPassword is required (pass --password or set RCONPassword in config/rcon.conf)")

    response = send_command(host, port, password, cmd, timeout=args.timeout)
    if response:
        print(response)


if __name__ == "__main__":
    main()
