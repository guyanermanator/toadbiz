from __future__ import annotations

import math
import random
import uuid
from dataclasses import dataclass, field
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
SEED_XOR_MASK = 0xA511E9
RESOURCE_SEED_MULTIPLIER = 1315423911
COORD_Q_HASH = 83492791
COORD_R_HASH = 2654435761
MIN_FACTION_START_DISTANCE = 24.0
FACTION_START_DISTANCE_DIVISOR = 8.0
MAX_FACTION_PLACEMENT_ATTEMPTS = 20000
MAX_FACTION_FALLBACK_ATTEMPTS = 10000

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


def _smooth_noise(fq: float, fr: float, seed: int, salt: int = 0) -> float:
    """Hash-based pseudo-random noise that accepts float coordinates (for multi-scale use)."""
    n = math.sin((fq + seed * 0.01 + salt * 7.17) * 0.127 + (fr + salt * 13.1) * 0.173) * 43758.5453
    return n - math.floor(n)


def _continent_height(q: int, r: int, seed: int, width: int, height: int) -> float:
    """
    Multi-scale continental height map.

    Uses large-scale noise octaves to produce continent-like land masses
    rather than scattered random hex noise.  Returns a 0-1 value where
    higher values mean more elevated / further inland terrain.
    """
    # Very large scale: continental plates (~200-400 hex spans)
    h0 = _smooth_noise(q * 0.0040, r * 0.0040, seed, 31)
    # Medium scale: sub-continental texture / peninsulas (~60-100 hex spans)
    h1 = _smooth_noise(q * 0.0110, r * 0.0110, seed, 32)
    # Small scale: coastal variation (~20-35 hex spans)
    h2 = _smooth_noise(q * 0.0270, r * 0.0270, seed, 33)
    # Micro detail (~8-15 hex spans)
    h3 = _smooth_noise(q * 0.0700, r * 0.0700, seed, 34)

    # Continental scale dominates the land/ocean decision
    h = h0 * 0.52 + h1 * 0.28 + h2 * 0.13 + h3 * 0.07

    # Smoothstep to sharpen continent edges slightly
    h = h * h * (3.0 - 2.0 * h)

    # Fade to ocean at map edges
    nx = q / max(1, width - 1)
    ny = r / max(1, height - 1)
    edge = max(abs(nx * 2.0 - 1.0), abs(ny * 2.0 - 1.0))
    fade = max(0.0, (edge - 0.18) / 0.72)
    h = h * (1.0 - min(1.0, fade * fade))

    return h


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
        self._rng = random.Random(self.seed ^ SEED_XOR_MASK)
        self.faction_starts = self._generate_faction_starts()

    def _is_inside(self, q: int, r: int) -> bool:
        return 0 <= q < self.width and 0 <= r < self.height

    def _terrain_for(self, q: int, r: int) -> str:
        ny = r / max(1, self.height - 1)
        latitude = abs(ny - 0.5) * 2.0

        # Continental height drives the land/ocean split (gives continent clumps)
        h = _continent_height(q, r, self.seed, self.width, self.height)

        # Moisture / biome variation (medium scale)
        m = (_noise01(q, r, self.seed, 3) * 0.6) + (_noise01(q, r, self.seed, 4) * 0.4)
        river_noise = _noise01(q, r, self.seed, 5)

        if h < 0.28:
            return "ocean"
        if h < 0.36:
            return "coastal"
        if latitude > 0.78 and h > 0.42:
            return "tundra"
        if h > 0.76:
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
        rng = random.Random((self.seed * RESOURCE_SEED_MULTIPLIER) ^ (q * COORD_Q_HASH) ^ (r * COORD_R_HASH))
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
        min_dist = max(MIN_FACTION_START_DISTANCE, min(self.width, self.height) / FACTION_START_DISTANCE_DIVISOR)
        while len(starts) < len(factions) and attempts < MAX_FACTION_PLACEMENT_ATTEMPTS:
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
                for _ in range(MAX_FACTION_FALLBACK_ATTEMPTS):
                    q = self._rng.randrange(0, self.width)
                    r = self._rng.randrange(0, self.height)
                    if self._valid_start(q, r) and all(existing.q != q or existing.r != r for existing in starts.values()):
                        starts[key] = HexCoord(q=q, r=r)
                        break
                else:
                    for r in range(self.height):
                        for q in range(self.width):
                            if self._valid_start(q, r) and all(existing.q != q or existing.r != r for existing in starts.values()):
                                starts[key] = HexCoord(q=q, r=r)
                                break
                        if key in starts:
                            break
                    if key not in starts:
                        raise ValueError("Unable to place unique faction start positions on valid land tiles.")
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


