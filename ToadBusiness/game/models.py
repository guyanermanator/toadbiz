from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any

from .catalog import StockTemplate


STARTING_CASH = 250.0
BASE_HOURLY_INCOME = 16.50
MAX_HISTORY_POINTS = 420
DEFAULT_PLAYER_COLOR = "#000080"
DEFAULT_MESSAGE_COLOR = "#111111"
DEFAULT_CHAT_FONT = "MS Sans Serif"


def now_ts() -> float:
    return time.time()


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def money(value: float) -> float:
    return round(float(value), 2)


def volatility_label(volatility: float) -> str:
    if volatility < 0.25:
        return "Low"
    if volatility < 0.45:
        return "Moderate"
    if volatility < 0.65:
        return "High"
    return "Extreme"


def risk_score(volatility: float, beta: float, allocation_ratio: float = 1.0) -> float:
    return clamp((volatility * 60.0) + (abs(beta - 1.0) * 20.0) + (allocation_ratio * 20.0), 0.0, 100.0)


def risk_label(score: float) -> str:
    if score < 30:
        return "Low"
    if score < 55:
        return "Moderate"
    if score < 78:
        return "High"
    return "Extreme"


@dataclass
class PricePoint:
    ts: float
    price: float

    def to_dict(self) -> dict[str, float]:
        return {"ts": round(self.ts, 3), "price": money(self.price)}

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "PricePoint":
        return cls(ts=float(payload["ts"]), price=float(payload["price"]))


