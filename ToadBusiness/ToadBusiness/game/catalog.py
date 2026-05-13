from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StockTemplate:
    id: str
    symbol: str
    name: str
    sector: str
    industry: str
    market_cap: str
    starting_price: float
    volatility: float
    beta: float
    liquidity: float
    max_volume: int
    ceo: str = "Interim Bean Counter"
    moon_sensitive: bool = False


STOCK_CATALOG: list[StockTemplate] = [
    StockTemplate(
        id="toad-bean",
        symbol="TBE",
        name="Toad Bean Enterprises",
        sector="Consumer Staples",
        industry="Canned Bean Futures",
        market_cap="Micro Cap",
        starting_price=12.75,
        volatility=0.46,
        beta=1.28,
        liquidity=0.68,
        max_volume=18000,
        ceo="Chumby",
    ),
    StockTemplate(
        id="bog-water",
        symbol="BGW",
        name="Bog Water Utilities",
        sector="Utilities",
        industry="Municipal Hydration",
        market_cap="Small Cap",
        starting_price=28.4,
        volatility=0.18,
        beta=0.62,
        liquidity=0.9,
        max_volume=26000,
        ceo="Myrtle Pumpwell",
    ),
    StockTemplate(
        id="lilypad-logistics",
        symbol="PAD",
        name="Lily Pad Logistics",
        sector="Industrials",
        industry="Regional Shipping",
        market_cap="Small Cap",
        starting_price=18.2,
        volatility=0.34,
        beta=1.05,
        liquidity=0.74,
        max_volume=22000,
        ceo="Forklift McGee",
    ),
    StockTemplate(
        id="cricket-crunch",
        symbol="CRK",
        name="Cricket Crunch Holdings",
        sector="Consumer Discretionary",
        industry="Snack Conglomerates",
        market_cap="Nano Cap",
        starting_price=6.8,
        volatility=0.72,
        beta=1.84,
        liquidity=0.44,
        max_volume=12000,
        ceo="Slime Gutter Slimeball",
    ),
    StockTemplate(
        id="moon-moth",
        symbol="MMI",
        name="Moon Moth Microchips",
        sector="Technology",
        industry="Novel Semiconductors",
        market_cap="Mid Cap",
        starting_price=42.1,
        volatility=0.52,
        beta=1.56,
        liquidity=0.82,
        max_volume=32000,
        ceo="Dr. Pixel Von Wink",
    ),
    StockTemplate(
        id="swamp-bank",
        symbol="SBK",
        name="Swamp Bank Trust",
        sector="Financials",
        industry="Community Banking",
        market_cap="Small Cap",
        starting_price=23.65,
        volatility=0.27,
        beta=0.92,
        liquidity=0.78,
        max_volume=24000,
        ceo="Ledgerly Jones",
    ),
    StockTemplate(
        id="orbital-trust",
        symbol="ORB",
        name="Orbital Trust",
        sector="Financials",
        industry="Lunar-Backed Trusts",
        market_cap="Small Cap",
        starting_price=31.25,
        volatility=0.41,
        beta=1.18,
        liquidity=0.7,
        max_volume=21000,
        ceo="Moon Unit Marv",
        moon_sensitive=True,
    ),
]


def template_by_id(stock_id: str) -> StockTemplate | None:
    for template in STOCK_CATALOG:
        if template.id == stock_id:
            return template
    return None