# ---------------------------------------------------------------------------
# Worker / Trade-route / Faction-state models
# ---------------------------------------------------------------------------

WORKER_ROLES = ("trade", "gather", "expand", "war")

# Resources collected per land hex owned per turn (very small base values)
RESOURCE_GATHER_RATE: dict[str, float] = {
    "grain": 0.04,
    "gold":  0.01,
}

# Upkeep cost per worker per turn
WORKER_UPKEEP_GRAIN = 0.08
WORKER_UPKEEP_GOLD  = 0.02

# Cost to spawn a new worker
WORKER_SPAWN_GRAIN = 0.80
WORKER_SPAWN_GOLD  = 0.40

# Base housing units provided by the faction capital; each city improvement adds more
CAPITAL_HOUSING = 5
CITY_HOUSING    = 2

# Maximum workers the simulation will maintain per faction
MAX_WORKERS_PER_FACTION = 8

# Worker travels at most this many hexes per tick
WORKER_STEP_DISTANCE = 5


@dataclass
class Worker:
    """A mobile unit belonging to a faction."""
    id: str
    faction: str
    q: int
    r: int
    target_q: int
    target_r: int
    role: str  # one of WORKER_ROLES
    steps_remaining: int  # turns until arrival
    steps_total: int      # original journey length (for progress display)

    def to_dict(self) -> dict[str, Any]:
        color = FACTION_PROFILES.get(self.faction, {}).get("color", "#888888")
        progress = 1.0 - (self.steps_remaining / max(1, self.steps_total))
        return {
            "id": self.id,
            "faction": self.faction,
            "color": color,
            "q": self.q,
            "r": self.r,
            "targetQ": self.target_q,
            "targetR": self.target_r,
            "role": self.role,
            "stepsRemaining": self.steps_remaining,
            "progress": round(progress, 3),
        }


@dataclass
class TradeRoute:
    """An established trade connection between two locations."""
    id: str
    faction_a: str
    faction_b: str
    q1: int
    r1: int
    q2: int
    r2: int
    value: float   # economic value per turn
    active: bool = True
    age_turns: int = 0

    def to_dict(self) -> dict[str, Any]:
        color_a = FACTION_PROFILES.get(self.faction_a, {}).get("color", "#888888")
        color_b = FACTION_PROFILES.get(self.faction_b, {}).get("color", "#888888")
        return {
            "id": self.id,
            "factionA": self.faction_a,
            "factionB": self.faction_b,
            "colorA": color_a,
            "colorB": color_b,
            "q1": self.q1,
            "r1": self.r1,
            "q2": self.q2,
            "r2": self.r2,
            "value": round(self.value, 2),
            "active": self.active,
            "ageTurns": self.age_turns,
        }


