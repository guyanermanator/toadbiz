from __future__ import annotations

import math
import random
import re
import time
import uuid
from typing import Any

from .assets import (
    BUSINESS_CATALOG,
    CEO_POOL,
    REAL_ESTATE_CATALOG,
    SABOTAGE_CATALOG,
    TENANT_POOL,
    business_template,
    real_estate_template,
    sabotage_template,
)
from .models import (
    BusinessAsset,
    Player,
    RealEstateAsset,
    Renter,
    Stock,
    money,
    risk_label,
    risk_score,
)


NAME_PATTERN = re.compile(r"[^a-zA-Z0-9 _.-]+")
COLOR_PATTERN = re.compile(r"^#[0-9a-fA-F]{6}$")
MAX_NEWS = 80
ALLOWED_CHAT_FONTS = {
    "MS Sans Serif",
    "Tahoma",
    "Verdana",
    "Arial",
    "Courier New",
    "Lucida Console",
    "Terminal",
    "Consolas",
}


def normalized_filter_text(value: str) -> str:
    translated = (
        value.lower()
        .replace("1", "i")
        .replace("!", "i")
        .replace("3", "e")
        .replace("4", "a")
        .replace("@", "a")
        .replace("0", "o")
        .replace("$", "s")
    )
    return re.sub(r"[^a-z]+", "", translated)


def contains_disallowed_word(value: str) -> bool:
    normalized = normalized_filter_text(value)
    blocked = (
        "".join(["n", "i", "g", "g", "e", "r"]),
        "".join(["n", "i", "g", "g", "a"]),
    )
    return any(word in normalized for word in blocked)


def clean_color(raw_color: str) -> str:
    if COLOR_PATTERN.match(raw_color or ""):
        return raw_color.lower()
    return "#000080"


def clean_font(raw_font: str) -> str:
    font = str(raw_font or "").strip()
    if font in ALLOWED_CHAT_FONTS:
        return font
    return "MS Sans Serif"


def stock_symbol_from_name(name: str) -> str:
    letters = "".join(char for char in name.upper() if char.isalpha())
    return (letters[:4] or "BIZ")[:6]


