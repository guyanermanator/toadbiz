from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .catalog import STOCK_CATALOG
from .models import Player, Stock


class GameStore:
    def __init__(self, state_file: Path) -> None:
        self.state_file = state_file
        self.state_file.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> tuple[dict[str, Stock], dict[str, Player], list[dict[str, Any]], list[dict[str, Any]]]:
        saved: dict[str, Any] = {}
        if self.state_file.exists():
            with self.state_file.open("r", encoding="utf-8") as handle:
                saved = json.load(handle)

        saved_stocks = {stock["id"]: stock for stock in saved.get("stocks", []) if "id" in stock}
        stocks: dict[str, Stock] = {}
        for template in STOCK_CATALOG:
            if template.id in saved_stocks:
                stocks[template.id] = Stock.from_save(template, saved_stocks[template.id])
            else:
                stocks[template.id] = Stock.from_template(template)
        catalog_ids = {template.id for template in STOCK_CATALOG}
        for stock_id, stock_payload in saved_stocks.items():
            if stock_id not in catalog_ids:
                stocks[stock_id] = Stock.from_dynamic_save(stock_payload)

        players = {
            key: Player.from_save(player_payload)
            for key, player_payload in saved.get("players", {}).items()
        }
        chat_log = list(saved.get("chatLog", []))[-60:]
        news_log = list(saved.get("newsLog", []))[-80:]
        return stocks, players, chat_log, news_log

    def save(
        self,
        stocks: dict[str, Stock],
        players: dict[str, Player],
        chat_log: list[dict[str, Any]],
        news_log: list[dict[str, Any]],
    ) -> None:
        payload = {
            "version": 1,
            "stocks": [stock.to_save() for stock in stocks.values()],
            "players": {key: player.to_save() for key, player in players.items()},
            "chatLog": chat_log[-60:],
            "newsLog": news_log[-80:],
        }
        temporary_path = self.state_file.with_suffix(".tmp")
        with temporary_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
        os.replace(temporary_path, self.state_file)