@dataclass
class FactionState:
    """Dynamic per-faction economy and workforce state."""
    faction: str
    grain: float = 4.0
    gold: float  = 2.0
    housing_capacity: int = CAPITAL_HOUSING
    workers: list[Worker] = field(default_factory=list)
    hexes_owned: int = 0  # updated each tick from StrategicMapWorld

    @property
    def worker_count(self) -> int:
        return len(self.workers)

    @property
    def can_spawn_worker(self) -> bool:
        return (
            self.worker_count < min(self.housing_capacity, MAX_WORKERS_PER_FACTION)
            and self.grain >= WORKER_SPAWN_GRAIN
            and self.gold >= WORKER_SPAWN_GOLD
        )

    def collect_resources(self) -> None:
        """Accrue base resources proportional to hexes owned."""
        land_bonus = max(0, self.hexes_owned - 10) * 0.0005
        self.grain += RESOURCE_GATHER_RATE["grain"] + land_bonus
        self.gold  += RESOURCE_GATHER_RATE["gold"]  + land_bonus * 0.3

    def pay_upkeep(self) -> int:
        """Deduct worker upkeep; return number of workers disbanded due to starvation."""
        cost_grain = self.worker_count * WORKER_UPKEEP_GRAIN
        cost_gold  = self.worker_count * WORKER_UPKEEP_GOLD
        disbanded = 0
        if self.grain < cost_grain or self.gold < cost_gold:
            # Disband the most recently created worker
            if self.workers:
                self.workers.pop()
                disbanded += 1
            cost_grain = max(0.0, cost_grain - WORKER_UPKEEP_GRAIN)
            cost_gold  = max(0.0, cost_gold  - WORKER_UPKEEP_GOLD)
        self.grain = max(0.0, self.grain - cost_grain)
        self.gold  = max(0.0, self.gold  - cost_gold)
        return disbanded

    def to_dict(self) -> dict[str, Any]:
        return {
            "faction": self.faction,
            "grain": round(self.grain, 2),
            "gold": round(self.gold, 2),
            "housingCapacity": self.housing_capacity,
            "workerCount": self.worker_count,
            "hexesOwned": self.hexes_owned,
        }


def _hex_distance(q1: int, r1: int, q2: int, r2: int) -> float:
    """Approximate Euclidean distance between two offset-grid hexes."""
    return math.sqrt((q2 - q1) ** 2 + (r2 - r1) ** 2)


def _trade_route_value(q1: int, r1: int, q2: int, r2: int) -> float:
    """Trade route value scales with distance — longer routes are more lucrative."""
    dist = _hex_distance(q1, r1, q2, r2)
    # Value formula: base + log-scale distance bonus, capped
    value = 0.5 + math.log1p(dist / 20.0) * 1.8
    return round(min(value, 8.0), 2)


