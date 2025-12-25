from __future__ import annotations

import socket
import struct


class RconError(RuntimeError):
    pass


def _recv_exact(sock: socket.socket, length: int) -> bytes:
    chunks = []
    remaining = length
    while remaining > 0:
        chunk = sock.recv(remaining)
        if not chunk:
            raise RconError("Connection closed by server")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _recv_packet(sock: socket.socket):
    raw_len = _recv_exact(sock, 4)
    (length,) = struct.unpack("<i", raw_len)
    payload = _recv_exact(sock, length)
    req_id, packet_type = struct.unpack("<ii", payload[:8])
    body = payload[8:-2]
    return req_id, packet_type, body


def _send_packet(sock: socket.socket, req_id: int, packet_type: int, body: str) -> None:
    body_bytes = body.encode("utf-8")
    packet = struct.pack("<iii", len(body_bytes) + 10, req_id, packet_type)
    packet += body_bytes + b"\x00\x00"
    sock.sendall(packet)


def _authenticate(sock: socket.socket, password: str) -> bool:
    _send_packet(sock, 1, 3, password)  # SERVERDATA_AUTH
    while True:
        req_id, packet_type, _ = _recv_packet(sock)
        if packet_type == 2:  # SERVERDATA_AUTH_RESPONSE
            return req_id != -1
        if req_id == -1:
            return False


class RconClient:
    def __init__(self, host: str, port: int, password: str, timeout: float) -> None:
        self._host = host
        self._port = port
        self._password = password
        self._timeout = timeout

    def send_command(self, command: str) -> str:
        with socket.create_connection((self._host, self._port), timeout=self._timeout) as sock:
            sock.settimeout(self._timeout)
            if not _authenticate(sock, self._password):
                raise RconError("RCON auth failed")
            _send_packet(sock, 2, 2, command)  # SERVERDATA_EXECCOMMAND
            try:
                req_id, packet_type, body = _recv_packet(sock)
                if packet_type not in (0, 2):
                    raise RconError(f"Unexpected packet type {packet_type}")
                return body.decode("utf-8", errors="replace")
            except socket.timeout:
                return ""