@dataclass
class Stock:
    id: str
    symbol: str
    name: str
    sector: str
    industry: str
    market_cap: str
    price: float
    previous_close: float
    opening_price: float
    baseline_price: float
    volatility: float
    beta: float
    liquidity: float
    max_volume: int
    ceo: str = "Interim Bean Counter"
    moon_sensitive: bool = False
    last_quip: str = "Freshly listed and already making accountants sweat."
    last_event: str = ""
    last_event_severity: str = "normal"
    day_volume: int = 0
    trade_pressure: float = 0.0
    history: list[PricePoint] = field(default_factory=list)

    @classmethod
    def from_template(cls, template: StockTemplate, ts: float | None = None) -> "Stock":
        created_at = ts or now_ts()
        return cls(
            id=template.id,
            symbol=template.symbol,
            name=template.name,
            sector=template.sector,
            industry=template.industry,
            market_cap=template.market_cap,
            price=template.starting_price,
            previous_close=template.starting_price,
            opening_price=template.starting_price,
            baseline_price=template.starting_price,
            volatility=template.volatility,
            beta=template.beta,
            liquidity=template.liquidity,
            max_volume=template.max_volume,
            ceo=template.ceo,
            moon_sensitive=template.moon_sensitive,
            history=[PricePoint(created_at, template.starting_price)],
        )

    def merge_template(self, template: StockTemplate) -> None:
        self.symbol = template.symbol
        self.name = template.name
        self.sector = template.sector
        self.industry = template.industry
        self.market_cap = template.market_cap
        self.volatility = template.volatility
        self.beta = template.beta
        self.liquidity = template.liquidity
        self.max_volume = template.max_volume
        self.ceo = template.ceo if not self.ceo else self.ceo
        self.moon_sensitive = template.moon_sensitive

    @property
    def percent_change(self) -> float:
        if self.previous_close <= 0:
            return 0.0
        return ((self.price - self.previous_close) / self.previous_close) * 100.0

    @property
    def direction(self) -> str:
        if self.percent_change > 0.03:
            return "up"
        if self.percent_change < -0.03:
            return "down"
        return "flat"

    @property
    def vol_label(self) -> str:
        return volatility_label(self.volatility)

    def add_history_point(self, ts: float | None = None) -> None:
        point_ts = ts or now_ts()
        if self.history and point_ts - self.history[-1].ts < 0.85:
            self.history[-1] = PricePoint(point_ts, self.price)
        else:
            self.history.append(PricePoint(point_ts, self.price))
        if len(self.history) > MAX_HISTORY_POINTS:
            self.history = self.history[-MAX_HISTORY_POINTS:]

    def apply_price_multiplier(self, multiplier: float) -> None:
        self.price = money(max(0.01, self.price * multiplier))

    def to_dict(self, held_by_players: int = 0, include_history: bool = True) -> dict[str, Any]:
        remaining_volume = max(0, self.max_volume - held_by_players)
        payload: dict[str, Any] = {
            "id": self.id,
            "symbol": self.symbol,
            "name": self.name,
            "sector": self.sector,
            "industry": self.industry,
            "marketCap": self.market_cap,
            "price": money(self.price),
            "previousClose": money(self.previous_close),
            "openingPrice": money(self.opening_price),
            "percentChange": round(self.percent_change, 2),
            "direction": self.direction,
            "volatility": round(self.volatility, 3),
            "volatilityLabel": self.vol_label,
            "beta": round(self.beta, 2),
            "liquidity": round(self.liquidity, 2),
            "maxVolume": self.max_volume,
            "remainingVolume": remaining_volume,
            "heldByPlayers": held_by_players,
            "dayVolume": self.day_volume,
            "riskScore": round(risk_score(self.volatility, self.beta), 1),
            "ceo": self.ceo,
            "moonSensitive": self.moon_sensitive,
            "quip": self.last_quip,
            "lastEvent": self.last_event,
            "lastEventSeverity": self.last_event_severity,
        }
        if include_history:
            payload["history"] = [point.to_dict() for point in self.history]
        return payload

    def to_save(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "price": money(self.price),
            "previousClose": money(self.previous_close),
            "openingPrice": money(self.opening_price),
            "baselinePrice": money(self.baseline_price),
            "symbol": self.symbol,
            "name": self.name,
            "sector": self.sector,
            "industry": self.industry,
            "marketCap": self.market_cap,
            "volatility": self.volatility,
            "beta": self.beta,
            "liquidity": self.liquidity,
            "maxVolume": self.max_volume,
            "ceo": self.ceo,
            "moonSensitive": self.moon_sensitive,
            "lastQuip": self.last_quip,
            "lastEvent": self.last_event,
            "lastEventSeverity": self.last_event_severity,
            "dayVolume": self.day_volume,
            "tradePressure": self.trade_pressure,
            "history": [point.to_dict() for point in self.history[-MAX_HISTORY_POINTS:]],
        }

    @classmethod
    def from_save(cls, template: StockTemplate, payload: dict[str, Any]) -> "Stock":
        stock = cls.from_template(template)
        stock.price = float(payload.get("price", template.starting_price))
        stock.previous_close = float(payload.get("previousClose", template.starting_price))
        stock.opening_price = float(payload.get("openingPrice", stock.price))
        stock.baseline_price = float(payload.get("baselinePrice", template.starting_price))
        stock.day_volume = int(payload.get("dayVolume", 0))
        stock.trade_pressure = float(payload.get("tradePressure", 0.0))
        stock.ceo = str(payload.get("ceo", template.ceo))
        stock.moon_sensitive = bool(payload.get("moonSensitive", template.moon_sensitive))
        stock.last_quip = str(payload.get("lastQuip", stock.last_quip))
        stock.last_event = str(payload.get("lastEvent", ""))
        stock.last_event_severity = str(payload.get("lastEventSeverity", "normal"))
        history = payload.get("history", [])
        stock.history = [PricePoint.from_dict(point) for point in history if "ts" in point and "price" in point]
        if not stock.history:
            stock.history = [PricePoint(now_ts(), stock.price)]
        stock.merge_template(template)
        return stock

    @classmethod
    def from_dynamic_save(cls, payload: dict[str, Any]) -> "Stock":
        price = float(payload.get("price", payload.get("baselinePrice", 10.0)))
        stock = cls(
            id=str(payload["id"]),
            symbol=str(payload.get("symbol", "PLY"))[:6].upper(),
            name=str(payload.get("name", "Player Business")),
            sector=str(payload.get("sector", "Player Business")),
            industry=str(payload.get("industry", "Owner-operated chaos")),
            market_cap=str(payload.get("marketCap", "Micro Cap")),
            price=price,
            previous_close=float(payload.get("previousClose", price)),
            opening_price=float(payload.get("openingPrice", price)),
            baseline_price=float(payload.get("baselinePrice", price)),
            volatility=float(payload.get("volatility", 0.55)),
            beta=float(payload.get("beta", 1.35)),
            liquidity=float(payload.get("liquidity", 0.52)),
            max_volume=int(payload.get("maxVolume", 8000)),
            ceo=str(payload.get("ceo", "Local Owner")),
            moon_sensitive=bool(payload.get("moonSensitive", False)),
            last_quip=str(payload.get("lastQuip", "Owner is still finding the good stapler.")),
            last_event=str(payload.get("lastEvent", "")),
            last_event_severity=str(payload.get("lastEventSeverity", "normal")),
            day_volume=int(payload.get("dayVolume", 0)),
            trade_pressure=float(payload.get("tradePressure", 0.0)),
        )
        history = payload.get("history", [])
        stock.history = [PricePoint.from_dict(point) for point in history if "ts" in point and "price" in point]
        if not stock.history:
            stock.history = [PricePoint(now_ts(), stock.price)]
        return stock