class StrategicWorldState:
    """
    Manages dynamic 4X simulation state: faction workers, trade routes, and
    faction resource economy.  This class is driven by the MarketEngine tick
    and references the static StrategicMapWorld for terrain / ownership data.
    """

    def __init__(self, map_world: StrategicMapWorld) -> None:
        self.map_world = map_world
        self._rng = random.Random(map_world.seed ^ 0xBEEF42)
        self.turn: int = 0
        self.trade_routes: list[TradeRoute] = []

        # Initialise one FactionState per faction
        self.faction_states: dict[str, FactionState] = {
            key: FactionState(faction=key)
            for key in FACTION_PROFILES
        }

        # Seed each faction with a couple of starting workers
        self._bootstrap_workers()

    # ------------------------------------------------------------------
    # Bootstrap
    # ------------------------------------------------------------------

    def _bootstrap_workers(self) -> None:
        for faction_key, fs in self.faction_states.items():
            start = self.map_world.faction_starts.get(faction_key)
            if start is None:
                continue
            # Spawn two workers: one trade-oriented, one expansion-oriented
            for role in ("trade", "expand"):
                target = self._choose_target(faction_key, role, start.q, start.r)
                if target is None:
                    continue
                dist = max(1, int(_hex_distance(start.q, start.r, target[0], target[1])))
                worker = Worker(
                    id=f"w-{faction_key}-{uuid.uuid4().hex[:6]}",
                    faction=faction_key,
                    q=start.q,
                    r=start.r,
                    target_q=target[0],
                    target_r=target[1],
                    role=role,
                    steps_remaining=dist,
                    steps_total=dist,
                )
                fs.workers.append(worker)
            # Deduct initial spawn costs
            fs.grain = max(0.0, fs.grain - WORKER_SPAWN_GRAIN * 2)
            fs.gold  = max(0.0, fs.gold  - WORKER_SPAWN_GOLD  * 2)

    # ------------------------------------------------------------------
    # Tick (called every ~3 s from MarketEngine)
    # ------------------------------------------------------------------

    def tick(self) -> None:
        self.turn += 1

        # Update hexes_owned from current faction territory shares
        total_cells = self.map_world.width * self.map_world.height
        for key, fs in self.faction_states.items():
            # We approximate using faction_starts distance — actual territory
            # percentages are tracked in MarketEngine; use a heuristic here
            fs.hexes_owned = max(10, int(total_cells * 0.06))  # placeholder; refined below

        # Resource collection
        for fs in self.faction_states.values():
            fs.collect_resources()
            fs.pay_upkeep()

        # Move workers
        for key, fs in self.faction_states.items():
            for worker in fs.workers:
                self._step_worker(worker, key)

        # Spawn new workers if affordable
        if self.turn % 4 == 0:
            for key, fs in self.faction_states.items():
                if fs.can_spawn_worker:
                    self._spawn_worker(key, fs)

        # Age and clean up stale trade routes
        self._age_trade_routes()

    def update_hex_ownership(self, faction_territories: dict[str, float]) -> None:
        """Refresh hexes_owned estimates from faction territory percentages."""
        total_cells = self.map_world.width * self.map_world.height
        for key, pct in faction_territories.items():
            if key in self.faction_states:
                self.faction_states[key].hexes_owned = max(10, int(total_cells * pct))
        # Update housing capacity based on hexes
        for key, fs in self.faction_states.items():
            fs.housing_capacity = CAPITAL_HOUSING + max(0, (fs.hexes_owned - 10) // 40) * CITY_HOUSING

    # ------------------------------------------------------------------
    # Worker helpers
    # ------------------------------------------------------------------

    def _step_worker(self, worker: Worker, faction_key: str) -> None:
        """Advance a worker one step toward its target."""
        if worker.steps_remaining <= 0:
            # Worker arrived — resolve effects then reassign
            self._worker_arrived(worker, faction_key)
            return

        # Move fractionally toward target (just update step counter; position
        # interpolation happens in the front end)
        worker.steps_remaining = max(0, worker.steps_remaining - WORKER_STEP_DISTANCE)

        # Linearly interpolate position toward target
        frac = 1.0 - (worker.steps_remaining / max(1, worker.steps_total))
        worker.q = worker.q + round((worker.target_q - worker.q) * min(frac, 1.0))
        worker.r = worker.r + round((worker.target_r - worker.r) * min(frac, 1.0))

    def _worker_arrived(self, worker: Worker, faction_key: str) -> None:
        """Handle worker arrival at destination."""
        if worker.role == "trade":
            # Establish a trade route from origin to destination
            origin_key = self._faction_at(worker.q, worker.r)
            dest_key   = self._faction_at(worker.target_q, worker.target_r)
            if origin_key and dest_key:
                self._ensure_trade_route(faction_key, origin_key, dest_key,
                                          worker.q, worker.r,
                                          worker.target_q, worker.target_r)
        elif worker.role in ("gather", "expand"):
            # Collect resources bonus (handled via collect_resources already)
            pass

        # Reassign: find a new mission
        start = self.map_world.faction_starts.get(faction_key)
        if start is None:
            return
        new_role = self._rng.choice(list(WORKER_ROLES))
        target = self._choose_target(faction_key, new_role, worker.q, worker.r)
        if target:
            dist = max(1, int(_hex_distance(worker.q, worker.r, target[0], target[1])))
            worker.target_q = target[0]
            worker.target_r = target[1]
            worker.role = new_role
            worker.steps_total = dist
            worker.steps_remaining = dist
        else:
            # Return to capital
            dist = max(1, int(_hex_distance(worker.q, worker.r, start.q, start.r)))
            worker.target_q = start.q
            worker.target_r = start.r
            worker.role = "trade"
            worker.steps_total = dist
            worker.steps_remaining = dist

    def _spawn_worker(self, faction_key: str, fs: FactionState) -> None:
        """Spawn a new worker at the faction capital."""
        start = self.map_world.faction_starts.get(faction_key)
        if start is None:
            return
        role = self._rng.choice(list(WORKER_ROLES))
        target = self._choose_target(faction_key, role, start.q, start.r)
        if target is None:
            return
        dist = max(1, int(_hex_distance(start.q, start.r, target[0], target[1])))
        worker = Worker(
            id=f"w-{faction_key}-{uuid.uuid4().hex[:6]}",
            faction=faction_key,
            q=start.q,
            r=start.r,
            target_q=target[0],
            target_r=target[1],
            role=role,
            steps_remaining=dist,
            steps_total=dist,
        )
        fs.workers.append(worker)
        fs.grain = max(0.0, fs.grain - WORKER_SPAWN_GRAIN)
        fs.gold  = max(0.0, fs.gold  - WORKER_SPAWN_GOLD)

    def _choose_target(
        self, faction_key: str, role: str, from_q: int, from_r: int
    ) -> tuple[int, int] | None:
        """Pick a sensible destination hex for a worker with the given role."""
        factions = list(FACTION_PROFILES.keys())
        other_factions = [f for f in factions if f != faction_key]

        if role == "trade" and other_factions:
            # Head toward another faction's capital
            target_faction = self._rng.choice(other_factions)
            target_start = self.map_world.faction_starts.get(target_faction)
            if target_start:
                return target_start.q, target_start.r

        if role == "expand":
            # Head toward a random land hex somewhat far away
            for _ in range(20):
                dq = self._rng.randint(-150, 150)
                dr = self._rng.randint(-150, 150)
                tq = max(0, min(self.map_world.width - 1, from_q + dq))
                tr = max(0, min(self.map_world.height - 1, from_r + dr))
                terrain = self.map_world._terrain_for(tq, tr)
                if terrain not in WATER_TERRAINS:
                    return tq, tr

        if role == "gather":
            # Head toward a plains/forest/river hex for resources
            for _ in range(20):
                dq = self._rng.randint(-80, 80)
                dr = self._rng.randint(-80, 80)
                tq = max(0, min(self.map_world.width - 1, from_q + dq))
                tr = max(0, min(self.map_world.height - 1, from_r + dr))
                terrain = self.map_world._terrain_for(tq, tr)
                if terrain in ("plains", "forest", "river"):
                    return tq, tr

        if role == "war" and other_factions:
            # Head toward a bordering enemy faction capital
            target_faction = self._rng.choice(other_factions)
            target_start = self.map_world.faction_starts.get(target_faction)
            if target_start:
                return target_start.q, target_start.r

        return None

    def _faction_at(self, q: int, r: int) -> str | None:
        """Return the faction that owns hex (q, r) according to Voronoi ownership."""
        terrain = self.map_world._terrain_for(q, r)
        return self.map_world._owner_for(q, r, terrain)

    # ------------------------------------------------------------------
    # Trade-route helpers
    # ------------------------------------------------------------------

    def _ensure_trade_route(
        self,
        worker_faction: str,
        faction_a: str,
        faction_b: str,
        q1: int, r1: int,
        q2: int, r2: int,
    ) -> None:
        """Create a trade route if one doesn't already exist between these endpoints."""
        for route in self.trade_routes:
            if (route.faction_a == faction_a and route.faction_b == faction_b) or \
               (route.faction_a == faction_b and route.faction_b == faction_a):
                route.active = True  # refresh
                return
        value = _trade_route_value(q1, r1, q2, r2)
        route = TradeRoute(
            id=f"rt-{uuid.uuid4().hex[:8]}",
            faction_a=faction_a,
            faction_b=faction_b,
            q1=q1, r1=r1,
            q2=q2, r2=r2,
            value=value,
            active=True,
            age_turns=0,
        )
        self.trade_routes.append(route)

    def _age_trade_routes(self) -> None:
        """Age trade routes and remove very stale inactive ones."""
        for route in self.trade_routes:
            route.age_turns += 1
        # Keep routes active for a long time; only drop routes older than 200 turns that
        # have been explicitly deactivated
        self.trade_routes = [r for r in self.trade_routes if r.active or r.age_turns < 200]
        # Cap total routes
        if len(self.trade_routes) > 40:
            self.trade_routes = sorted(self.trade_routes, key=lambda r: r.value, reverse=True)[:40]

    # ------------------------------------------------------------------
    # Snapshot for network transmission
    # ------------------------------------------------------------------

    def snapshot(self) -> dict[str, Any]:
        all_workers = [
            w.to_dict()
            for fs in self.faction_states.values()
            for w in fs.workers
        ]
        return {
            "turn": self.turn,
            "workers": all_workers,
            "tradeRoutes": [r.to_dict() for r in self.trade_routes if r.active],
            "factionStates": {key: fs.to_dict() for key, fs in self.faction_states.items()},
        }

