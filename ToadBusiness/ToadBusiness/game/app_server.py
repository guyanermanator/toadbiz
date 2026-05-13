from __future__ import annotations

import argparse
import asyncio
import json
import mimetypes
import secrets
import socket
import string
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

from .persistence import GameStore
from .simulation import MarketEngine
from .websocket import (
    WebSocketClosed,
    is_websocket_request,
    read_frame,
    read_http_headers,
    send_close,
    send_json,
    send_pong,
    write_handshake,
)


ROOT_DIR = Path(__file__).resolve().parents[1]
PUBLIC_DIR = ROOT_DIR / "public"
STATE_FILE = ROOT_DIR / "data" / "game_state.json"


class ClientConnection:
    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self.reader = reader
        self.writer = writer
        self.name: str | None = None
        self.signal_host_lobby: str | None = None
        self.signal_join_lobby: str | None = None
        self.signal_join_id: str | None = None
        self.send_lock = asyncio.Lock()

    async def send(self, payload: dict[str, Any]) -> None:
        async with self.send_lock:
            await send_json(self.writer, payload)


class GameServer:
    def __init__(self, host: str, port: int, public_dir: Path = PUBLIC_DIR, state_file: Path = STATE_FILE) -> None:
        self.host = host
        self.port = port
        self.public_dir = public_dir.resolve()
        self.store = GameStore(state_file)
        stocks, players, chat_log, news_log = self.store.load()
        self.engine = MarketEngine(stocks, players, chat_log, news_log)
        self.clients: set[ClientConnection] = set()
        self.signal_lobbies: dict[str, dict[str, Any]] = {}
        self._last_save = 0.0

    async def run(self) -> None:
        server = await asyncio.start_server(self.handle_connection, self.host, self.port)
        sockets = ", ".join(str(sock.getsockname()) for sock in server.sockets or [])
        urls = [f"http://127.0.0.1:{self.port}"]
        lan_ip = self.lan_ip()
        if lan_ip and lan_ip != "127.0.0.1":
            urls.append(f"http://{lan_ip}:{self.port}")
        print(f"Toad Business running at {', '.join(urls)} ({sockets})", flush=True)
        async with server:
            await asyncio.gather(server.serve_forever(), self.game_loop(), self.autosave_loop())

    async def handle_connection(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            request_line, headers, _raw = await read_http_headers(reader)
            parts = request_line.split()
            if len(parts) < 2:
                await self.write_http(writer, 400, b"Bad Request", "text/plain")
                return
            method, target = parts[0], parts[1]
            if is_websocket_request(headers):
                await self.handle_websocket(headers, reader, writer)
            else:
                await self.handle_static(method, target, writer)
        except (asyncio.IncompleteReadError, ConnectionError, OSError):
            pass
        finally:
            if not writer.is_closing():
                writer.close()
                try:
                    await writer.wait_closed()
                except OSError:
                    pass

    async def handle_static(self, method: str, target: str, writer: asyncio.StreamWriter) -> None:
        if method != "GET":
            await self.write_http(writer, 405, b"Method Not Allowed", "text/plain")
            return
        path = unquote(urlsplit(target).path)
        if path == "/":
            path = "/index.html"
        file_path = (self.public_dir / path.lstrip("/")).resolve()
        if not self.is_safe_public_file(file_path):
            await self.write_http(writer, 404, b"Not Found", "text/plain")
            return
        content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        await self.write_http(writer, 200, file_path.read_bytes(), content_type)

    def is_safe_public_file(self, file_path: Path) -> bool:
        try:
            return file_path.is_file() and self.public_dir in file_path.parents
        except OSError:
            return False

    async def write_http(self, writer: asyncio.StreamWriter, status: int, body: bytes, content_type: str) -> None:
        reason = {
            200: "OK",
            400: "Bad Request",
            404: "Not Found",
            405: "Method Not Allowed",
            500: "Internal Server Error",
        }.get(status, "OK")
        response = (
            f"HTTP/1.1 {status} {reason}\r\n"
            f"Content-Length: {len(body)}\r\n"
            f"Content-Type: {content_type}; charset=utf-8\r\n"
            "Cache-Control: no-store\r\n"
            "Connection: close\r\n"
            "\r\n"
        ).encode("ascii") + body
        writer.write(response)
        await writer.drain()

    async def handle_websocket(
        self,
        headers: dict[str, str],
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        client_key = headers.get("sec-websocket-key")
        if not client_key:
            await self.write_http(writer, 400, b"Missing WebSocket key", "text/plain")
            return
        await write_handshake(writer, client_key)
        client = ClientConnection(reader, writer)
        self.clients.add(client)
        self.refresh_connected_players()
        await self.broadcast_market()
        try:
            await self.websocket_loop(client)
        except WebSocketClosed:
            pass
        finally:
            self.engine.leave_player(client.name)
            await self.cleanup_signaling_client(client)
            self.clients.discard(client)
            self.refresh_connected_players()
            await self.broadcast_market()

    async def websocket_loop(self, client: ClientConnection) -> None:
        while True:
            opcode, payload = await read_frame(client.reader)
            if opcode == 0x8:
                await send_close(client.writer)
                raise WebSocketClosed()
            if opcode == 0x9:
                await send_pong(client.writer, payload)
                continue
            if opcode != 0x1:
                continue
            try:
                message = json.loads(payload.decode("utf-8"))
                await self.process_message(client, message)
            except (json.JSONDecodeError, UnicodeDecodeError):
                await client.send({"type": "error", "message": "Invalid message."})
            except ValueError as exc:
                await client.send({"type": "error", "message": str(exc)})

    async def process_message(self, client: ClientConnection, message: dict[str, Any]) -> None:
        message_type = message.get("type")
        if message_type == "signalHostStart":
            lobby_id = await self.create_signal_lobby(client)
            await client.send({"type": "signalLobbyReady", "lobbyId": lobby_id})
            return
        if message_type == "signalJoinStart":
            lobby_id = str(message.get("lobbyId", "")).upper()
            offer = message.get("offer")
            join_id = await self.add_signal_joiner(client, lobby_id, offer)
            await client.send({"type": "signalJoinPending", "lobbyId": lobby_id, "joinId": join_id})
            return
        if message_type == "signalHostAnswer":
            await self.route_host_answer(
                client,
                str(message.get("lobbyId", "")).upper(),
                str(message.get("joinId", "")),
                message.get("answer"),
            )
            return
        if message_type == "signalIceCandidate":
            await self.route_ice_candidate(
                client,
                str(message.get("lobbyId", "")).upper(),
                str(message.get("joinId", "")),
                str(message.get("role", "")),
                message.get("candidate"),
            )
            return

        if message_type == "join":
            player = self.engine.join_player(
                str(message.get("name", "")),
                str(message.get("color", "")),
                str(message.get("messageColor", "")),
                str(message.get("chatFont", "")),
            )
            client.name = player.name
            await client.send(
                {
                    "type": "welcome",
                    "player": self.engine.player_snapshot(player.name),
                    "market": self.engine.market_snapshot(),
                    "chatLog": self.engine.chat_log,
                }
            )
            self.refresh_connected_players()
            await self.broadcast_market()
            return

        if not client.name:
            raise ValueError("Join with a player name first.")

        if message_type == "profile":
            player = self.engine.update_player_profile(
                client.name,
                str(message.get("name", "")),
                str(message.get("color", "")),
                str(message.get("messageColor", "")),
                str(message.get("chatFont", "")),
            )
            client.name = player.name
            await client.send({"type": "notice", "message": "Profile updated."})
            await self.broadcast_market()
        elif message_type == "buy":
            result = self.engine.buy(client.name, str(message.get("stockId", "")), message.get("shares", 0))
            await client.send({"type": "notice", "message": f"Bought {result['shares']} {result['stock']} shares."})
            await self.broadcast_market()
        elif message_type == "buyMax":
            result = self.engine.buy_max(client.name, str(message.get("stockId", "")))
            await client.send({"type": "notice", "message": f"Bought max: {result['shares']} {result['stock']} shares."})
            await self.broadcast_market()
        elif message_type == "sell":
            result = self.engine.sell(client.name, str(message.get("stockId", "")), message.get("shares", 0))
            await client.send({"type": "notice", "message": f"Sold {result['shares']} {result['stock']} shares."})
            await self.broadcast_market()
        elif message_type == "sellMax":
            result = self.engine.sell_max(client.name, str(message.get("stockId", "")))
            await client.send({"type": "notice", "message": f"Sold all: {result['shares']} {result['stock']} shares."})
            await self.broadcast_market()
        elif message_type == "upgradeIncome":
            result = self.engine.upgrade_income(client.name)
            await client.send({"type": "notice", "message": f"Hourly income upgraded to ${result['hourlyIncome']:.2f}."})
            await self.broadcast_market()
        elif message_type == "buyProperty":
            result = self.engine.buy_real_estate(client.name, str(message.get("templateId", "")))
            await client.send({"type": "notice", "message": f"Bought {result['name']}."})
            await self.broadcast_market()
        elif message_type == "sellProperty":
            result = self.engine.sell_real_estate(client.name, str(message.get("assetId", "")))
            await client.send({"type": "notice", "message": f"Sold {result['name']} for ${result['value']:.2f}."})
            await self.broadcast_market()
        elif message_type == "upgradeProperty":
            result = self.engine.upgrade_real_estate(client.name, str(message.get("assetId", "")))
            await client.send({"type": "notice", "message": f"Upgraded {result['name']}."})
            await self.broadcast_market()
        elif message_type == "evictRenter":
            result = self.engine.evict_renter(client.name, str(message.get("assetId", "")))
            await client.send({"type": "notice", "message": f"Evicted {result['oldRenter']}; {result['newRenter']} moved in."})
            await self.broadcast_market()
        elif message_type == "setRent":
            result = self.engine.set_rent(client.name, str(message.get("assetId", "")), message.get("rentPerHour", 0))
            await client.send({"type": "notice", "message": f"{result['property']} rent set to ${result['rentPerHour']:.2f}/hr."})
            await self.broadcast_market()
        elif message_type == "buyBusiness":
            result = self.engine.buy_business(client.name, str(message.get("templateId", "")))
            await client.send({"type": "notice", "message": f"Bought {result['name']} and listed its stock."})
            await self.broadcast_market()
        elif message_type == "sellBusiness":
            result = self.engine.sell_business(client.name, str(message.get("businessId", "")))
            await client.send({"type": "notice", "message": f"Sold {result['name']} for ${result['value']:.2f}."})
            await self.broadcast_market()
        elif message_type == "upgradeBusiness":
            result = self.engine.upgrade_business(client.name, str(message.get("businessId", "")))
            await client.send({"type": "notice", "message": f"Upgraded {result['name']}."})
            await self.broadcast_market()
        elif message_type == "renameBusiness":
            result = self.engine.rename_business(client.name, str(message.get("businessId", "")), str(message.get("name", "")))
            await client.send({"type": "notice", "message": f"Business renamed to {result['name']}."})
            await self.broadcast_market()
        elif message_type == "sabotage":
            result = self.engine.sabotage(client.name, str(message.get("stockId", "")), str(message.get("optionId", "")))
            await client.send({"type": "notice", "message": f"Funded {result['option']} against {result['stock']}."})
            await self.broadcast_market()
        elif message_type == "chat":
            entry = self.engine.add_chat(client.name, str(message.get("message", "")))
            await self.broadcast({"type": "chat", "entry": entry})
        else:
            raise ValueError("Unknown action.")

    async def game_loop(self) -> None:
        while True:
            await asyncio.sleep(1.0)
            self.engine.tick()
            await self.broadcast_market()

    async def autosave_loop(self) -> None:
        while True:
            await asyncio.sleep(5.0)
            if self.engine.dirty:
                self.store.save(self.engine.stocks, self.engine.players, self.engine.chat_log, self.engine.news_log)
                self.engine.mark_clean()

    async def send_player(self, client: ClientConnection) -> None:
        if client.name:
            await client.send({"type": "player", "player": self.engine.player_snapshot(client.name)})

    async def broadcast_market(self) -> None:
        clients = [client for client in self.clients if client.name]
        if not clients:
            return
        market = self.engine.market_snapshot()
        sends = []
        for client in clients:
            payload: dict[str, Any] = {"type": "snapshot", "market": market}
            if client.name:
                payload["player"] = self.engine.player_snapshot(client.name)
            sends.append(client.send(payload))
        await self._gather_safely(clients, sends)

    async def broadcast(self, payload: dict[str, Any]) -> None:
        clients = [client for client in self.clients if client.name]
        await self._gather_safely(clients, [client.send(payload) for client in clients])

    async def _gather_safely(self, clients: list[ClientConnection], sends: list[Any]) -> None:
        if not sends:
            return
        results = await asyncio.gather(*sends, return_exceptions=True)
        for client, result in zip(clients, results):
            if isinstance(result, Exception):
                await self.cleanup_signaling_client(client)
                self.clients.discard(client)

    def refresh_connected_players(self) -> None:
        self.engine.connected_players = sum(1 for client in self.clients if client.name)

    def random_code(self, length: int = 6) -> str:
        alphabet = string.ascii_uppercase + string.digits
        return "".join(secrets.choice(alphabet) for _ in range(length))

    async def create_signal_lobby(self, host: ClientConnection) -> str:
        await self.cleanup_signaling_client(host)
        for _ in range(20):
            lobby_id = self.random_code(6)
            if lobby_id not in self.signal_lobbies:
                self.signal_lobbies[lobby_id] = {"host": host, "joins": {}}
                host.signal_host_lobby = lobby_id
                return lobby_id
        raise ValueError("Unable to create lobby right now.")

    async def add_signal_joiner(self, joiner: ClientConnection, lobby_id: str, offer: Any) -> str:
        if not lobby_id or not offer:
            raise ValueError("Invalid join request.")
        lobby = self.signal_lobbies.get(lobby_id)
        if not lobby:
            raise ValueError("Lobby not found.")
        host: ClientConnection = lobby["host"]
        if host not in self.clients:
            raise ValueError("Host is offline.")

        await self.cleanup_signaling_client(joiner)
        join_id = self.random_code(8)
        lobby["joins"][join_id] = joiner
        joiner.signal_join_lobby = lobby_id
        joiner.signal_join_id = join_id

        await host.send({"type": "signalJoinOffer", "lobbyId": lobby_id, "joinId": join_id, "offer": offer})
        return join_id

    async def route_host_answer(self, host: ClientConnection, lobby_id: str, join_id: str, answer: Any) -> None:
        lobby = self.signal_lobbies.get(lobby_id)
        if not lobby or lobby.get("host") is not host:
            raise ValueError("Lobby is not active for this host.")
        target: ClientConnection | None = lobby["joins"].get(join_id)
        if not target:
            raise ValueError("Join request expired.")
        await target.send({"type": "signalJoinAnswer", "lobbyId": lobby_id, "joinId": join_id, "answer": answer})

    async def route_ice_candidate(self, client: ClientConnection, lobby_id: str, join_id: str, role: str, candidate: Any) -> None:
        if not candidate:
            return
        lobby = self.signal_lobbies.get(lobby_id)
        if not lobby:
            raise ValueError("Lobby not found.")
        host: ClientConnection = lobby["host"]
        joiner: ClientConnection | None = lobby["joins"].get(join_id)
        if not joiner:
            raise ValueError("Join request expired.")

        if role == "join":
            if client is not joiner:
                raise ValueError("Invalid join signaling client.")
            await host.send({"type": "signalHostIceCandidate", "lobbyId": lobby_id, "joinId": join_id, "candidate": candidate})
            return

        if role == "host":
            if client is not host:
                raise ValueError("Invalid host signaling client.")
            await joiner.send({"type": "signalJoinIceCandidate", "lobbyId": lobby_id, "joinId": join_id, "candidate": candidate})
            return

        raise ValueError("Unknown signaling role.")

    async def cleanup_signaling_client(self, client: ClientConnection) -> None:
        if client.signal_host_lobby:
            lobby_id = client.signal_host_lobby
            lobby = self.signal_lobbies.pop(lobby_id, None)
            client.signal_host_lobby = None
            if lobby:
                for join_id, joiner in list(lobby["joins"].items()):
                    joiner.signal_join_lobby = None
                    joiner.signal_join_id = None
                    if joiner in self.clients:
                        try:
                            await joiner.send({"type": "signalLobbyClosed", "lobbyId": lobby_id})
                        except Exception:
                            pass

        if client.signal_join_lobby and client.signal_join_id:
            lobby_id = client.signal_join_lobby
            join_id = client.signal_join_id
            client.signal_join_lobby = None
            client.signal_join_id = None
            lobby = self.signal_lobbies.get(lobby_id)
            if lobby:
                lobby["joins"].pop(join_id, None)
                host = lobby.get("host")
                if host and host in self.clients:
                    try:
                        await host.send({"type": "signalJoinLeft", "lobbyId": lobby_id, "joinId": join_id})
                    except Exception:
                        pass

    def lan_ip(self) -> str:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            probe.connect(("8.8.8.8", 80))
            return str(probe.getsockname()[0])
        except OSError:
            return "127.0.0.1"
        finally:
            probe.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Toad Business realtime stock game server.")
    parser.add_argument("--host", default="0.0.0.0", help="Bind host. 0.0.0.0 allows LAN play.")
    parser.add_argument("--port", default=8000, type=int, help="HTTP/WebSocket port.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    server = GameServer(args.host, args.port)
    try:
        asyncio.run(server.run())
    except KeyboardInterrupt:
        server.store.save(server.engine.stocks, server.engine.players, server.engine.chat_log, server.engine.news_log)
        print("Saved game state.")
