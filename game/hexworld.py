"""Hex grid world engine powering the Globe View.

All players share the same server-side world.  The world is generated once
from a deterministic seed and then evolved each tick via conquest, diplomacy,
and organic population growth.  Compact packed-int cells are transmitted to
clients as part of the market snapshot so the frontend can render a true
4X-style hex map.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Grid dimensions
# ---------------------------------------------------------------------------
GRID_WIDTH = 32
GRID_HEIGHT = 24

# ---------------------------------------------------------------------------
# Biome indices (4 bits, 0–15)
# ---------------------------------------------------------------------------
BIOME_OCEAN = 0
BIOME_PLAINS = 1
BIOME_FOREST = 2
BIOME_MOUNTAIN = 3
BIOME_DESERT = 4
BIOME_SWAMP = 5
BIOME_TUNDRA = 6
BIOME_COASTAL = 7

BIOME_NAMES = [
    "Ocean", "Plains", "Forest", "Mountain",
    "Desert", "Swamp", "Tundra", "Coastal",
]

# Resources produced by each biome
BIOME_RESOURCES: dict[int, dict[str, float]] = {
    BIOME_OCEAN:    {"trade": 0.5,  "fish": 0.3},
    BIOME_PLAINS:   {"grain": 1.5,  "labor": 1.2},
    BIOME_FOREST:   {"lumber": 2.0, "game": 1.3},
    BIOME_MOUNTAIN: {"minerals": 2.0, "stone": 1.5},
    BIOME_DESERT:   {"spice": 1.8,  "glass": 1.1},
    BIOME_SWAMP:    {"herbs": 1.8,  "chemicals": 1.4},
    BIOME_TUNDRA:   {"fur": 1.6,    "minerals": 0.8},
    BIOME_COASTAL:  {"trade": 2.0,  "fish": 1.8},
}

# Map resources → stock sectors that benefit from them
RESOURCE_SECTOR_AFFINITY: dict[str, list[str]] = {
    "grain":     ["Bog Commerce", "Swamp Food"],
    "labor":     ["Player Business"],
    "lumber":    ["Timber & Toads", "Toad Construction"],
    "minerals":  ["Croak Mining", "Lizard Industries"],
    "stone":     ["Toad Construction", "Lizard Industries"],
    "spice":     ["Bog Commerce"],
    "glass":     ["Lizard Industries"],
    "herbs":     ["Swamp Pharma"],
    "chemicals": ["Swamp Pharma", "Bug Biotech"],
    "fur":       ["Toad Fashion"],
    "trade":     ["Toad Finance", "Bog Commerce"],
    "fish":      ["Swamp Food", "Pond Harvest"],
    "game":      ["Swamp Food"],
}

# ---------------------------------------------------------------------------
# Faction constants
# ---------------------------------------------------------------------------
FACTION_KEYS = ["toad", "frog", "bug", "lizard", "bird", "fox", "shark"]

# 0 = neutral / water; 1–7 = faction
FACTION_IDX: dict[str, int] = {k: i + 1 for i, k in enumerate(FACTION_KEYS)}
FACTION_FROM_IDX: dict[int, str | None] = {0: None}
FACTION_FROM_IDX.update({i + 1: k for i, k in enumerate(FACTION_KEYS)})

# Conquest bonus per biome for each faction (multiplier on base chance)
FACTION_BIOME_AFFINITY: dict[str, dict[int, float]] = {
    "toad":   {BIOME_SWAMP: 1.8, BIOME_PLAINS: 1.4, BIOME_COASTAL: 1.3},
    "frog":   {BIOME_SWAMP: 1.6, BIOME_FOREST: 1.6, BIOME_COASTAL: 1.2},
    "bug":    {BIOME_SWAMP: 2.0, BIOME_FOREST: 1.5, BIOME_PLAINS: 1.1},
    "lizard": {BIOME_DESERT: 2.0, BIOME_MOUNTAIN: 1.7, BIOME_PLAINS: 0.9},
    "bird":   {BIOME_MOUNTAIN: 1.8, BIOME_TUNDRA: 1.6, BIOME_COASTAL: 1.3},
    "fox":    {BIOME_FOREST: 1.5, BIOME_MOUNTAIN: 1.3, BIOME_PLAINS: 1.4},
    "shark":  {BIOME_COASTAL: 2.2, BIOME_OCEAN: 2.5, BIOME_PLAINS: 0.5},
}

# ---------------------------------------------------------------------------
# Improvement indices (4 bits, 0–15)
# ---------------------------------------------------------------------------
IMP_NONE = 0
IMP_CITY = 1
IMP_TOWN = 2
IMP_FARM = 3
IMP_FORT = 4
IMP_MINE = 5
IMP_PORT = 6

IMPROVEMENT_NAMES = ["", "City", "Town", "Farm", "Fort", "Mine", "Port"]

# ---------------------------------------------------------------------------
# Territory name pool
# ---------------------------------------------------------------------------
TERRITORY_NAMES = [
    "Thornwood", "Bogmere", "Fernholt", "Stonereach", "Ashfields",
    "Duskhollow", "Grimfen", "Saltridge", "Ironmoor", "Mistpeak",
    "Clearwater", "Murkdale", "Craghaven", "Swiftcliff", "Emberpass",
    "Coldstep", "Verdant Flats", "Deepfen", "Ridgewatch", "Sunken Gully",
    "Thornvale", "Silvermarsh", "Dustcrown", "Cresthill", "Lowfen",
    "Greystone Pass", "Shallowmere", "Scorched Peak", "Longmoor", "Frostwatch",
    "Mudwater", "Dawnridge", "Ashfen", "Brambleholt", "Cliffwatch",
    "Stonepeak", "Rivermouth", "Coldfen", "Blightmoor", "Highrock",
    "Wetmarsh", "Dusthaven", "Ironpeak", "Greywood", "Saltfen",
    "Blackmoor", "Redcliff", "Sunhaven", "Windhollow", "Frostridge",
]


# ---------------------------------------------------------------------------
# Noise helpers (deterministic, no external dependency)
# ---------------------------------------------------------------------------

def _sinnoise(x: float, y: float) -> float:
    """Multi-octave sine noise in [-1, 1]."""
    v = (
        math.sin(x * 1.30 + y * 0.70) * 0.40
        + math.cos(x * 0.50 - y * 1.10) * 0.25
        + math.sin(x * 2.10 + y * 1.80) * 0.18
        + math.cos(x * 0.35 + y * 2.40) * 0.10
        + math.sin(x * 3.70 - y * 0.55) * 0.07
    )
    return max(-1.0, min(1.0, v))


# ---------------------------------------------------------------------------
# HexCell
# ---------------------------------------------------------------------------

@dataclass
class HexCell:
    q: int
    r: int
    biome: int = BIOME_OCEAN
    faction_idx: int = 0        # 0 = neutral
    improvement: int = IMP_NONE
    population: int = 0         # 0–127
    territory_name: str = ""
    business_ids: list[str] = field(default_factory=list)

    @property
    def is_land(self) -> bool:
        return self.biome != BIOME_OCEAN

    @property
    def faction(self) -> str | None:
        return FACTION_FROM_IDX.get(self.faction_idx)

    # -- Packing: biome(4) | faction(4) | improvement(4) | population(7) --

    def pack(self) -> int:
        return (
            (self.biome & 0xF)
            | ((self.faction_idx & 0xF) << 4)
            | ((self.improvement & 0xF) << 8)
            | ((max(0, min(127, self.population)) & 0x7F) << 12)
        )

    @classmethod
    def unpack(cls, q: int, r: int, packed: int, territory_name: str = "") -> "HexCell":
        return cls(
            q=q,
            r=r,
            biome=packed & 0xF,
            faction_idx=(packed >> 4) & 0xF,
            improvement=(packed >> 8) & 0xF,
            population=(packed >> 12) & 0x7F,
            territory_name=territory_name,
        )


# ---------------------------------------------------------------------------
# HexWorld
# ---------------------------------------------------------------------------

class HexWorld:
    """Shared hex grid world.  Generated once from a seed; evolved each tick."""

    def __init__(
        self,
        width: int = GRID_WIDTH,
        height: int = GRID_HEIGHT,
        seed: int = 12345,
    ) -> None:
        self.width = width
        self.height = height
        self.seed = seed
        self.cells: list[HexCell] = []
        self._business_locations: dict[str, tuple[int, int]] = {}
        self._rng = random.Random(seed + 1)   # separate stream for dynamics

    # -----------------------------------------------------------------------
    # Generation
    # -----------------------------------------------------------------------

    def generate(self) -> None:
        rng = random.Random(self.seed)
        ox, oy = rng.uniform(0, 100), rng.uniform(0, 100)
        mx, my = rng.uniform(0, 100), rng.uniform(0, 100)

        # ---- First pass: compute raw height & moisture arrays ----
        heights: list[float] = []
        moistures: list[float] = []
        for r in range(self.height):
            for q in range(self.width):
                nx = q / max(self.width - 1, 1)
                ny = r / max(self.height - 1, 1)
                cx, cy = nx * 2 - 1, ny * 2 - 1

                raw_h = _sinnoise(nx * 4.0 + ox, ny * 4.0 + oy)
                h = raw_h * 0.5 + 0.5  # [0, 1]
                # Soft edge-fade to create coast-line effect
                edge = max(abs(cx), abs(cy))
                fade = max(0.0, (edge - 0.30) / 0.70)
                h = h * (1.0 - fade * 0.88)
                heights.append(h)

                raw_m = _sinnoise(nx * 3.0 + mx, ny * 3.0 + my)
                moistures.append(raw_m * 0.5 + 0.5)

        # ---- Compute percentile thresholds on height ----
        sorted_h = sorted(heights)
        n = len(sorted_h)
        # ~62% ocean, ~10% coastal, ~28% land biomes
        ocean_t = sorted_h[int(n * 0.62)]
        coastal_t = sorted_h[int(n * 0.72)]
        mountain_t = sorted_h[int(n * 0.94)]

        # Normalise moisture to true [0,1] range for consistent biomes
        m_min = min(moistures)
        m_max = max(moistures)
        m_range = max(m_max - m_min, 1e-6)
        moistures = [(m - m_min) / m_range for m in moistures]

        # ---- Second pass: assign cells ----
        self.cells = []
        for idx, (h, moisture) in enumerate(zip(heights, moistures)):
            q = idx % self.width
            r = idx // self.width
            ny = r / max(self.height - 1, 1)
            latitude = abs(ny - 0.5) * 2.0

            if h < ocean_t:
                biome = BIOME_OCEAN
            elif h < coastal_t:
                biome = BIOME_COASTAL
            elif h >= mountain_t:
                biome = BIOME_TUNDRA if latitude > 0.65 else BIOME_MOUNTAIN
            elif latitude > 0.75 and h > (ocean_t + coastal_t) / 2 + 0.1:
                biome = BIOME_TUNDRA
            elif moisture < 0.25:
                biome = BIOME_DESERT
            elif moisture > 0.72 and h < (ocean_t + coastal_t) / 2 + 0.08:
                biome = BIOME_SWAMP
            elif moisture > 0.52:
                biome = BIOME_FOREST
            else:
                biome = BIOME_PLAINS

            pop = 0
            if biome != BIOME_OCEAN:
                nx2 = q / max(self.width - 1, 1)
                pop_noise = _sinnoise(nx2 * 6.0 + ox + 10, ny * 6.0 + oy + 10) * 0.5 + 0.5
                factor = {
                    BIOME_PLAINS: 1.5, BIOME_COASTAL: 1.6, BIOME_FOREST: 1.1,
                    BIOME_DESERT: 0.5, BIOME_MOUNTAIN: 0.7, BIOME_SWAMP: 0.9,
                    BIOME_TUNDRA: 0.4,
                }.get(biome, 1.0)
                pop = min(127, int(pop_noise * factor * 45))

            self.cells.append(HexCell(q=q, r=r, biome=biome, population=pop))

        self._assign_factions(rng)
        self._place_improvements(rng)
        self._assign_territory_names(rng)

    def _assign_factions(self, rng: random.Random) -> None:
        land = [c for c in self.cells if c.is_land]
        if not land:
            return

        # Spread faction seeds across the map with minimum separation
        seeds: list[tuple[int, int, str]] = []
        for faction in FACTION_KEYS:
            best: HexCell | None = None
            for _ in range(100):
                candidate = rng.choice(land)
                min_dist = (
                    min(
                        ((candidate.q - sq) ** 2 + (candidate.r - sr) ** 2) ** 0.5
                        for sq, sr, _ in seeds
                    )
                    if seeds
                    else 999
                )
                if min_dist >= 4 or not seeds:
                    best = candidate
                    break
            if best is None:
                best = rng.choice(land)
            seeds.append((best.q, best.r, faction))

        # Voronoi-style assignment weighted by biome affinity
        for cell in land:
            best_idx, best_score = 0, float("inf")
            for sq, sr, sfaction in seeds:
                d = ((cell.q - sq) ** 2 + (cell.r - sr) ** 2) ** 0.5
                aff = FACTION_BIOME_AFFINITY.get(sfaction, {}).get(cell.biome, 1.0)
                score = d / max(aff, 0.1)
                if score < best_score:
                    best_score = score
                    best_idx = FACTION_IDX[sfaction]
            cell.faction_idx = best_idx

    def _place_improvements(self, rng: random.Random) -> None:
        for cell in self.cells:
            if not cell.is_land or cell.population == 0:
                continue
            if cell.population >= 60:
                cell.improvement = IMP_CITY
            elif cell.population >= 35:
                if cell.biome == BIOME_COASTAL and rng.random() < 0.55:
                    cell.improvement = IMP_PORT
                else:
                    cell.improvement = IMP_TOWN
            elif cell.population >= 18:
                if cell.biome == BIOME_MOUNTAIN and rng.random() < 0.45:
                    cell.improvement = IMP_MINE
                elif cell.biome in (BIOME_PLAINS, BIOME_SWAMP) and rng.random() < 0.35:
                    cell.improvement = IMP_FARM
                elif cell.biome == BIOME_COASTAL and rng.random() < 0.30:
                    cell.improvement = IMP_PORT

    def _assign_territory_names(self, rng: random.Random) -> None:
        names = TERRITORY_NAMES.copy()
        rng.shuffle(names)
        name_idx = 0
        for cell in self.cells:
            if not cell.is_land:
                continue
            if cell.improvement in (IMP_CITY, IMP_TOWN, IMP_PORT) or cell.population >= 20:
                if name_idx < len(names):
                    cell.territory_name = names[name_idx]
                    name_idx += 1

    # -----------------------------------------------------------------------
    # Accessors
    # -----------------------------------------------------------------------

    def cell_at(self, q: int, r: int) -> HexCell | None:
        if 0 <= q < self.width and 0 <= r < self.height:
            return self.cells[r * self.width + q]
        return None

    def land_cells(self) -> list[HexCell]:
        return [c for c in self.cells if c.is_land]

    def neighbors(self, q: int, r: int) -> list[HexCell]:
        """Odd-r offset neighbors for pointy-top hex grid."""
        if r & 1:
            dirs = [(1, 0), (1, -1), (0, -1), (-1, 0), (0, 1), (1, 1)]
        else:
            dirs = [(1, 0), (0, -1), (-1, -1), (-1, 0), (-1, 1), (0, 1)]
        return [c for dq, dr in dirs if (c := self.cell_at(q + dq, r + dr)) is not None]

    # -----------------------------------------------------------------------
    # Dynamics
    # -----------------------------------------------------------------------

    def conquest_tick(
        self,
        faction_modifiers: dict[str, float] | None = None,
    ) -> list[tuple[int, int]]:
        """Run one tick of territorial conquest and population growth.

        Returns list of (q, r) coords that changed (for potential future
        delta-sending optimisation).
        """
        changed: list[tuple[int, int]] = []
        land = self.land_cells()
        if not land:
            return changed

        iterations = max(6, len(land) // 5)
        for _ in range(iterations):
            cell = self._rng.choice(land)
            neighbors = self.neighbors(cell.q, cell.r)
            # Candidates: land neighbors owned by a different (non-neutral) faction
            candidates = [
                n for n in neighbors
                if n.is_land and n.faction_idx != cell.faction_idx and n.faction_idx != 0
            ]
            if not candidates:
                continue
            challenger = self._rng.choice(candidates)
            cf = FACTION_FROM_IDX.get(challenger.faction_idx)
            if not cf:
                continue

            aff = FACTION_BIOME_AFFINITY.get(cf, {}).get(cell.biome, 1.0)
            mod = (faction_modifiers or {}).get(cf, 1.0)
            defense = {
                IMP_FORT: 0.30,
                IMP_CITY: 0.20,
                IMP_TOWN: 0.10,
            }.get(cell.improvement, 0.0)
            pop_def = min(0.25, cell.population / 400.0)
            chance = 0.30 + (aff - 1.0) * 0.12 + (mod - 1.0) * 0.08 - defense - pop_def
            chance = max(0.04, min(0.70, chance))

            if self._rng.random() < chance:
                cell.faction_idx = challenger.faction_idx
                cell.population = max(0, cell.population - self._rng.randint(0, 4))
                challenger.population = min(127, challenger.population + self._rng.randint(0, 2))
                changed.append((cell.q, cell.r))

        # Organic population growth for a sample of inhabited cells
        sample_k = max(1, len(land) // 15)
        for cell in self._rng.choices(land, k=sample_k):
            if cell.faction_idx == 0:
                continue
            delta = self._rng.randint(-1, 2)
            cell.population = max(1, min(127, cell.population + delta))
            # Auto-promote improvements based on population
            if cell.population >= 60 and cell.improvement == IMP_TOWN:
                cell.improvement = IMP_CITY
                changed.append((cell.q, cell.r))
            elif cell.population >= 35 and cell.improvement == IMP_NONE:
                if cell.biome == BIOME_COASTAL:
                    cell.improvement = IMP_PORT
                else:
                    cell.improvement = IMP_TOWN
                changed.append((cell.q, cell.r))
            elif cell.population < 10 and cell.improvement in (IMP_TOWN, IMP_CITY):
                cell.improvement = IMP_NONE
                changed.append((cell.q, cell.r))

        return changed

    def faction_hex_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {f: 0 for f in FACTION_KEYS}
        for cell in self.cells:
            f = cell.faction
            if f:
                counts[f] += 1
        return counts

    def faction_territories(self) -> dict[str, float]:
        counts = self.faction_hex_counts()
        total = sum(counts.values()) or 1
        return {f: counts[f] / total for f in FACTION_KEYS}

    def resource_sector_modifier(self, sector: str) -> float:
        """Return a small stock multiplier (0.96–1.04) from world resources."""
        relevant: set[str] = {
            res for res, sects in RESOURCE_SECTOR_AFFINITY.items()
            if sector in sects
        }
        if not relevant:
            return 1.0
        bonus = 0.0
        imp_boost = {
            IMP_CITY: 1.6, IMP_TOWN: 1.2, IMP_PORT: 1.4,
            IMP_FARM: 1.3, IMP_MINE: 1.5,
        }
        for cell in self.cells:
            if not cell.is_land or cell.faction_idx == 0:
                continue
            ib = imp_boost.get(cell.improvement, 1.0)
            for res in relevant:
                amt = BIOME_RESOURCES.get(cell.biome, {}).get(res, 0.0)
                if amt > 0:
                    bonus += (amt - 1.0) * ib * (cell.population / 127.0) * 0.00025
        return max(0.96, min(1.04, 1.0 + bonus))

    # -----------------------------------------------------------------------
    # Business placement
    # -----------------------------------------------------------------------

    def assign_business(
        self,
        business_id: str,
        preferred_faction: str | None = None,
    ) -> tuple[int, int, str]:
        """Place a business on the hex grid.

        Returns ``(q, r, territory_name)``.
        """
        self.remove_business(business_id)
        land = self.land_cells()

        candidates: list[HexCell] = []
        if preferred_faction:
            fidx = FACTION_IDX.get(preferred_faction, 0)
            candidates = [
                c for c in land
                if c.faction_idx == fidx and c.improvement != IMP_NONE
            ]
            if not candidates:
                candidates = [c for c in land if c.faction_idx == fidx]

        if not candidates:
            candidates = [c for c in land if c.improvement != IMP_NONE]
        if not candidates:
            candidates = land
        if not candidates:
            return (-1, -1, "Unknown Territory")

        cell = self._rng.choice(candidates)
        cell.business_ids.append(business_id)
        self._business_locations[business_id] = (cell.q, cell.r)
        territory = cell.territory_name or f"{BIOME_NAMES[cell.biome]} Sector"
        return (cell.q, cell.r, territory)

    def remove_business(self, business_id: str) -> None:
        if business_id in self._business_locations:
            q, r = self._business_locations.pop(business_id)
            cell = self.cell_at(q, r)
            if cell and business_id in cell.business_ids:
                cell.business_ids.remove(business_id)

    def business_territory(self, business_id: str) -> str | None:
        loc = self._business_locations.get(business_id)
        if loc is None:
            return None
        cell = self.cell_at(*loc)
        if cell is None:
            return None
        return cell.territory_name or f"{BIOME_NAMES[cell.biome]} Sector"

    # -----------------------------------------------------------------------
    # Serialisation
    # -----------------------------------------------------------------------

    def to_save(self) -> dict[str, Any]:
        return {
            "width": self.width,
            "height": self.height,
            "seed": self.seed,
            "cells": [c.pack() for c in self.cells],
            # Sparse territory-name dict keyed by "q,r"
            "territories": {
                f"{c.q},{c.r}": c.territory_name
                for c in self.cells
                if c.territory_name
            },
            "businessLocations": {
                bid: list(loc)
                for bid, loc in self._business_locations.items()
            },
        }

    @classmethod
    def from_save(cls, payload: dict[str, Any]) -> "HexWorld":
        world = cls(
            width=int(payload.get("width", GRID_WIDTH)),
            height=int(payload.get("height", GRID_HEIGHT)),
            seed=int(payload.get("seed", 12345)),
        )
        packed: list[int] = payload.get("cells", [])
        territories: dict[str, str] = payload.get("territories", {})
        expected = world.width * world.height

        if packed and len(packed) == expected:
            world.cells = []
            for idx, val in enumerate(packed):
                q, r = idx % world.width, idx // world.width
                name = territories.get(f"{q},{r}", "")
                world.cells.append(HexCell.unpack(q, r, int(val), name))
        else:
            world.generate()

        # Restore business locations
        for bid, loc in payload.get("businessLocations", {}).items():
            if isinstance(loc, (list, tuple)) and len(loc) == 2:
                q, r = int(loc[0]), int(loc[1])
                world._business_locations[bid] = (q, r)
                cell = world.cell_at(q, r)
                if cell and bid not in cell.business_ids:
                    cell.business_ids.append(bid)

        return world

    def to_snapshot(self) -> dict[str, Any]:
        """Compact payload included in the market snapshot."""
        territories = {
            f"{c.q},{c.r}": c.territory_name
            for c in self.cells
            if c.territory_name
        }
        businesses: dict[str, Any] = {}
        for bid, (q, r) in self._business_locations.items():
            cell = self.cell_at(q, r)
            if cell:
                businesses[bid] = {
                    "q": q,
                    "r": r,
                    "biome": cell.biome,
                    "faction": cell.faction,
                    "territory": cell.territory_name or f"{BIOME_NAMES[cell.biome]} Sector",
                }
        return {
            "width": self.width,
            "height": self.height,
            "cells": [c.pack() for c in self.cells],
            "territories": territories,
            "businesses": businesses,
        }
