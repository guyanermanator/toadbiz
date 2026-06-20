from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Any


TERRAIN_TYPES = ("ocean", "coastal", "plains", "forest", "mountain", "desert", "river", "swamp", "tundra")
IMPROVEMENT_TYPES = ("none", "research_site", "refinery", "nature_reserve", "corporate_hq")
RESOURCE_TYPES = (
    "gold",
    "silver",
    "iron",
    "copper",
    "lithium",
    "uranium",
    "silicon",
    "nickel",
    "fish",
    "timber",
    "grain",
    "oil",
    "water",
)
WATER_TERRAINS = {"ocean"}

FACTION_PROFILES: dict[str, dict[str, Any]] = {
    "toad": {"name": "Toad", "color": "#4a9d6f", "aggression": {"war": 0.30, "trade": 0.45, "expansion": 0.25}},
    "frog": {"name": "Frog", "color": "#2d7a3a", "aggression": {"war": 0.28, "trade": 0.42, "expansion": 0.30}},
    "bug": {"name": "Bug", "color": "#8b5a2b", "aggression": {"war": 0.35, "trade": 0.30, "expansion": 0.35}},
    "lizard": {"name": "Lizard", "color": "#ff6b35", "aggression": {"war": 0.42, "trade": 0.22, "expansion": 0.36}},
    "bird": {"name": "Bird", "color": "#ffd700", "aggression": {"war": 0.25, "trade": 0.35, "expansion": 0.40}},
    "fox": {"name": "Fox", "color": "#d2691e", "aggression": {"war": 0.32, "trade": 0.36, "expansion": 0.32}},
    "shark": {"name": "Shark", "color": "#0066cc", "aggression": {"war": 0.48, "trade": 0.20, "expansion": 0.32}},
}

TERRAIN_RESOURCE_WEIGHTS: dict[str, list[tuple[str, float, float]]] = {
    "ocean": [("fish", 1.0, 2.6), ("water", 0.8, 1.9)],
    "coastal": [("fish", 1.0, 2.3), ("water", 0.6, 1.6), ("oil", 0.2, 1.1)],
    "plains": [("grain", 1.0, 2.5), ("water", 0.2, 0.9), ("copper", 0.15, 0.8)],
    "forest": [("timber", 1.0, 2.4), ("grain", 0.3, 1.0), ("silicon", 0.15, 0.7)],
    "mountain": [("iron", 1.0, 2.2), ("copper", 0.6, 1.6), ("silver", 0.2, 1.1), ("uranium", 0.08, 0.8)],
    "desert": [("silicon", 1.0, 2.3), ("oil", 0.4, 1.8), ("gold", 0.1, 0.8)],
    "river": [("water", 1.0, 2.2), ("grain", 0.5, 1.5), ("gold", 0.06, 0.8)],
    "swamp": [("water", 1.0, 2.0), ("timber", 0.5, 1.4), ("lithium", 0.12, 0.8)],
    "tundra": [("nickel", 0.8, 1.7), ("silver", 0.3, 1.1), ("water", 0.4, 1.1)],
}

TERRAIN_COLORS: dict[str, str] = {
    "ocean": "#0d2157",
    "coastal": "#2a7faa",
    "plains": "#6aaa44",
    "forest": "#2d6a2d",
    "mountain": "#7a6551",
    "desert": "#c9942a",
    "river": "#4f9dd1",
    "swamp": "#4a7535",
    "tundra": "#8ab5c4",
}


def _noise01(q: int, r: int, seed: int, salt: int = 0) -> float:
    n = math.sin((q + seed * 0.01 + salt * 7.17) * 0.127 + (r + salt * 13.1) * 0.173) * 43758.5453
    return n - math.floor(n)


@dataclass(frozen=True)
class HexCoord:
    q: int
    r: int

    @property
    def id(self) -> str:
        return f"{self.q}:{self.r}"