class MarketEngine:
    def __init__(
        self,
        stocks: dict[str, Stock],
        players: dict[str, Player],
        chat_log: list[dict[str, Any]],
        news_log: list[dict[str, Any]] | None = None,
    ) -> None:
        self.stocks = stocks
        self.players = players
        self.chat_log = chat_log[-60:]
        self.news_log = (news_log or [])[-MAX_NEWS:]
        self.connected_players = 0
        self.active_player_counts: dict[str, int] = {}
        self.sabotage_pressure: dict[str, float] = {}
        self.last_tick = time.time()
        self.next_event_at = self.last_tick + random.uniform(18.0, 36.0)
        self._dirty = False
        # Faction territory tracking (lightweight: just % control per faction)
        self.faction_territories = {
            "toad": 0.15, "frog": 0.15, "bug": 0.15,
            "lizard": 0.15, "bird": 0.15, "fox": 0.15, "shark": 0.10,
        }
        self.last_faction_update = self.last_tick
        self.ensure_business_stocks()

    @property
    def dirty(self) -> bool:
        return self._dirty

    def mark_clean(self) -> None:
        self._dirty = False

    def sanitize_name(self, raw_name: str, field: str = "name") -> str:
        name = NAME_PATTERN.sub("", raw_name).strip()
        if not name:
            raise ValueError(f"Choose a {field} first.")
        if contains_disallowed_word(name):
            raise ValueError(f"That {field} is not allowed.")
        return name[:32]

    def player_key(self, name: str) -> str:
        return name.strip().lower()

    def join_player(
        self,
        raw_name: str,
        raw_color: str = "",
        raw_message_color: str = "",
        raw_chat_font: str = "",
    ) -> Player:
        name = self.sanitize_name(raw_name, "player name")[:24]
        color = clean_color(raw_color)
        key = self.player_key(name)
        if key not in self.players:
            self.players[key] = Player(name=name, color=color)
            self._dirty = True
        player = self.players[key]
        player.name = name
        player.color = color
        player.message_color = clean_color(raw_message_color) if raw_message_color else color
        player.chat_font = clean_font(raw_chat_font)
        
        # Accrue income for offline time before marking player as active
        current_ts = time.time()
        player.accrue_income(current_ts, self.total_hourly_income(player))
        player.last_income_at = current_ts
        
        self.active_player_counts[key] = self.active_player_counts.get(key, 0) + 1
        return player

    def update_player_profile(
        self,
        current_name: str,
        raw_name: str,
        raw_color: str = "",
        raw_message_color: str = "",
        raw_chat_font: str = "",
    ) -> Player:
        current_key = self.player_key(current_name)
        if current_key not in self.players:
            raise ValueError("Join the market before updating profile.")
        player = self.players[current_key]
        new_name = self.sanitize_name(raw_name or player.name, "player name")[:24]
        new_key = self.player_key(new_name)
        if new_key != current_key and new_key in self.players:
            raise ValueError("That player name is already in use.")
        if new_key != current_key:
            self.players[new_key] = player
            del self.players[current_key]
            if current_key in self.active_player_counts:
                self.active_player_counts[new_key] = self.active_player_counts.pop(current_key)
        player.name = new_name
        player.color = clean_color(raw_color) if raw_color else player.color
        player.message_color = clean_color(raw_message_color) if raw_message_color else player.message_color
        player.chat_font = clean_font(raw_chat_font)
        self._dirty = True
        return player

    def leave_player(self, player_name: str | None) -> None:
        if not player_name:
            return
        key = self.player_key(player_name)
        player = self.players.get(key)
        if player and self.active_player_counts.get(key, 0) > 0:
            player.accrue_income(time.time(), self.total_hourly_income(player))
        count = self.active_player_counts.get(key, 0) - 1
        if count <= 0:
            self.active_player_counts.pop(key, None)
        else:
            self.active_player_counts[key] = count

    def tick(self) -> bool:
        current_ts = time.time()
        elapsed = max(0.1, current_ts - self.last_tick)
        self.last_tick = current_ts

        for key in list(self.active_player_counts):
            player = self.players.get(key)
            if player:
                player.accrue_income(current_ts, self.total_hourly_income(player))

        self.update_assets(elapsed)

        changed = False
        for stock in self.stocks.values():
            random_step = random.gauss(0.0, stock.volatility * 0.0018) * min(2.0, elapsed)
            baseline_pull = ((stock.baseline_price - stock.price) / max(stock.baseline_price, 0.01)) * 0.00055 * elapsed
            pressure = stock.trade_pressure * 0.08 * elapsed
            ceo_bias = self.ceo_bias(stock.ceo) * 0.004 * elapsed
            moon_pull = self.moon_multiplier(current_ts) if stock.moon_sensitive else 0.0
            multiplier = 1.0 + random_step + baseline_pull + pressure + ceo_bias + moon_pull
            if abs(multiplier - 1.0) > 0.00005:
                stock.apply_price_multiplier(multiplier)
                changed = True
            stock.trade_pressure *= max(0.0, 1.0 - (0.18 * elapsed))
            stock.add_history_point(current_ts)
            if stock.direction == "up" and not stock.last_event:
                stock.last_quip = "Buyers are bumping elbows at the counter."
            elif stock.direction == "down" and not stock.last_event:
                stock.last_quip = "Sellers are backing away like the floor is sticky."

        # Update faction territories periodically
        if current_ts - self.last_faction_update >= 4.0:  # Every ~4 seconds
            self.update_faction_territories(current_ts)
            self.last_faction_update = current_ts
            changed = True

        if current_ts >= self.next_event_at:
            self.trigger_random_event(current_ts)
            self.next_event_at = current_ts + random.uniform(22.0, 52.0)
            changed = True

        if changed or self.players:
            self._dirty = True
        return changed

    def update_assets(self, elapsed: float) -> None:
        for player in self.players.values():
            for asset in player.real_estate:
                template = real_estate_template(asset.template_id)
                appreciation = template.appreciation if template else 0.000012
                tenant_drag = 0.99998 if asset.renter and asset.renter.quality == "shady" else 1.0
                asset.value = money(asset.value * (1.0 + appreciation * elapsed) * tenant_drag)
                if random.random() < 0.0009 * elapsed and asset.renter is None:
                    asset.renter = self.random_renter()
            for business in player.businesses:
                stock = self.stocks.get(business.stock_id)
                if stock:
                    implied_value = stock.price * stock.max_volume * 0.004
                    business.value = money((business.value * 0.995) + (implied_value * 0.005))
                    business.income_per_hour = money(max(0.5, business.income_per_hour * (1.0 + stock.percent_change / 100000.0)))

    def ceo_bias(self, ceo_name: str) -> float:
        for ceo in CEO_POOL:
            if ceo["name"] == ceo_name:
                return float(ceo["bias"])
        return 0.0

    def update_faction_territories(self, current_ts: float) -> None:
        """Lightweight faction territory update using random drift and player influence."""
        # Simple random walk for territories to create dynamic movement
        factions = list(self.faction_territories.keys())
        
        for faction in factions:
            # Random drift (±1-3% per update, scaled by time)
            drift = random.gauss(0, 0.015)
            self.faction_territories[faction] = max(0.05, min(0.25, 
                self.faction_territories[faction] + drift
            ))
        
        # Normalize to sum to 1.0
        total = sum(self.faction_territories.values())
        for faction in factions:
            self.faction_territories[faction] /= total

    def moon_multiplier(self, current_ts: float) -> float:
        cycle_seconds = 180.0
        phase = (current_ts % cycle_seconds) / cycle_seconds
        return math.sin(phase * math.tau) * 0.0015

    def moon_phase_name(self, current_ts: float | None = None) -> str:
        phase = ((current_ts or time.time()) % 180.0) / 180.0
        if phase < 0.125 or phase >= 0.875:
            return "New Moon"
        if phase < 0.375:
            return "Waxing Moon"
        if phase < 0.625:
            return "Full Moon"
        return "Waning Moon"

    def held_counts(self) -> dict[str, int]:
        held = {stock_id: 0 for stock_id in self.stocks}
        for player in self.players.values():
            for stock_id, position in player.positions.items():
                if stock_id in held:
                    held[stock_id] += position.shares
        return held

    def max_buyable(self, player: Player, stock: Stock) -> int:
        held = self.held_counts().get(stock.id, 0)
        remaining_volume = max(0, stock.max_volume - held)
        cash_limit = int(player.cash // stock.price)
        return max(0, min(cash_limit, remaining_volume))

    def buy(self, player_name: str, stock_id: str, shares: int) -> dict[str, Any]:
        player = self.require_player(player_name)
        stock = self.require_stock(stock_id)
        shares = self._normalize_share_count(shares)
        max_buy = self.max_buyable(player, stock)
        if shares > max_buy:
            raise ValueError(f"Only {max_buy} shares are available to buy right now.")
        cost = money(stock.price * shares)
        if player.cash < cost:
            raise ValueError("Not enough cash for that order.")

        player.cash = money(player.cash - cost)
        player.position_for(stock.id).buy(shares, cost)
        stock.day_volume += shares
        impact = self.apply_trade_impact(stock, shares, side="buy")
        stock.last_quip = "Demand poked the price upward."
        stock.add_history_point()
        self._dirty = True
        return {"stock": stock.name, "shares": shares, "cost": cost, "side": "buy", "impactPercent": impact}

    def buy_max(self, player_name: str, stock_id: str) -> dict[str, Any]:
        player = self.require_player(player_name)
        stock = self.require_stock(stock_id)
        shares = self.max_buyable(player, stock)
        if shares <= 0:
            raise ValueError("No shares are available with your current cash.")
        return self.buy(player.name, stock_id, shares)

    def sell(self, player_name: str, stock_id: str, shares: int) -> dict[str, Any]:
        player = self.require_player(player_name)
        stock = self.require_stock(stock_id)
        shares = self._normalize_share_count(shares)
        position = player.position_for(stock.id)
        if shares > position.shares:
            raise ValueError(f"You only own {position.shares} shares.")

        proceeds = money(stock.price * shares)
        realized = position.sell(shares, proceeds)
        player.cash = money(player.cash + proceeds)
        player.remove_empty_positions()
        stock.day_volume += shares
        impact = self.apply_trade_impact(stock, shares, side="sell")
        stock.last_quip = "A sell wave made the price wobble."
        stock.add_history_point()
        self._dirty = True
        return {
            "stock": stock.name,
            "shares": shares,
            "proceeds": proceeds,
            "realizedPnl": money(realized),
            "side": "sell",
            "impactPercent": impact,
        }

    def sell_max(self, player_name: str, stock_id: str) -> dict[str, Any]:
        player = self.require_player(player_name)
        stock = self.require_stock(stock_id)
        shares = player.position_for(stock.id).shares
        if shares <= 0:
            raise ValueError("You do not own shares in this stock.")
        return self.sell(player.name, stock_id, shares)

    def upgrade_income(self, player_name: str) -> dict[str, Any]:
        player = self.require_player(player_name)
        cost = player.upgrade_income()
        self._dirty = True
        return {"cost": cost, "hourlyIncome": player.hourly_income, "incomeLevel": player.income_level}

    def buy_real_estate(self, player_name: str, template_id: str) -> dict[str, Any]:
        player = self.require_player(player_name)
        template = real_estate_template(template_id)
        if not template:
            raise ValueError("That property is not available.")
        if player.cash < template.cost:
            raise ValueError(f"Need ${template.cost:.2f} to buy that property.")
        player.cash = money(player.cash - template.cost)
        asset = RealEstateAsset(
            id=f"re-{uuid.uuid4().hex[:10]}",
            template_id=template.id,
            name=template.name,
            value=template.starting_value,
            base_rent=template.base_rent,
            rent_per_hour=template.base_rent,
            renter=self.random_renter(),
        )
        player.real_estate.append(asset)
        self.add_news(f"{player.name} bought {asset.name}", "Rent checks begin immediately if the tenant remembers.", "normal")
        self._dirty = True
        return {"name": asset.name, "cost": template.cost}

    def sell_real_estate(self, player_name: str, asset_id: str) -> dict[str, Any]:
        player = self.require_player(player_name)
        asset = self.find_real_estate(player, asset_id)
        player.real_estate = [item for item in player.real_estate if item.id != asset.id]
        player.cash = money(player.cash + asset.value)
        self._dirty = True
        return {"name": asset.name, "value": money(asset.value)}

    def upgrade_real_estate(self, player_name: str, asset_id: str) -> dict[str, Any]:
        player = self.require_player(player_name)
        asset = self.find_real_estate(player, asset_id)
        cost = asset.upgrade_cost
        if player.cash < cost:
            raise ValueError(f"Need ${cost:.2f} for that property upgrade.")
        player.cash = money(player.cash - cost)
        asset.level += 1
        asset.value = money(asset.value * 1.18)
        asset.rent_per_hour = money(asset.rent_per_hour * 1.22)
        self._dirty = True
        return {"name": asset.name, "cost": cost}

    def evict_renter(self, player_name: str, asset_id: str) -> dict[str, Any]:
        player = self.require_player(player_name)
        asset = self.find_real_estate(player, asset_id)
        old_name = asset.renter.name if asset.renter else "Nobody"
        asset.renter = self.random_renter()
        self._dirty = True
        return {"property": asset.name, "oldRenter": old_name, "newRenter": asset.renter.name}

    def set_rent(self, player_name: str, asset_id: str, rent_per_hour: float) -> dict[str, Any]:
        player = self.require_player(player_name)
        asset = self.find_real_estate(player, asset_id)
        rent = money(max(1.0, min(float(rent_per_hour), asset.base_rent * 8.0)))
        asset.rent_per_hour = rent
        if asset.renter and rent > asset.base_rent * 2.5 and random.random() < 0.35:
            asset.renter = None
        self._dirty = True
        return {"property": asset.name, "rentPerHour": rent}

    def buy_business(self, player_name: str, template_id: str) -> dict[str, Any]:
        player = self.require_player(player_name)
        template = business_template(template_id)
        if not template:
            raise ValueError("That business is not available.")
        if player.cash < template.cost:
            raise ValueError(f"Need ${template.cost:.2f} to buy that business.")
        player.cash = money(player.cash - template.cost)
        sequence = len(player.businesses) + 1
        business_id = f"biz-{self.player_key(player.name).replace(' ', '-')}-{sequence}-{uuid.uuid4().hex[:5]}"
        stock_id = f"player-{business_id}"
        business = BusinessAsset(
            id=business_id,
            template_id=template.id,
            name=f"{player.name}'s {template.name}",
            value=template.starting_value,
            income_per_hour=template.income_per_hour,
            stock_id=stock_id,
        )
        stock = Stock(
            id=stock_id,
            symbol=stock_symbol_from_name(business.name),
            name=business.name,
            sector=template.sector,
            industry=template.industry,
            market_cap="Player Micro Cap",
            price=template.starting_price,
            previous_close=template.starting_price,
            opening_price=template.starting_price,
            baseline_price=template.starting_price,
            volatility=0.58,
            beta=1.42,
            liquidity=0.48,
            max_volume=template.max_volume,
            ceo=player.name,
            last_quip="A player-owned business has entered the exchange.",
        )
        stock.add_history_point()
        player.businesses.append(business)
        self.stocks[stock.id] = stock
        self.add_news(f"{business.name} listed publicly", "The exchange made room next to the questionable snacks.", "normal", stock_id=stock.id)
        self._dirty = True
        return {"name": business.name, "cost": template.cost, "stockId": stock.id}

    def upgrade_business(self, player_name: str, business_id: str) -> dict[str, Any]:
        player = self.require_player(player_name)
        business = self.find_business(player, business_id)
        cost = business.upgrade_cost
        if player.cash < cost:
            raise ValueError(f"Need ${cost:.2f} for that business upgrade.")
        player.cash = money(player.cash - cost)
        business.level += 1
        business.value = money(business.value * 1.24)
        business.income_per_hour = money(business.income_per_hour * 1.28)
        stock = self.stocks.get(business.stock_id)
        if stock:
            stock.baseline_price = money(stock.baseline_price * 1.08)
            stock.apply_price_multiplier(1.035)
            stock.last_quip = "Owner investment made the shelves look less haunted."
        self._dirty = True
        return {"name": business.name, "cost": cost}

    def rename_business(self, player_name: str, business_id: str, new_name: str) -> dict[str, Any]:
        player = self.require_player(player_name)
        business = self.find_business(player, business_id)
        clean_name = self.sanitize_name(new_name, "business name")[:36]
        business.name = clean_name
        stock = self.stocks.get(business.stock_id)
        if stock:
            stock.name = clean_name
            stock.symbol = stock_symbol_from_name(clean_name)
            stock.ceo = player.name
        self._dirty = True
        return {"name": clean_name}

    def sell_business(self, player_name: str, business_id: str) -> dict[str, Any]:
        player = self.require_player(player_name)
        business = self.find_business(player, business_id)
        player.businesses = [item for item in player.businesses if item.id != business.id]
        player.cash = money(player.cash + business.value)
        stock = self.stocks.get(business.stock_id)
        if stock:
            stock.last_quip = "The founder cashed out and left a box of receipts."
        self._dirty = True
        return {"name": business.name, "value": money(business.value)}

    def sabotage(self, player_name: str, stock_id: str, option_id: str) -> dict[str, Any]:
        player = self.require_player(player_name)
        stock = self.require_stock(stock_id)
        option = sabotage_template(option_id)
        if not option:
            raise ValueError("That sabotage option is not available.")
        now = time.time()
        cooldown_until = player.sabotage_cooldowns.get(option.id, 0.0)
        if cooldown_until > now:
            remaining = int(cooldown_until - now)
            raise ValueError(f"Sabotage cooldown has {remaining}s remaining.")
        cost = self.sabotage_cost(stock, option.id)
        if player.cash < cost:
            raise ValueError(f"Need ${cost:.2f} for that influence.")
        player.cash = money(player.cash - cost)
        player.sabotage_cooldowns[option.id] = now + option.cooldown_seconds
        self.sabotage_pressure[stock.id] = self.sabotage_pressure.get(stock.id, 0.0) + option.power
        self.add_news(
            f"{stock.symbol} influence campaign funded",
            f"{option.event_hint}; no outcome is guaranteed.",
            "normal",
            stock_id=stock.id,
        )
        self._dirty = True
        return {"stock": stock.name, "option": option.name, "cost": cost}

    def sabotage_cost(self, stock: Stock, option_id: str) -> float:
        option = sabotage_template(option_id)
        if not option:
            return 0.0
        market_proxy = stock.price * stock.max_volume * 0.01
        return money(option.base_cost + market_proxy * 0.015)

    def add_chat(self, player_name: str, message: str) -> dict[str, Any]:
        player = self.require_player(player_name)
        clean_message = str(message).strip()
        if not clean_message:
            raise ValueError("Chat message is empty.")
        clean_message = clean_message[:220]
        entry = {
            "ts": round(time.time(), 3),
            "name": player.name,
            "color": player.color,
            "messageColor": player.message_color,
            "chatFont": player.chat_font,
            "message": clean_message,
        }
        self.chat_log.append(entry)
        self.chat_log = self.chat_log[-60:]
        self._dirty = True
        return entry

    def estimate_trade_impact(self, stock: Stock, shares: int) -> float:
        volume_ratio = shares / max(stock.max_volume, 1)
        return min(0.18, volume_ratio * (0.9 + stock.volatility) / max(stock.liquidity, 0.1) * 3.4)

    def apply_trade_impact(self, stock: Stock, shares: int, side: str) -> float:
        impact = self.estimate_trade_impact(stock, shares)
        if side == "sell":
            stock.apply_price_multiplier(1.0 - impact)
            stock.trade_pressure -= impact * 0.45
            return round(-impact * 100.0, 3)
        stock.apply_price_multiplier(1.0 + impact)
        stock.trade_pressure += impact * 0.45
        return round(impact * 100.0, 3)

    def trigger_random_event(self, current_ts: float) -> None:
        if self.sabotage_pressure and random.random() < 0.62:
            stock_id = max(self.sabotage_pressure, key=lambda key: self.sabotage_pressure[key])
            pressure = self.sabotage_pressure.pop(stock_id, 0.0)
            stock = self.stocks.get(stock_id)
            if stock:
                self.trigger_sabotage_event(stock, pressure)
                return

        roll = random.random()
        if roll < 0.15:
            self.trigger_faction_event()
        elif roll < 0.45:
            self.trigger_sector_event(positive=False)
        elif roll < 0.70:
            self.trigger_sector_event(positive=True)
        elif roll < 0.85:
            self.trigger_ceo_event()
        else:
            self.trigger_stock_event()

    def trigger_faction_event(self) -> None:
        """Generate faction war or diplomacy events."""
        faction_names = {
            "toad": "Toad Nation",
            "frog": "Frog Collective",
            "bug": "Bug Swarm",
            "lizard": "Lizard Empire",
            "bird": "Bird Confederation",
            "fox": "Fox Syndicate",
            "shark": "Shark Dominion",
        }
        factions = list(self.faction_territories.keys())
        
        is_war = random.random() < 0.55  # 55% war, 45% diplomacy
        
        if is_war:
            # Random war between two neighboring factions
            faction_a = random.choice(factions)
            faction_b = random.choice([f for f in factions if f != faction_a])
            name_a = faction_names[faction_a]
            name_b = faction_names[faction_b]
            
            war_events = [
                (f"<strong>{name_a} declares war on {name_b}</strong>", "territorial disputes escalate into open conflict on the frontier", -0.008, -0.008),
                (f"<strong>Border clash: {name_a} vs {name_b}</strong>", "skirmishes reported along contested boundaries", -0.006, -0.006),
                (f"<strong>{name_a} siege reported</strong>", f"forces surrounding {name_b} settlements in dispute", -0.010, -0.005),
            ]
            title, body, impact_a, impact_b = random.choice(war_events)
            
            # Adjust territory control based on war
            control_a = self.faction_territories[faction_a]
            control_b = self.faction_territories[faction_b]
            total = control_a + control_b
            
            # Territory shifts slightly toward aggressor
            shift = random.uniform(0.005, 0.015)
            self.faction_territories[faction_a] = max(0.05, control_a + shift)
            self.faction_territories[faction_b] = max(0.05, control_b - shift)
            
            # Renormalize
            total_control = sum(self.faction_territories.values())
            for f in factions:
                self.faction_territories[f] /= total_control
            
            self.add_news(title, body, "major", impact=min(impact_a, impact_b) * 100.0)
        else:
            # Diplomacy: pacts, treaties, alliances
            faction_a = random.choice(factions)
            faction_b = random.choice([f for f in factions if f != faction_a])
            name_a = faction_names[faction_a]
            name_b = faction_names[faction_b]
            
            diplomacy_events = [
                (f"<strong>{name_a} and {name_b} sign trade pact</strong>", "economic cooperation agreement strengthens both economies", 0.003),
                (f"<strong>Peace treaty: {name_a}-{name_b}</strong>", "decades-long territorial dispute resolved through mediation", 0.004),
                (f"<strong>{name_a} proposes alliance with {name_b}</strong>", "unified political bloc emerges to counter regional threats", 0.002),
            ]
            title, body, impact = random.choice(diplomacy_events)
            self.add_news(title, body, "normal", impact=impact * 100.0)

    def trigger_sabotage_event(self, stock: Stock, pressure: float) -> None:
        events = [
            ("Leaked chat messages", "private messages made the boardroom sound like a snack fight", -0.055, "major"),
            ("CEO farted in public", "the microphone was somehow still on", -0.025, "normal"),
            ("CEO choked on a cookie", "investors question biscuit safety protocols", -0.035, "major"),
            ("CEO fell out of window", "officials blame a very aggressive swivel chair", -0.075, "major"),
            ("CEO assassination scandal", "rumors of a shadow contract freeze the ticker", -0.12, "major"),
        ]
        title, body, base_impact, severity = random.choice(events)
        impact = max(-0.22, base_impact - min(0.1, pressure * 0.035))
        stock.apply_price_multiplier(1.0 + impact)
        stock.last_event = title
        stock.last_event_severity = severity
        stock.last_quip = body
        self.add_news(f"{stock.symbol}: {title}", body, severity, stock_id=stock.id, impact=impact * 100.0)

    def trigger_sector_event(self, positive: bool) -> None:
        sectors = sorted({stock.sector for stock in self.stocks.values()})
        if not sectors:
            return
        sector = random.choice(sectors)
        if positive:
            title = f"{sector} sector rally"
            body = random.choice(
                [
                    "analysts discover a spreadsheet cell that makes everyone look smarter",
                    "consumer demand rises after a catchy jingle refuses to leave town",
                    "regulators approve a suspiciously cheerful subsidy",
                ]
            )
            impact = random.uniform(0.018, 0.055)
            severity = "normal"
        else:
            title = f"{sector} sector disaster"
            body = random.choice(
                [
                    "a natural disaster snarls suppliers and damages inventory",
                    "a warehouse flood turns quarterly guidance into soup",
                    "a compliance audit finds six unlabeled folders and one cursed binder",
                ]
            )
            impact = -random.uniform(0.022, 0.075)
            severity = "major"
        for stock in self.stocks.values():
            if stock.sector == sector:
                stock.apply_price_multiplier(1.0 + impact)
                stock.last_event = title
                stock.last_event_severity = severity
                stock.last_quip = body
        self.add_news(title, body, severity, sector=sector, impact=impact * 100.0)

    def trigger_ceo_event(self) -> None:
        if not self.stocks:
            return
        stock = random.choice(list(self.stocks.values()))
        new_ceo = random.choice(CEO_POOL)
        old_ceo = stock.ceo
        stock.ceo = str(new_ceo["name"])
        impact = float(new_ceo["bias"]) * random.uniform(1.8, 3.6)
        stock.apply_price_multiplier(1.0 + impact)
        title = f"{stock.symbol}: CEO change"
        body = f"{old_ceo} is out; {stock.ceo} {new_ceo['quip']}."
        stock.last_event = title
        stock.last_event_severity = "major" if abs(impact) > 0.025 else "normal"
        stock.last_quip = body
        self.add_news(title, body, stock.last_event_severity, stock_id=stock.id, impact=impact * 100.0)

    def trigger_stock_event(self) -> None:
        if not self.stocks:
            return
        stock = random.choice(list(self.stocks.values()))
        positive = random.random() > 0.45
        if positive:
            title = f"{stock.symbol}: surprise win"
            body = random.choice(
                [
                    "a shipment arrived on time and everyone is taking credit",
                    "a customer bought the premium package by mistake",
                    "the CEO found a motivational sticky note under the desk",
                ]
            )
            impact = random.uniform(0.018, 0.06)
            severity = "normal"
        else:
            title = f"{stock.symbol}: bad vibes"
            body = random.choice(
                [
                    "the office coffee machine unionized",
                    "a key presentation was saved as final_final_bad2.ppt",
                    "inventory was counted twice and still feels wrong",
                ]
            )
            impact = -random.uniform(0.016, 0.055)
            severity = "normal"
        stock.apply_price_multiplier(1.0 + impact)
        stock.last_event = title
        stock.last_event_severity = severity
        stock.last_quip = body
        self.add_news(title, body, severity, stock_id=stock.id, impact=impact * 100.0)

    def add_news(
        self,
        title: str,
        body: str,
        severity: str,
        stock_id: str | None = None,
        sector: str | None = None,
        impact: float | None = None,
    ) -> None:
        self.news_log.append(
            {
                "ts": round(time.time(), 3),
                "title": title,
                "body": body,
                "severity": severity,
                "stockId": stock_id,
                "sector": sector,
                "impact": round(impact, 2) if impact is not None else None,
            }
        )
        self.news_log = self.news_log[-MAX_NEWS:]
        self._dirty = True

    def ensure_business_stocks(self) -> None:
        for player in self.players.values():
            for business in player.businesses:
                if business.stock_id and business.stock_id not in self.stocks:
                    price = max(1.0, business.value / 40.0)
                    self.stocks[business.stock_id] = Stock(
                        id=business.stock_id,
                        symbol=stock_symbol_from_name(business.name),
                        name=business.name,
                        sector="Player Business",
                        industry="Owner-operated chaos",
                        market_cap="Player Micro Cap",
                        price=price,
                        previous_close=price,
                        opening_price=price,
                        baseline_price=price,
                        volatility=0.58,
                        beta=1.42,
                        liquidity=0.48,
                        max_volume=7000,
                        ceo=player.name,
                    )

    def random_renter(self) -> Renter:
        tenant = random.choice(TENANT_POOL)
        return Renter(
            name=str(tenant["name"]),
            quality=str(tenant["quality"]),
            rent_multiplier=float(tenant["rentMultiplier"]),
        )

    def find_real_estate(self, player: Player, asset_id: str) -> RealEstateAsset:
        for asset in player.real_estate:
            if asset.id == asset_id:
                return asset
        raise ValueError("That property is not owned by this player.")

    def find_business(self, player: Player, business_id: str) -> BusinessAsset:
        for business in player.businesses:
            if business.id == business_id:
                return business
        raise ValueError("That business is not owned by this player.")

    def require_player(self, player_name: str) -> Player:
        key = self.player_key(player_name)
        if key not in self.players:
            raise ValueError("Join the market before trading.")
        player = self.players[key]
        if key in self.active_player_counts:
            player.accrue_income(time.time(), self.total_hourly_income(player))
        return player

    def require_stock(self, stock_id: str) -> Stock:
        if stock_id not in self.stocks:
            raise ValueError("That stock is not listed.")
        return self.stocks[stock_id]

    def _normalize_share_count(self, shares: int) -> int:
        try:
            normalized = int(shares)
        except (TypeError, ValueError) as exc:
            raise ValueError("Shares must be a whole number.") from exc
        if normalized <= 0:
            raise ValueError("Shares must be greater than zero.")
        if normalized > 1_000_000:
            raise ValueError("That order is too large.")
        return normalized

    def total_hourly_income(self, player: Player) -> float:
        property_income = sum(asset.hourly_income() for asset in player.real_estate)
        business_income = sum(asset.income_per_hour for asset in player.businesses)
        return money(player.hourly_income + property_income + business_income)

    def player_net_worth(self, player: Player) -> float:
        stock_value = 0.0
        for stock_id, position in player.positions.items():
            stock = self.stocks.get(stock_id)
            if stock:
                stock_value += stock.price * position.shares
        property_value = sum(asset.value for asset in player.real_estate)
        business_value = sum(asset.value for asset in player.businesses)
        return money(player.cash + stock_value + property_value + business_value)

    def market_snapshot(self) -> dict[str, Any]:
        held = self.held_counts()
        stocks = [stock.to_dict(held_by_players=held.get(stock.id, 0), include_history=True) for stock in self.stocks.values()]
        gainers = sorted(stocks, key=lambda item: item["percentChange"], reverse=True)[:5]
        losers = sorted(stocks, key=lambda item: item["percentChange"])[:5]
        ticker = sorted(stocks, key=lambda item: abs(item["percentChange"]), reverse=True)
        leaderboard = sorted(
            (
                {
                    "name": player.name,
                    "color": player.color,
                    "messageColor": player.message_color,
                    "chatFont": player.chat_font,
                    "netWorth": self.player_net_worth(player),
                    "online": key in self.active_player_counts,
                }
                for key, player in self.players.items()
            ),
            key=lambda item: item["netWorth"],
            reverse=True,
        )[:10]
        return {
            "serverTime": round(time.time(), 3),
            "globalTime": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
            "moonPhase": self.moon_phase_name(),
            "connectedPlayers": self.connected_players,
            "stocks": stocks,
            "leaderboard": leaderboard,
            "news": list(reversed(self.news_log[-18:])),
            "realEstateCatalog": [template.__dict__ for template in REAL_ESTATE_CATALOG],
            "businessCatalog": [template.__dict__ for template in BUSINESS_CATALOG],
            "sabotageOptions": [
                {**template.__dict__, "costByStock": {stock.id: self.sabotage_cost(stock, template.id) for stock in self.stocks.values()}}
                for template in SABOTAGE_CATALOG
            ],
            "movers": {
                "gainers": [{"id": item["id"], "name": item["name"], "symbol": item["symbol"], "percentChange": item["percentChange"]} for item in gainers],
                "losers": [{"id": item["id"], "name": item["name"], "symbol": item["symbol"], "percentChange": item["percentChange"]} for item in losers],
            },
            "ticker": [
                {
                    "id": item["id"],
                    "name": item["name"],
                    "symbol": item["symbol"],
                    "price": item["price"],
                    "percentChange": item["percentChange"],
                    "direction": item["direction"],
                    "quip": item["quip"],
                }
                for item in ticker
            ],
            "factionTerritories": self.faction_territories,
        }

    def player_snapshot(self, player_name: str) -> dict[str, Any]:
        player = self.require_player(player_name)
        positions = []
        total_market_value = 0.0
        total_cost = 0.0
        total_realized = 0.0

        for stock_id, position in player.positions.items():
            if stock_id not in self.stocks:
                continue
            stock = self.stocks[stock_id]
            market_value = stock.price * position.shares
            unrealized = market_value - position.cost_basis
            total_market_value += market_value
            total_cost += position.cost_basis
            total_realized += position.realized_pnl
            allocation_ratio = 0.0
            if market_value > 0:
                allocation_ratio = market_value / max(1.0, player.cash + total_market_value)
            score = risk_score(stock.volatility, stock.beta, allocation_ratio)
            positions.append(
                {
                    "stockId": stock.id,
                    "symbol": stock.symbol,
                    "name": stock.name,
                    "shares": position.shares,
                    "averageCost": money(position.average_cost),
                    "currentPrice": money(stock.price),
                    "marketValue": money(market_value),
                    "costBasis": money(position.cost_basis),
                    "unrealizedPnl": money(unrealized),
                    "realizedPnl": money(position.realized_pnl),
                    "percentPnl": round((unrealized / position.cost_basis) * 100.0, 2) if position.cost_basis > 0 else 0.0,
                    "riskScore": round(score, 1),
                    "riskLabel": risk_label(score),
                }
            )

        property_value = sum(asset.value for asset in player.real_estate)
        business_value = sum(asset.value for asset in player.businesses)
        net_worth = player.cash + total_market_value + property_value + business_value
        total_hourly = self.total_hourly_income(player)
        current_ts = time.time()
        return {
            "name": player.name,
            "color": player.color,
            "messageColor": player.message_color,
            "chatFont": player.chat_font,
            "cash": money(player.cash),
            "hourlyIncome": money(player.hourly_income),
            "totalHourlyIncome": total_hourly,
            "incomeActive": self.player_key(player.name) in self.active_player_counts,
            "incomeLevel": player.income_level,
            "incomePerSecond": round(total_hourly / 3600.0, 5),
            "nextIncomeUpgradeCost": player.next_income_upgrade_cost,
            "positions": sorted(positions, key=lambda item: item["marketValue"], reverse=True),
            "realEstate": [
                {
                    "id": asset.id,
                    "templateId": asset.template_id,
                    "name": asset.name,
                    "value": money(asset.value),
                    "rentPerHour": money(asset.rent_per_hour),
                    "incomePerHour": asset.hourly_income(),
                    "level": asset.level,
                    "upgradeCost": asset.upgrade_cost,
                    "renter": asset.renter.to_save() if asset.renter else None,
                }
                for asset in player.real_estate
            ],
            "businesses": [
                {
                    "id": asset.id,
                    "templateId": asset.template_id,
                    "name": asset.name,
                    "value": money(asset.value),
                    "incomePerHour": money(asset.income_per_hour),
                    "level": asset.level,
                    "upgradeCost": asset.upgrade_cost,
                    "stockId": asset.stock_id,
                    "stockPrice": money(self.stocks[asset.stock_id].price) if asset.stock_id in self.stocks else 0.0,
                }
                for asset in player.businesses
            ],
            "sabotageCooldowns": {
                option_id: max(0, int(until - current_ts))
                for option_id, until in player.sabotage_cooldowns.items()
            },
            "portfolio": {
                "marketValue": money(total_market_value),
                "costBasis": money(total_cost),
                "propertyValue": money(property_value),
                "businessValue": money(business_value),
                "cash": money(player.cash),
                "netWorth": money(net_worth),
                "unrealizedPnl": money(total_market_value - total_cost),
                "realizedPnl": money(total_realized),
                "totalPnl": money((total_market_value - total_cost) + total_realized),
            },
        }
