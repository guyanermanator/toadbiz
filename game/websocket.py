from __future__ import annotations

import asyncio
import base64
import hashlib
import json
from typing import Any


WEBSOCKET_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


class WebSocketClosed(Exception):
    pass


def accept_key(client_key: str) -> str:
    digest = hashlib.sha1((client_key + WEBSOCKET_GUID).encode("ascii")).digest()
    return base64.b64encode(digest).decode("ascii")


async def read_http_headers(reader: asyncio.StreamReader) -> tuple[str, dict[str, str], bytes]:
    raw = await reader.readuntil(b"\r\n\r\n")
    header_text = raw.decode("iso-8859-1")
    lines = header_text.split("\r\n")
    request_line = lines[0]
    headers: dict[str, str] = {}
    for line in lines[1:]:
        if not line or ":" not in line:
            continue
        name, value = line.split(":", 1)
        headers[name.strip().lower()] = value.strip()
    return request_line, headers, raw


def is_websocket_request(headers: dict[str, str]) -> bool:
    return headers.get("upgrade", "").lower() == "websocket" and "upgrade" in headers.get("connection", "").lower()


async def write_handshake(writer: asyncio.StreamWriter, client_key: str) -> None:
    response = (
        "HTTP/1.1 101 Switching Protocols\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Accept: {accept_key(client_key)}\r\n"
        "\r\n"
    )
    writer.write(response.encode("ascii"))
    await writer.drain()


async def read_frame(reader: asyncio.StreamReader) -> tuple[int, bytes]:
    try:
        header = await reader.readexactly(2)
    except asyncio.IncompleteReadError as exc:
        raise WebSocketClosed() from exc

    first, second = header
    opcode = first & 0x0F
    masked = (second & 0x80) != 0
    length = second & 0x7F

    if length == 126:
        extended = await reader.readexactly(2)
        length = int.from_bytes(extended, "big")
    elif length == 127:
        extended = await reader.readexactly(8)
        length = int.from_bytes(extended, "big")

    mask_key = b""
    if masked:
        mask_key = await reader.readexactly(4)

    payload = await reader.readexactly(length) if length else b""
    if masked and payload:
        payload = bytes(byte ^ mask_key[index % 4] for index, byte in enumerate(payload))
    return opcode, payload


def encode_frame(opcode: int, payload: bytes) -> bytes:
    first = 0x80 | (opcode & 0x0F)
    length = len(payload)
    if length < 126:
        header = bytes([first, length])
    elif length < 65536:
        header = bytes([first, 126]) + length.to_bytes(2, "big")
    else:
        header = bytes([first, 127]) + length.to_bytes(8, "big")
    return header + payload


async def send_text(writer: asyncio.StreamWriter, text: str) -> None:
    writer.write(encode_frame(0x1, text.encode("utf-8")))
    await writer.drain()


async def send_json(writer: asyncio.StreamWriter, payload: dict[str, Any]) -> None:
    await send_text(writer, json.dumps(payload, separators=(",", ":")))


async def send_pong(writer: asyncio.StreamWriter, payload: bytes) -> None:
    writer.write(encode_frame(0xA, payload))
    await writer.drain()


async def send_close(writer: asyncio.StreamWriter) -> None:
    writer.write(encode_frame(0x8, b""))
    await writer.drain()