class StrategicMapWorld:
    def __init__(self, width: int = 1000, height: int = 1000, seed: int = 1337, chunk_size: int = 24) -> None:
        self.width = max(32, int(width))
        self.height = max(32, int(height))
        self.seed = int(seed)
        self.chunk_size = max(8, int(chunk_size))
        self._rng = random.Random(self.seed ^ 0xA511E9)
        self.faction_starts = self._generate_faction_starts()

    def _is_inside(self, q: int, r: int) -> bool:
        return 0 <= q < self.width and 0 <= r < self.height

    def _terrain_for(self, q: int, r: int) -> str:
        nx = q / max(1, self.width - 1)
        ny = r / max(1, self.height - 1)
        latitude = abs(ny - 0.5) * 2.0
        h = (_noise01(q, r, self.seed, 1) * 0.62) + (_noise01(q, r, self.seed, 2) * 0.38)
        m = (_noise01(q, r, self.seed, 3) * 0.6) + (_noise01(q, r, self.seed, 4) * 0.4)
        river_noise = _noise01(q, r, self.seed, 5)

        edge = max(abs(nx * 2 - 1), abs(ny * 2 - 1))
        h = h * (1.0 - max(0.0, edge - 0.22) * 0.58)

        if h < 0.28:
            return "ocean"
        if h < 0.34:
            return "coastal"
        if latitude > 0.78 and h > 0.42:
            return "tundra"
        if h > 0.75:
            return "mountain"
        if 0.47 < h < 0.66 and 0.42 < river_noise < 0.47:
            return "river"
        if m < 0.22:
            return "desert"
        if m > 0.71:
            return "swamp"
        if m > 0.50:
            return "forest"
        return "plains"

    def _resource_yields_for(self, q: int, r: int, terrain: str) -> list[dict[str, Any]]:
        rng = random.Random((self.seed * 1315423911) ^ (q * 83492791) ^ (r * 2654435761))
        resource_table = TERRAIN_RESOURCE_WEIGHTS.get(terrain, [])
        if not resource_table:
            return []

        picked: list[dict[str, Any]] = []
        for name, chance, max_yield in resource_table:
            if rng.random() <= chance:
                amount = round(0.35 + rng.random() * max_yield, 2)
                picked.append({"resource": name, "yield": amount})

        if not picked:
            base = resource_table[0]
            amount = round(0.25 + rng.random() * max(0.8, base[2] * 0.6), 2)
            picked.append({"resource": base[0], "yield": amount})

        if rng.random() < 0.035:
            rare = rng.choice(["gold", "silver", "uranium", "lithium"])
            amount = round(0.15 + rng.random() * 0.7, 2)
            if all(entry["resource"] != rare for entry in picked):
                picked.append({"resource": rare, "yield": amount})

        return picked[:4]

    def _improvement_for(self, q: int, r: int, terrain: str) -> str | None:
        if terrain in WATER_TERRAINS:
            return None
        n = _noise01(q, r, self.seed, 6)
        if n > 0.993:
            return "corporate_hq"
        if n > 0.985:
            return "research_site"
        if n > 0.976:
            return "refinery"
        if n > 0.966:
            return "nature_reserve"
        return None

    def _valid_start(self, q: int, r: int) -> bool:
        terrain = self._terrain_for(q, r)
        return terrain not in WATER_TERRAINS

    def _generate_faction_starts(self) -> dict[str, HexCoord]:
        starts: dict[str, HexCoord] = {}
        factions = list(FACTION_PROFILES)
        attempts = 0
        min_dist = max(24.0, min(self.width, self.height) / 8.0)
        while len(starts) < len(factions) and attempts < 20000:
            attempts += 1
            key = factions[len(starts)]
            q = self._rng.randrange(0, self.width)
            r = self._rng.randrange(0, self.height)
            if not self._valid_start(q, r):
                continue
            if any(((q - other.q) ** 2 + (r - other.r) ** 2) ** 0.5 < min_dist for other in starts.values()):
                continue
            starts[key] = HexCoord(q=q, r=r)
        for key in factions:
            if key not in starts:
                for _ in range(10000):
                    q = self._rng.randrange(0, self.width)
                    r = self._rng.randrange(0, self.height)
                    if self._valid_start(q, r):
                        starts[key] = HexCoord(q=q, r=r)
                        break
                else:
                    starts[key] = HexCoord(0, 0)
        return starts

    def _owner_for(self, q: int, r: int, terrain: str) -> str | None:
        if terrain in WATER_TERRAINS:
            return None
        best_faction = None
        best_score = float("inf")
        for key, start in self.faction_starts.items():
            dx = q - start.q
            dy = r - start.r
            dist = (dx * dx + dy * dy) ** 0.5
            faction_weight = 0.9 + (_noise01(q, r, self.seed, 7 + len(key)) * 0.35)
            score = dist / faction_weight
            if score < best_score:
                best_score = score
                best_faction = key
        return best_faction

    def cell_snapshot(self, q: int, r: int) -> dict[str, Any] | None:
        if not self._is_inside(q, r):
            return None
        coord = HexCoord(q=q, r=r)
        terrain = self._terrain_for(q, r)
        owner = self._owner_for(q, r, terrain)
        resources = self._resource_yields_for(q, r, terrain)
        improvement = self._improvement_for(q, r, terrain)
        return {
            "id": coord.id,
            "q": q,
            "r": r,
            "terrain": terrain,
            "terrainColor": TERRAIN_COLORS.get(terrain, "#555555"),
            "owner": owner,
            "ownerColor": FACTION_PROFILES.get(owner, {}).get("color") if owner else None,
            "resources": resources,
            "improvement": improvement,
        }

    def chunk_snapshot(self, chunk_q: int, chunk_r: int) -> dict[str, Any]:
        base_q = max(0, chunk_q * self.chunk_size)
        base_r = max(0, chunk_r * self.chunk_size)
        max_q = min(self.width, base_q + self.chunk_size)
        max_r = min(self.height, base_r + self.chunk_size)
        cells: list[dict[str, Any]] = []
        for r in range(base_r, max_r):
            for q in range(base_q, max_q):
                cell = self.cell_snapshot(q, r)
                if cell is not None:
                    cells.append(cell)
        return {"chunkQ": chunk_q, "chunkR": chunk_r, "chunkSize": self.chunk_size, "cells": cells}

    def metadata_snapshot(self) -> dict[str, Any]:
        return {
            "width": self.width,
            "height": self.height,
            "chunkSize": self.chunk_size,
            "terrains": list(TERRAIN_TYPES),
            "resources": list(RESOURCE_TYPES),
            "improvements": list(IMPROVEMENT_TYPES),
            "factions": {
                key: {
                    "name": value["name"],
                    "color": value["color"],
                    "aggression": value["aggression"],
                    "startHex": {"q": self.faction_starts[key].q, "r": self.faction_starts[key].r},
                }
                for key, value in FACTION_PROFILES.items()
            },
        }