@dataclass
class Position:
    shares: int = 0
    cost_basis: float = 0.0
    realized_pnl: float = 0.0

    @property
    def average_cost(self) -> float:
        if self.shares <= 0:
            return 0.0
        return self.cost_basis / self.shares

    def buy(self, shares: int, cost: float) -> None:
        self.shares += shares
        self.cost_basis = money(self.cost_basis + cost)

    def sell(self, shares: int, proceeds: float) -> float:
        shares_to_sell = min(shares, self.shares)
        if shares_to_sell <= 0:
            return 0.0
        avg_cost = self.average_cost
        removed_basis = avg_cost * shares_to_sell
        realized = proceeds - removed_basis
        self.shares -= shares_to_sell
        self.cost_basis = money(max(0.0, self.cost_basis - removed_basis))
        if self.shares == 0:
            self.cost_basis = 0.0
        self.realized_pnl = money(self.realized_pnl + realized)
        return realized

    def to_save(self) -> dict[str, Any]:
        return {
            "shares": self.shares,
            "costBasis": money(self.cost_basis),
            "realizedPnl": money(self.realized_pnl),
        }

    @classmethod
    def from_save(cls, payload: dict[str, Any]) -> "Position":
        return cls(
            shares=int(payload.get("shares", 0)),
            cost_basis=float(payload.get("costBasis", 0.0)),
            realized_pnl=float(payload.get("realizedPnl", 0.0)),
        )


@dataclass
class Renter:
    name: str
    quality: str
    rent_multiplier: float

    def to_save(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "quality": self.quality,
            "rentMultiplier": self.rent_multiplier,
        }

    @classmethod
    def from_save(cls, payload: dict[str, Any]) -> "Renter":
        return cls(
            name=str(payload.get("name", "Tenant")),
            quality=str(payload.get("quality", "normal")),
            rent_multiplier=float(payload.get("rentMultiplier", 1.0)),
        )


@dataclass
class RealEstateAsset:
    id: str
    template_id: str
    name: str
    value: float
    base_rent: float
    rent_per_hour: float
    level: int = 1
    renter: Renter | None = None

    @property
    def upgrade_cost(self) -> float:
        return money(max(75.0, self.value * 0.22) * math.pow(1.7, self.level - 1))

    def hourly_income(self) -> float:
        multiplier = self.renter.rent_multiplier if self.renter else 0.0
        return money(self.rent_per_hour * multiplier)

    def to_save(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "templateId": self.template_id,
            "name": self.name,
            "value": money(self.value),
            "baseRent": money(self.base_rent),
            "rentPerHour": money(self.rent_per_hour),
            "level": self.level,
            "renter": self.renter.to_save() if self.renter else None,
        }

    @classmethod
    def from_save(cls, payload: dict[str, Any]) -> "RealEstateAsset":
        renter_payload = payload.get("renter")
        return cls(
            id=str(payload.get("id", "")),
            template_id=str(payload.get("templateId", "shabby-shack")),
            name=str(payload.get("name", "Shabby Shack")),
            value=float(payload.get("value", 120.0)),
            base_rent=float(payload.get("baseRent", 10.0)),
            rent_per_hour=float(payload.get("rentPerHour", 10.0)),
            level=int(payload.get("level", 1)),
            renter=Renter.from_save(renter_payload) if isinstance(renter_payload, dict) else None,
        )


@dataclass
class BusinessAsset:
    id: str
    template_id: str
    name: str
    value: float
    income_per_hour: float
    level: int = 1
    stock_id: str = ""

    @property
    def upgrade_cost(self) -> float:
        return money(max(60.0, self.value * 0.25) * math.pow(1.75, self.level - 1))

    def to_save(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "templateId": self.template_id,
            "name": self.name,
            "value": money(self.value),
            "incomePerHour": money(self.income_per_hour),
            "level": self.level,
            "stockId": self.stock_id,
        }

    @classmethod
    def from_save(cls, payload: dict[str, Any]) -> "BusinessAsset":
        return cls(
            id=str(payload.get("id", "")),
            template_id=str(payload.get("templateId", "lemonade-stand")),
            name=str(payload.get("name", "Lemonade Stand")),
            value=float(payload.get("value", 90.0)),
            income_per_hour=float(payload.get("incomePerHour", 1.5)),
            level=int(payload.get("level", 1)),
            stock_id=str(payload.get("stockId", "")),
        )


