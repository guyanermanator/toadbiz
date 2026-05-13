from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RealEstateTemplate:
    id: str
    name: str
    cost: float
    starting_value: float
    base_rent: float
    appreciation: float


@dataclass(frozen=True)
class BusinessTemplate:
    id: str
    name: str
    cost: float
    starting_value: float
    income_per_hour: float
    sector: str
    industry: str
    starting_price: float
    max_volume: int


@dataclass(frozen=True)
class SabotageTemplate:
    id: str
    name: str
    description: str
    base_cost: float
    power: float
    cooldown_seconds: int
    event_hint: str


REAL_ESTATE_CATALOG: list[RealEstateTemplate] = [
    RealEstateTemplate(
        id="shabby-shack",
        name="Shabby Shack",
        cost=130.0,
        starting_value=130.0,
        base_rent=10.0,
        appreciation=0.000018,
    ),
    RealEstateTemplate(
        id="leaky-duplex",
        name="Leaky Duplex",
        cost=650.0,
        starting_value=650.0,
        base_rent=36.0,
        appreciation=0.000015,
    ),
    RealEstateTemplate(
        id="mall-kiosk",
        name="Abandoned Mall Kiosk",
        cost=1450.0,
        starting_value=1450.0,
        base_rent=72.0,
        appreciation=0.000012,
    ),
]


BUSINESS_CATALOG: list[BusinessTemplate] = [
    BusinessTemplate(
        id="lemonade-stand",
        name="Lemonade Stand",
        cost=85.0,
        starting_value=85.0,
        income_per_hour=1.5,
        sector="Player Business",
        industry="Front Yard Refreshments",
        starting_price=3.25,
        max_volume=6000,
    ),
    BusinessTemplate(
        id="bean-cart",
        name="Bean Cart",
        cost=420.0,
        starting_value=420.0,
        income_per_hour=8.0,
        sector="Player Business",
        industry="Mobile Bean Retail",
        starting_price=7.8,
        max_volume=9000,
    ),
    BusinessTemplate(
        id="tiny-consultancy",
        name="Tiny Consultancy",
        cost=1350.0,
        starting_value=1350.0,
        income_per_hour=24.0,
        sector="Player Business",
        industry="Questionable Advice",
        starting_price=16.4,
        max_volume=12000,
    ),
]


SABOTAGE_CATALOG: list[SabotageTemplate] = [
    SabotageTemplate(
        id="ceo-prank",
        name="Corporate Spy Prank",
        description="Increase odds of a CEO humiliation event.",
        base_cost=95.0,
        power=0.28,
        cooldown_seconds=120,
        event_hint="CEO prank pressure is building",
    ),
    SabotageTemplate(
        id="leaked-chats",
        name="Leaked Chat Messages",
        description="Increase odds of embarrassing internal logs surfacing.",
        base_cost=180.0,
        power=0.42,
        cooldown_seconds=180,
        event_hint="private chat logs are looking less private",
    ),
    SabotageTemplate(
        id="shadow-contract",
        name="Shadow Contract Rumor",
        description="Increase odds of a severe leadership disaster.",
        base_cost=520.0,
        power=0.68,
        cooldown_seconds=420,
        event_hint="the boardroom feels unusually nervous",
    ),
]


CEO_POOL = [
    {"name": "Slime Gutter Slimeball", "bias": -0.014, "quip": "is maximizing executive snacks over shareholder value"},
    {"name": "Chumby", "bias": 0.008, "quip": "is steadily stapling growth to the quarterly plan"},
    {"name": "Myrtle Pumpwell", "bias": 0.003, "quip": "is keeping the pipes and numbers mostly upright"},
    {"name": "Dr. Pixel Von Wink", "bias": 0.006, "quip": "keeps saying AI in every meeting and somehow it works"},
    {"name": "Ledgerly Jones", "bias": 0.002, "quip": "has alphabetized every expense receipt"},
    {"name": "Forklift McGee", "bias": -0.002, "quip": "is moving fast and occasionally hitting walls"},
]


TENANT_POOL = [
    {"name": "Gary Paysearly", "quality": "good", "rentMultiplier": 1.15},
    {"name": "Mina Quietly", "quality": "good", "rentMultiplier": 1.05},
    {"name": "Randy Floorpizza", "quality": "shady", "rentMultiplier": 0.58},
    {"name": "Beth Alwayslate", "quality": "shady", "rentMultiplier": 0.72},
    {"name": "Normal Norman", "quality": "normal", "rentMultiplier": 1.0},
]


def real_estate_template(template_id: str) -> RealEstateTemplate | None:
    for template in REAL_ESTATE_CATALOG:
        if template.id == template_id:
            return template
    return None


def business_template(template_id: str) -> BusinessTemplate | None:
    for template in BUSINESS_CATALOG:
        if template.id == template_id:
            return template
    return None


def sabotage_template(template_id: str) -> SabotageTemplate | None:
    for template in SABOTAGE_CATALOG:
        if template.id == template_id:
            return template
    return None
