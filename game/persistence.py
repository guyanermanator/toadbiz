from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .catalog import STOCK_CATALOG
from .models import Player, Stock

SAVE_VERSION = 2
DEFAULT_FACTION_TERRITORIES = {
    "toad": 0.15,
    "frog": 0.15,
    "bug": 0.15,
    "lizard": 0.15,
    "bird": 0.15,
    "fox": 0.15,
    "shark": 0.10,
}


class GameStore:
    def __init__(self, state_file: Path) -> None:
        self.state_file = state_file
        self.state_file.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> tuple[dict[str, Stock], dict[str, Player], list[dict[str, Any]], list[dict[str, Any]], dict[str, float]]:
        saved: dict[str, Any] = {}
        if self.state_file.exists():
            with self.state_file.open("r", encoding="utf-8") as handle:
                saved = json.load(handle)
        saved = self._migrate_payload(saved)

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
        faction_territories = self._clean_faction_territories(saved.get("factionTerritories", {}))
        return stocks, players, chat_log, news_log, faction_territories

    def save(
        self,
        stocks: dict[str, Stock],
        players: dict[str, Player],
        chat_log: list[dict[str, Any]],
        news_log: list[dict[str, Any]],
        faction_territories: dict[str, float],
    ) -> None:
        payload = {
            "version": SAVE_VERSION,
            "stocks": [stock.to_save() for stock in stocks.values()],
            "players": {key: player.to_save() for key, player in players.items()},
            "chatLog": chat_log[-60:],
            "newsLog": news_log[-80:],
            "factionTerritories": self._clean_faction_territories(faction_territories),
        }
        temporary_path = self.state_file.with_suffix(".tmp")
        with temporary_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
        os.replace(temporary_path, self.state_file)

    def _migrate_payload(self, saved: dict[str, Any]) -> dict[str, Any]:
        payload = dict(saved or {})
        version = int(payload.get("version", 0) or 0)
        if version < 1:
            version = 1
        if version < 2:
            payload.setdefault("factionTerritories", DEFAULT_FACTION_TERRITORIES)
            version = 2
        payload["version"] = version
        return payload

    def _clean_faction_territories(self, payload: Any) -> dict[str, float]:
        cleaned = dict(DEFAULT_FACTION_TERRITORIES)
        if isinstance(payload, dict):
            for key, value in payload.items():
                if key in cleaned:
                    try:
                        cleaned[key] = max(0.01, float(value))
                    except (TypeError, ValueError):
                        continue
        total = sum(cleaned.values()) or 1.0
        return {key: value / total for key, value in cleaned.items()}