@dataclass
class Player:
    name: str
    color: str = DEFAULT_PLAYER_COLOR
    message_color: str = DEFAULT_MESSAGE_COLOR
    chat_font: str = DEFAULT_CHAT_FONT
    cash: float = STARTING_CASH
    hourly_income: float = BASE_HOURLY_INCOME
    income_level: int = 1
    positions: dict[str, Position] = field(default_factory=dict)
    real_estate: list[RealEstateAsset] = field(default_factory=list)
    businesses: list[BusinessAsset] = field(default_factory=list)
    sabotage_cooldowns: dict[str, float] = field(default_factory=dict)
    last_income_at: float = field(default_factory=now_ts)
    created_at: float = field(default_factory=now_ts)

    def accrue_income(self, ts: float | None = None, hourly_rate: float | None = None) -> None:
        current_ts = ts or now_ts()
        if self.last_income_at <= 0:
            self.last_income_at = current_ts
            return
        elapsed = max(0.0, current_ts - self.last_income_at)
        if elapsed <= 0:
            return
        rate = self.hourly_income if hourly_rate is None else hourly_rate
        self.cash = money(self.cash + ((rate / 3600.0) * elapsed))
        self.last_income_at = current_ts

    @property
    def next_income_upgrade_cost(self) -> float:
        return money(75.0 * math.pow(1.72, self.income_level - 1))

    def upgrade_income(self) -> float:
        cost = self.next_income_upgrade_cost
        if self.cash < cost:
            raise ValueError(f"Need ${cost:.2f} to upgrade hourly income.")
        self.cash = money(self.cash - cost)
        self.income_level += 1
        self.hourly_income = money(BASE_HOURLY_INCOME * math.pow(1.18, self.income_level - 1))
        return cost

    def position_for(self, stock_id: str) -> Position:
        if stock_id not in self.positions:
            self.positions[stock_id] = Position()
        return self.positions[stock_id]

    def remove_empty_positions(self) -> None:
        self.positions = {
            stock_id: position
            for stock_id, position in self.positions.items()
            if position.shares > 0 or abs(position.realized_pnl) >= 0.01
        }

    def to_save(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "color": self.color,
            "messageColor": self.message_color,
            "chatFont": self.chat_font,
            "cash": money(self.cash),
            "hourlyIncome": money(self.hourly_income),
            "incomeLevel": self.income_level,
            "positions": {stock_id: position.to_save() for stock_id, position in self.positions.items()},
            "realEstate": [asset.to_save() for asset in self.real_estate],
            "businesses": [asset.to_save() for asset in self.businesses],
            "sabotageCooldowns": self.sabotage_cooldowns,
            "lastIncomeAt": self.last_income_at,
            "createdAt": self.created_at,
        }

    @classmethod
    def from_save(cls, payload: dict[str, Any]) -> "Player":
        positions = {
            stock_id: Position.from_save(position)
            for stock_id, position in payload.get("positions", {}).items()
        }
        return cls(
            name=str(payload.get("name", "Player")),
            color=str(payload.get("color", DEFAULT_PLAYER_COLOR)),
            message_color=str(payload.get("messageColor", DEFAULT_MESSAGE_COLOR)),
            chat_font=str(payload.get("chatFont", DEFAULT_CHAT_FONT)),
            cash=float(payload.get("cash", STARTING_CASH)),
            hourly_income=float(payload.get("hourlyIncome", BASE_HOURLY_INCOME)),
            income_level=int(payload.get("incomeLevel", 1)),
            positions=positions,
            real_estate=[RealEstateAsset.from_save(asset) for asset in payload.get("realEstate", [])],
            businesses=[BusinessAsset.from_save(asset) for asset in payload.get("businesses", [])],
            sabotage_cooldowns={
                str(key): float(value)
                for key, value in payload.get("sabotageCooldowns", {}).items()
            },
            last_income_at=float(payload.get("lastIncomeAt", now_ts())),
            created_at=float(payload.get("createdAt", now_ts())),
        )
