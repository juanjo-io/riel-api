import json
import os
from datetime import date, timedelta

from .base import DataProvider

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MOCK_MERCHANTS = {
    "a1b2c3d4-0001-0001-0001-000000000001": {"name": "Restaurante El Patio"},
    "a1b2c3d4-0002-0002-0002-000000000002": {"name": "Distribuidora Velásquez"},
    "a1b2c3d4-0003-0003-0003-000000000003": {"name": "Tienda Nueva"},
}

# Argentina profiles (ARS) — 10 merchants, 5 sectors, 5 actions
MOCK_MERCHANTS_AR = {
    "a1b2c3d4-0004-0004-0004-000000000004": {"name": "Panadería San Martín",      "bank": "Banco Nación",   "sector": "gastronomia"},
    "a1b2c3d4-0005-0005-0005-000000000005": {"name": "Ferretería López",           "bank": "Banco Galicia",  "sector": "ferreteria"},
    "a1b2c3d4-0006-0006-0006-000000000006": {"name": "Almacén El Toro",            "bank": "Brubank",        "sector": "almacen"},
    "a1b2c3d4-0007-0007-0007-000000000007": {"name": "Kiosco Don Julio",           "bank": "Banco Nación",   "sector": "kiosco"},
    "a1b2c3d4-0008-0008-0008-000000000008": {"name": "Librería Central",           "bank": "Banco Galicia",  "sector": "libreria"},
    "a1b2c3d4-0009-0009-0009-000000000009": {"name": "Taller Mecánico Rodríguez",  "bank": "HSBC Argentina", "sector": "taller"},
    "a1b2c3d4-0010-0010-0010-000000000010": {"name": "Verdulería La Fresca",       "bank": "Brubank",        "sector": "verduleria"},
    "a1b2c3d4-0011-0011-0011-000000000011": {"name": "Carnicería El Gaucho",       "bank": "Banco Nación",   "sector": "carniceria"},
    "a1b2c3d4-0012-0012-0012-000000000012": {"name": "Fotocopias Rápidas",         "bank": "Banco Galicia",  "sector": "fotocopias"},
    "a1b2c3d4-0013-0013-0013-000000000013": {"name": "Indumentaria Moda BA",       "bank": "Santander",      "sector": "indumentaria"},
}


# ── Review workflow mock state ────────────────────────────────────────────────
# Keyed by link_id. All dates relative to 2026-04-16 reference date.
# review_status: "unreviewed" | "in_review" | "reviewed"
MOCK_REVIEW_STATE_AR = {
    "a1b2c3d4-0004-0004-0004-000000000004": {
        "review_status":   "reviewed",
        "owner":           "j.lopez@riel.com",
        "analyst_note":    "Strong panadería with consistent foot traffic. Revenue concentration "
                           "within acceptable range. Recommend limit increase to ARS 500k.",
        "last_review_date": "2026-04-08",
    },
    "a1b2c3d4-0005-0005-0005-000000000005": {
        "review_status":   "in_review",
        "owner":           "m.garcia@riel.com",
        "analyst_note":    "FX exposure elevated due to imported hardware stock. Monitoring "
                           "whether ARS depreciation passes through to end prices.",
        "last_review_date": None,
    },
    "a1b2c3d4-0006-0006-0006-000000000006": {
        "review_status":   "unreviewed",
        "owner":           None,
        "analyst_note":    None,
        "last_review_date": None,
    },
    "a1b2c3d4-0007-0007-0007-000000000007": {
        "review_status":   "reviewed",
        "owner":           "j.lopez@riel.com",
        "analyst_note":    "Stable kiosco with low burn. No concerns.",
        "last_review_date": "2026-04-10",
    },
    "a1b2c3d4-0008-0008-0008-000000000008": {
        "review_status":   "in_review",
        "owner":           "m.garcia@riel.com",
        "analyst_note":    "Short runway driven by school supplies seasonal slump. "
                           "Owner indicated pending purchase order from school district.",
        "last_review_date": "2026-03-28",   # 7d cadence → overdue since 2026-04-04
    },
    "a1b2c3d4-0009-0009-0009-000000000009": {
        "review_status":   "unreviewed",
        "owner":           None,
        "analyst_note":    None,
        "last_review_date": None,
    },
    "a1b2c3d4-0010-0010-0010-000000000010": {
        "review_status":   "reviewed",
        "owner":           "m.garcia@riel.com",
        "analyst_note":    "Override in place. Owner confirmed new long-term supply "
                           "contract signed 2026-04-09. Runway recovery expected within 45 days.",
        "last_review_date": "2026-04-10",
    },
    "a1b2c3d4-0011-0011-0011-000000000011": {
        "review_status":   "reviewed",
        "owner":           "j.lopez@riel.com",
        "analyst_note":    "Healthy carnicería. Consistent inflows, low FX risk.",
        "last_review_date": "2026-04-02",
    },
    "a1b2c3d4-0012-0012-0012-000000000012": {
        "review_status":   "unreviewed",
        "owner":           None,
        "analyst_note":    None,
        "last_review_date": None,   # never reviewed → overdue immediately
    },
    "a1b2c3d4-0013-0013-0013-000000000013": {
        "review_status":   "reviewed",
        "owner":           "j.lopez@riel.com",
        "analyst_note":    "Growing indumentaria brand. Opportunity to increase limit.",
        "last_review_date": "2026-04-12",
    },
}

# ── Analyst overrides (demo mode only) ───────────────────────────────────────
# These override the model recommendation for display; scoring logic is unchanged.
MOCK_OVERRIDES_AR = {
    "a1b2c3d4-0010-0010-0010-000000000010": {
        "original_recommendation": "reduce_exposure",
        "current_recommendation":  "monitor",
        "override_reason":         "Owner confirmed new long-term supply contract signed "
                                   "2026-04-09. Runway expected to recover within 45 days. "
                                   "Risk team agrees to hold at Monitor pending next batch.",
        "override_timestamp":      "2026-04-10T14:23:00",
        "override_by":             "m.garcia@riel.com",
    },
    "a1b2c3d4-0012-0012-0012-000000000012": {
        "original_recommendation": "review_now",
        "current_recommendation":  "reduce_exposure",
        "override_reason":         "Field visit 2026-04-14 confirmed equipment is leased "
                                   "not owned; off-balance obligations not captured by model. "
                                   "Actual liquidity risk is higher than model signal.",
        "override_timestamp":      "2026-04-14T09:15:00",
        "override_by":             "m.garcia@riel.com",
    },
}


# ── Case / action log (demo mode only) ───────────────────────────────────────
# Keyed by link_id. Each entry is a list of case events ordered oldest-first.
# event_type: flag_raised | analyst_reviewed | recommendation_confirmed |
#             no_action_taken | reduce_exposure_recommended | topup_candidate_flagged
MOCK_CASE_LOG_AR = {
    # Panadería San Martín — positive trajectory, flagged for top-up
    "a1b2c3d4-0004-0004-0004-000000000004": [
        {
            "date":       "2026-03-15",
            "event_type": "topup_candidate_flagged",
            "note":       "Cash-flow positive for 3 consecutive months. Flagged as limit-increase candidate.",
            "analyst":    "j.lopez@riel.com",
        },
        {
            "date":       "2026-04-08",
            "event_type": "analyst_reviewed",
            "note":       "Full review completed. All metrics green. Limit increase to ARS 500k recommended.",
            "analyst":    "j.lopez@riel.com",
        },
        {
            "date":       "2026-04-08",
            "event_type": "recommendation_confirmed",
            "note":       "Credit committee approved limit increase to ARS 500k.",
            "analyst":    "j.lopez@riel.com",
        },
    ],
    # Librería Central — short runway, seasonal slump, overdue review
    "a1b2c3d4-0008-0008-0008-000000000008": [
        {
            "date":       "2026-03-15",
            "event_type": "flag_raised",
            "note":       "Runway fell below 30-day threshold. Case opened for review.",
            "analyst":    None,
        },
        {
            "date":       "2026-03-28",
            "event_type": "analyst_reviewed",
            "note":       "Partial review: owner confirmed school-supply seasonal slump. "
                          "Pending purchase order from school district. Review paused.",
            "analyst":    "m.garcia@riel.com",
        },
        {
            "date":       "2026-04-15",
            "event_type": "no_action_taken",
            "note":       "Purchase order not yet confirmed. Case remains open, review overdue.",
            "analyst":    "m.garcia@riel.com",
        },
    ],
    # Verdulería La Fresca — reduce_exposure with analyst override
    "a1b2c3d4-0010-0010-0010-000000000010": [
        {
            "date":       "2026-04-05",
            "event_type": "flag_raised",
            "note":       "Runway critical and deterioration index severe. Escalation triggered automatically.",
            "analyst":    None,
        },
        {
            "date":       "2026-04-10",
            "event_type": "analyst_reviewed",
            "note":       "Owner interview and field visit completed. New long-term supply contract presented.",
            "analyst":    "m.garcia@riel.com",
        },
        {
            "date":       "2026-04-10",
            "event_type": "reduce_exposure_recommended",
            "note":       "Model maintains Reduce Exposure. Override applied: Monitor pending runway recovery.",
            "analyst":    "m.garcia@riel.com",
        },
    ],
    # Fotocopias Rápidas — unreviewed, field visit escalated to reduce_exposure
    "a1b2c3d4-0012-0012-0012-000000000012": [
        {
            "date":       "2026-04-14",
            "event_type": "flag_raised",
            "note":       "Field visit initiated after model flagged Review Now. Off-balance obligations identified.",
            "analyst":    "m.garcia@riel.com",
        },
        {
            "date":       "2026-04-14",
            "event_type": "analyst_reviewed",
            "note":       "Equipment confirmed leased, not owned. Off-balance obligations not captured by model.",
            "analyst":    "m.garcia@riel.com",
        },
        {
            "date":       "2026-04-14",
            "event_type": "reduce_exposure_recommended",
            "note":       "Override applied: Reduce Exposure. Actual liquidity risk exceeds model signal.",
            "analyst":    "m.garcia@riel.com",
        },
    ],
    # Indumentaria Moda BA — growing brand, top-up flagged
    "a1b2c3d4-0013-0013-0013-000000000013": [
        {
            "date":       "2026-04-12",
            "event_type": "analyst_reviewed",
            "note":       "Quarterly review completed. Positive trajectory confirmed, inflows stable.",
            "analyst":    "j.lopez@riel.com",
        },
        {
            "date":       "2026-04-12",
            "event_type": "topup_candidate_flagged",
            "note":       "Flagged for limit increase to ARS 750k pending credit committee review.",
            "analyst":    "j.lopez@riel.com",
        },
    ],
}


def _tx(link_id, days_ago, amount, counterparty, category):
    today = date.today()
    return {
        "id":               f"tx-mock-{link_id[-4:]}-{days_ago:04d}",
        "account":          f"acc-mock-{link_id[-4:]}",
        "link":             link_id,
        "value_date":       (today - timedelta(days=days_ago)).isoformat(),
        "amount":           amount,
        "currency":         "COP",
        "description":      f"{counterparty} · {category}",
        "category":         category,
        "counterparty_name": counterparty,
        "type":             "INFLOW" if amount > 0 else "OUTFLOW",
        "status":           "PROCESSED",
    }


def _generate_el_patio(link_id: str) -> list[dict]:
    """
    Restaurante El Patio — 180 days, 14 counterparties, ~80 transactions.
    Expected Riél score: 77 → APPROVE.
    """
    import random
    rng = random.Random(1001)
    txs = []

    inflow_sources = [
        "Rappi Colombia", "iFood Colombia", "Domicilios.com",
        "Efectivo Ventas", "Transferencia Clientes",
    ]

    # 26 weekly inflows (days_ago 5, 12, ..., 180)
    for i, da in enumerate(range(5, 185, 7)):
        txs.append(_tx(link_id, da, rng.randint(3_500_000, 6_500_000), inflow_sources[i % 5], "transfer"))

    # Meat supplier: 12 weekly outflows (days_ago 5..82) → covers check-weeks 0–11
    for da in range(5, 89, 7):
        txs.append(_tx(link_id, da, -rng.randint(350_000, 650_000), "Proveedor Carnes La Mejor", "food"))

    # Veg supplier: 6 biweekly outflows
    for da in range(5, 82, 14):
        txs.append(_tx(link_id, da, -rng.randint(180_000, 320_000), "Distribuidora Verduras Frescas", "food"))

    # 6 months of fixed costs (rent + 4 utilities) starting at days_ago 10
    for m in range(6):
        base = 10 + m * 30
        txs.append(_tx(link_id, base,     -1_500_000,                        "Inmobiliaria Centro",    "transfer"))
        txs.append(_tx(link_id, base + 1, -rng.randint(90_000, 130_000),     "Gas Natural Fenosa",     "utilities"))
        txs.append(_tx(link_id, base + 2, -rng.randint(110_000, 190_000),    "Codensa",                "utilities"))
        txs.append(_tx(link_id, base + 3, -rng.randint(30_000, 60_000),      "Acueducto de Bogotá",   "utilities"))
        txs.append(_tx(link_id, base + 4, -rng.randint(60_000, 85_000),      "ETB Fibra",              "utilities"))

    # Occasional beverage and grain suppliers
    for da in [25, 75, 130]:
        txs.append(_tx(link_id, da, -rng.randint(280_000, 450_000), "Bebidas y Licores Andina",  "food"))
    for da in [50, 110, 155]:
        txs.append(_tx(link_id, da, -rng.randint(130_000, 250_000), "Granos y Secos Colombia",   "food"))

    return txs


def _generate_velasquez(link_id: str) -> list[dict]:
    """
    Distribuidora Velásquez — 90 days, 5 counterparties, 20 transactions.
    Expected Riél score: 51 → REVIEW.
    """
    txs = []

    # 10 inflows — irregular amounts (high CV → low income_stability)
    inflows = [
        (2,  2_200_000), (13,  800_000), (20, 2_600_000), (36,  900_000),
        (43, 2_100_000), (50, 1_500_000), (65, 2_800_000), (72,  600_000),
        (78, 2_300_000), (88, 1_000_000),
    ]
    for da, am in inflows:
        src = "Almacenes Éxito" if da % 2 == 0 else "Efectivo Ventas"
        txs.append(_tx(link_id, da, am, src, "transfer"))

    # 10 outflows covering 10 of 13 check-weeks (skip weeks 3, 7, 11)
    # Proveedor Nacional has 4 outflows → repayment_proxy True
    outflows = [
        (5,  -300_000, "Proveedor Nacional Alimentos", "transfer"),
        (13, -140_000, "Proveedor Nacional Alimentos", "transfer"),
        (20, -290_000, "Proveedor Nacional Alimentos", "transfer"),
        (34, -800_000, "Arrendador Bodega",             "transfer"),
        (41, -130_000, "Codensa",                       "utilities"),
        (48, -260_000, "Arrendador Bodega",             "transfer"),
        (62, -270_000, "Proveedor Nacional Alimentos",  "transfer"),
        (69, -110_000, "Codensa",                       "utilities"),
        (76, -240_000, "Arrendador Bodega",             "transfer"),
        (90, -130_000, "Codensa",                       "utilities"),
    ]
    for da, am, cp, cat in outflows:
        txs.append(_tx(link_id, da, am, cp, cat))

    return txs


def _generate_tienda_nueva(link_id: str) -> list[dict]:
    """
    Tienda Nueva — 30 days, 3 counterparties, 10 transactions.
    Expected Riél score: 22 → DECLINE.
    """
    txs = []

    inflows = [
        (28, 700_000), (21, 150_000), (18, 650_000),
        (10, 100_000), (5,  550_000), (2,  200_000),
    ]
    for da, am in inflows:
        txs.append(_tx(link_id, da, am, "Ventas Efectivo", "transfer"))

    outflows = [
        (4,  -180_000, "Proveedor Local", "commerce"),
        (12, -90_000,  "Arrendador",      "transfer"),
        (19, -150_000, "Proveedor Local", "commerce"),
        (26, -80_000,  "Arrendador",      "transfer"),
    ]
    for da, am, cp, cat in outflows:
        txs.append(_tx(link_id, da, am, cp, cat))

    return txs


def _ar_tx(link_id, days_ago, amount, counterparty, currency="ARS", description=None):
    today = date.today()
    return {
        "id":               f"tx-ar-{link_id[-4:]}-{days_ago:04d}",
        "account":          f"acc-ar-{link_id[-4:]}",
        "link":             link_id,
        "value_date":       (today - timedelta(days=days_ago)).isoformat(),
        "amount":           amount,
        "currency":         currency,
        "description":      description or f"{counterparty}",
        "category":         "transfer",
        "counterparty_name": counterparty,
        "type":             "INFLOW" if amount > 0 else "OUTFLOW",
        "status":           "PROCESSED",
    }


def _generate_panaderia_san_martin(link_id: str) -> list[dict]:
    """
    Panadería San Martín — 180 days, ARS, 8 inflow sources, growing trend.
    Expected action: opportunity (all green + deterioration > 0.20).
    """
    import random
    rng = random.Random(4004)
    txs = []

    # 8 inflow counterparties — diversified, no single one dominates
    sources = [
        "Ventas Mostrador",
        "Mercado Pago San Martín",
        "MODO Pagos",
        "Buenas Migas Distribuidora",
        "Cafetería del Barrio",
        "Confitería Los Andes",
        "Catering Eventos BA",
        "Almacén La Esquina",
    ]

    # Weekly inflows, growing ~20 % in recent 30 days vs prior 30 days
    # days 1–30: avg 1 850 000 ARS/week → 4 weeks = 7 400 000
    # days 31–60: avg 1 500 000 ARS/week → 4 weeks = 6 000 000
    # days 61–180: avg 1 300 000 ARS/week
    for i, da in enumerate(range(3, 180, 7)):
        if da <= 30:
            base = 1_700_000
        elif da <= 60:
            base = 1_400_000
        else:
            base = 1_200_000
        amount = rng.randint(base, base + 300_000)
        txs.append(_ar_tx(link_id, da, amount, sources[i % len(sources)]))

    # Flour supplier: weekly recurring outflows (main contractual obligation)
    for da in range(4, 180, 7):
        txs.append(_ar_tx(link_id, da, -rng.randint(100_000, 140_000), "Harinera del Plata"))

    # Rent: monthly (3 times in 90-day window counts as contractual)
    for m in range(6):
        txs.append(_ar_tx(link_id, 10 + m * 30, -380_000, "Inmobiliaria Norte"))

    # Utilities: monthly
    for m in range(6):
        base = 12 + m * 30
        txs.append(_ar_tx(link_id, base,     -rng.randint(40_000, 60_000),  "Edesur"))
        txs.append(_ar_tx(link_id, base + 1, -rng.randint(20_000, 35_000),  "Metrogas"))

    # Packaging supplier: biweekly
    for da in range(6, 180, 14):
        txs.append(_ar_tx(link_id, da, -rng.randint(55_000, 85_000), "Envases Rápido"))

    return txs


def _generate_ferreteria_lopez(link_id: str) -> list[dict]:
    """
    Ferretería López — 90 days, ARS with USD tool imports (~15 % of outflows).
    Expected action: monitor (one amber: fx_mismatch_exposure 0.14).
    """
    import random
    rng = random.Random(5005)
    txs = []

    # Steady weekly inflows from 7 evenly-distributed sources (concentration < 50 %)
    sources = [
        "Ventas Mostrador López",
        "Transferencia Clientes",
        "Mercado Pago Ferretería",
        "Constructora Palermo",
        "Corralón del Sur",
        "Obras Servicios SA",
        "Electricidad Rápida",
    ]
    for i, da in enumerate(range(2, 90, 7)):
        amount = rng.randint(1_250_000, 1_450_000)  # narrow range keeps shares even
        txs.append(_ar_tx(link_id, da, amount, sources[i % len(sources)]))

    # Local suppliers (ARS, recurring)
    for da in range(5, 90, 14):
        txs.append(_ar_tx(link_id, da, -rng.randint(280_000, 360_000), "Distribuidora Herramientas SA"))
    for da in range(7, 90, 30):
        txs.append(_ar_tx(link_id, da, -340_000, "Inmobiliaria Centro"))

    # USD tool imports — currency USD, ~15 % of total outflows
    for da in [15, 45, 75]:
        txs.append(_ar_tx(link_id, da, -rng.randint(180_000, 220_000),
                          "Stanley Tools Import", currency="USD",
                          description="Importacion herramientas USD"))

    # Utilities (ARS)
    for da in range(10, 90, 30):
        txs.append(_ar_tx(link_id, da, -rng.randint(45_000, 65_000), "Edenor"))

    return txs


def _generate_almacen_el_toro(link_id: str) -> list[dict]:
    """
    Almacén El Toro — 60 days, cash squeeze, high FX, single customer.
    Expected action: reduce_exposure (multiple reds + deterioration < -0.30).
    """
    import random
    rng = random.Random(6006)
    txs = []

    # Single inflow source (concentration = 1.0 → red)
    # Declining: 30d inflows ~1.8M, 31-60d inflows ~3.6M → deterioration ≈ -0.50
    for da in range(3, 30, 7):   # 4 inflows in last 30d
        txs.append(_ar_tx(link_id, da, rng.randint(380_000, 520_000), "Supermercado Vecinal"))
    for da in range(32, 62, 7):  # 4 inflows in 31-60d window (2x larger)
        txs.append(_ar_tx(link_id, da, rng.randint(800_000, 950_000), "Supermercado Vecinal"))

    # High USD/EUR costs (FX > 0.30 → red)
    for da in [8, 22, 38, 52]:
        txs.append(_ar_tx(link_id, da, -rng.randint(300_000, 400_000),
                          "Importadora Buenos Aires", currency="USD",
                          description="Importacion productos USD"))

    # ARS outflows (rent, local supplier — high relative to inflows)
    for da in [10, 40]:
        txs.append(_ar_tx(link_id, da, -580_000, "Arrendador Local"))
    for da in range(5, 62, 14):
        txs.append(_ar_tx(link_id, da, -rng.randint(150_000, 220_000), "Proveedor Lácteos SA"))

    return txs


def _generate_kiosco_don_julio(link_id: str) -> list[dict]:
    """
    Kiosco Don Julio — stable, 8 diversified sources, slight growth.
    Expected action: healthy (all green, det ~0.11, not > 0.20).
    Window design: starts [2, 33, 63] so adj=[0,31,61] → clean window boundaries.
    """
    txs = []
    sources = [
        "Ventas Mostrador", "Mercado Pago Kiosco", "MODO Pagos",
        "Clientes Barrio A", "Clientes Barrio B", "Clientes Barrio C",
        "Delivery Rappi", "Transferencias Clientes",
    ]
    # 8 inflows per window, one per source (equal per-source totals → concentration ~37%)
    for window_start, amount in [(2, 440_000), (33, 400_000), (63, 370_000)]:
        for j, da in enumerate(range(window_start, window_start + 29, 4)):
            if j >= len(sources):
                break
            txs.append(_ar_tx(link_id, da, amount, sources[j]))

    # Rent: monthly, adj=[10,40,70] → one per window
    for da in [12, 42, 72]:
        txs.append(_ar_tx(link_id, da, -200_000, "Arrendador Kiosco"))
    # Supply: biweekly, 2 per window adj=[5,19] / [35,49] / [65,79]
    for da in [7, 21, 35, 49, 65, 79]:
        txs.append(_ar_tx(link_id, da, -65_000, "Distribuidora Snacks"))

    return txs


def _generate_libreria_central(link_id: str) -> list[dict]:
    """
    Librería Central — thin margins (inflows barely exceed outflows).
    Expected action: review_now (runway red ~14d; coverage amber ~1.46; det amber ~0).
    Window design: starts [2, 33, 63]; equal outflows per window via explicit days.
    """
    txs = []
    sources = [
        "Ventas Mostrador", "Mercado Libre Libros", "Tarjetas Crédito",
        "MODO Pagos", "Transferencias", "Mercado Pago", "PagoMisCuentas",
    ]
    # 7 inflows per window at equal amounts → equal 30d/31-60d net → det = 0 (amber)
    for window_start in [2, 33, 63]:
        for j, da in enumerate(range(window_start, window_start + 25, 4)):
            if j >= len(sources):
                break
            txs.append(_ar_tx(link_id, da, 115_000, sources[j]))

    # Rent: one per window adj=[10,40,70]
    for da in [12, 42, 72]:
        txs.append(_ar_tx(link_id, da, -350_000, "Inmobiliaria Norte"))
    # Book supplier: biweekly, 2 per window adj=[5,19] / [35,49] / [65,79]
    for da in [7, 21, 35, 49, 65, 79]:
        txs.append(_ar_tx(link_id, da, -100_000, "Editorial Distribuidora"))

    return txs


def _generate_taller_mecanico(link_id: str) -> list[dict]:
    """
    Taller Mecánico Rodríguez — USD parts imports ~15 % of outflows, else healthy.
    Expected action: monitor (fx_mismatch amber).
    """
    import random
    rng = random.Random(9009)
    txs = []
    sources = [
        "Ventas Taller", "Seguros Provincias", "Flotas Empresariales",
        "Talleres Aliados", "Particulares", "Municipio Contratos",
        "Transporte Logística",
    ]
    for i, da in enumerate(range(2, 90, 7)):
        txs.append(_ar_tx(link_id, da, rng.randint(1_100_000, 1_400_000), sources[i % len(sources)]))

    # ARS suppliers (recurring)
    for da in range(6, 90, 14):
        txs.append(_ar_tx(link_id, da, -rng.randint(320_000, 380_000), "Repuestos Nacionales SA"))
    for da in [10, 40, 70]:
        txs.append(_ar_tx(link_id, da, -520_000, "Local Comercial"))

    # USD parts imports (~15 % of outflows) — 3 times in 90d
    for da in [15, 45, 75]:
        txs.append(_ar_tx(link_id, da, -rng.randint(250_000, 300_000),
                          "Parts Import USA", currency="USD",
                          description="Repuestos importados USD"))

    return txs


def _generate_verduleria_la_fresca(link_id: str) -> list[dict]:
    """
    Verdulería La Fresca — single buyer, revenue collapsing, high burn.
    Expected action: reduce_exposure (runway red + concentration red + det red).
    """
    import random
    rng = random.Random(1010)
    txs = []

    # Single inflow source: concentration = 1.0 (red)
    for da in range(3, 30, 7):    # 30d: ~200k/week (crashing)
        txs.append(_ar_tx(link_id, da, rng.randint(180_000, 220_000), "Mercado Municipal"))
    for da in range(32, 62, 7):   # 31-60d: ~700k/week (was decent)
        txs.append(_ar_tx(link_id, da, rng.randint(650_000, 750_000), "Mercado Municipal"))
    for da in range(63, 91, 7):   # 61-90d: ~900k/week (was even better)
        txs.append(_ar_tx(link_id, da, rng.randint(850_000, 950_000), "Mercado Municipal"))

    # High ARS costs (fixed, not going down)
    for da in [8, 38, 68]:
        txs.append(_ar_tx(link_id, da, -580_000, "Arrendador Puesto"))
    for da in range(5, 91, 7):
        txs.append(_ar_tx(link_id, da, -rng.randint(180_000, 220_000), "Proveedor Frutas"))

    return txs


def _generate_carniceria_el_gaucho(link_id: str) -> list[dict]:
    """
    Carnicería El Gaucho — diversified, slight positive trend.
    Expected action: healthy (all green, det ~0.17, runway > 60d).
    Window design: starts [2, 33, 63]; equal outflows per window.
    """
    txs = []
    sources = [
        "Ventas Mostrador", "Mercado Pago Gaucho", "Delivery Local",
        "Restaurantes BA", "Asados Empresariales", "Clientes Mayoristas",
        "MODO Pagos", "Transferencias Directas",
    ]
    # 8 sources × 3 windows; recent window has higher amounts → det ~0.17
    for window_start, amount in [(2, 680_000), (33, 600_000), (63, 560_000)]:
        for j, da in enumerate(range(window_start, window_start + 29, 4)):
            if j >= len(sources):
                break
            txs.append(_ar_tx(link_id, da, amount, sources[j]))

    # Rent: one per window adj=[10,40,70]
    for da in [12, 42, 72]:
        txs.append(_ar_tx(link_id, da, -450_000, "Local Comercial BA"))
    # Meat supplier: biweekly, 2 per window adj=[7,21] / [35,49] / [65,79]
    for da in [9, 23, 37, 51, 67, 81]:
        txs.append(_ar_tx(link_id, da, -300_000, "Frigorífico Central"))

    return txs


def _generate_fotocopias_rapidas(link_id: str) -> list[dict]:
    """
    Fotocopias Rápidas — 5 equal sources, stable margins, tight runway.
    Expected action: review_now (runway amber ~52d; concentration amber 60%; det amber 0).
    Window design: starts [2, 33, 63]; equal amounts → det = 0; 5 sources → conc = 60%.
    """
    txs = []
    sources = [
        "Universidad BA", "Empresa Editorial", "Colegio Nacional",
        "Oficinas Corporativas", "Particulares y Varios",
    ]
    # 5 inflows per window at equal amounts → top-3/total = 3/5 = 60% (amber)
    for window_start in [2, 33, 63]:
        for j, da in enumerate(range(window_start, window_start + 17, 4)):
            if j >= len(sources):
                break
            txs.append(_ar_tx(link_id, da, 360_000, sources[j]))

    # Rent: one per window adj=[10,40,70]
    for da in [12, 42, 72]:
        txs.append(_ar_tx(link_id, da, -300_000, "Local Comercial"))
    # Equipment lease: biweekly, 2 per window adj=[5,19] / [35,49] / [65,79]
    for da in [7, 21, 35, 49, 65, 79]:
        txs.append(_ar_tx(link_id, da, -180_000, "Alquiler Equipos Canon"))

    return txs


def _generate_indumentaria_moda_ba(link_id: str) -> list[dict]:
    """
    Indumentaria Moda BA — fast-growing fashion retail, diversified channels.
    Expected action: opportunity (all green, det > 0.20).
    """
    import random
    rng = random.Random(1313)
    txs = []
    sources = [
        "Tienda Online", "Instagram Shop", "Mercado Libre Ropa",
        "Ventas Mostrador", "Mayoristas Textiles", "TiendaNube",
        "WhatsApp Pedidos", "Feria Palermo",
    ]
    # Strong growth: recent 30d ~2.5M, prior 30d ~1.7M
    for i, da in enumerate(range(3, 30, 4)):   # 7 inflows in 30d
        txs.append(_ar_tx(link_id, da, rng.randint(330_000, 390_000), sources[i % len(sources)]))
    for i, da in enumerate(range(32, 62, 5)):  # 6 inflows in 31-60d
        txs.append(_ar_tx(link_id, da, rng.randint(260_000, 300_000), sources[i % len(sources)]))
    for i, da in enumerate(range(63, 90, 5)):  # 6 inflows in 61-90d
        txs.append(_ar_tx(link_id, da, rng.randint(220_000, 260_000), sources[i % len(sources)]))

    # ARS costs
    for da in [10, 40, 70]:
        txs.append(_ar_tx(link_id, da, -380_000, "Local Palermo"))
    for da in range(6, 90, 14):
        txs.append(_ar_tx(link_id, da, -rng.randint(200_000, 260_000), "Proveedor Telas BA"))

    return txs


_GENERATORS = {
    "a1b2c3d4-0001-0001-0001-000000000001": _generate_el_patio,
    "a1b2c3d4-0002-0002-0002-000000000002": _generate_velasquez,
    "a1b2c3d4-0003-0003-0003-000000000003": _generate_tienda_nueva,
    "a1b2c3d4-0004-0004-0004-000000000004": _generate_panaderia_san_martin,
    "a1b2c3d4-0005-0005-0005-000000000005": _generate_ferreteria_lopez,
    "a1b2c3d4-0006-0006-0006-000000000006": _generate_almacen_el_toro,
    "a1b2c3d4-0007-0007-0007-000000000007": _generate_kiosco_don_julio,
    "a1b2c3d4-0008-0008-0008-000000000008": _generate_libreria_central,
    "a1b2c3d4-0009-0009-0009-000000000009": _generate_taller_mecanico,
    "a1b2c3d4-0010-0010-0010-000000000010": _generate_verduleria_la_fresca,
    "a1b2c3d4-0011-0011-0011-000000000011": _generate_carniceria_el_gaucho,
    "a1b2c3d4-0012-0012-0012-000000000012": _generate_fotocopias_rapidas,
    "a1b2c3d4-0013-0013-0013-000000000013": _generate_indumentaria_moda_ba,
}


class MockProvider(DataProvider):

    def provider_name(self) -> str:
        return "mock"

    def list_merchants(self) -> list[dict]:
        return [
            {"link_id": k, "name": v["name"]}
            for k, v in MOCK_MERCHANTS.items()
        ]

    def get_transactions(self, link_id: str) -> list[dict]:
        gen = _GENERATORS.get(link_id)
        if gen:
            return gen(link_id)
        # Fallback: legacy sample file (for any other link_id)
        path = os.path.join(_BASE_DIR, "sample_transactions.json")
        with open(path) as f:
            return json.load(f)

    def list_argentina_merchants(self) -> list[dict]:
        return [
            {"link_id": k, **v}
            for k, v in MOCK_MERCHANTS_AR.items()
        ]

    def get_account_summary(self, link_id: str) -> dict:
        if link_id in MOCK_MERCHANTS_AR:
            meta = MOCK_MERCHANTS_AR[link_id]
            return {
                "id":          f"acc-ar-{link_id[-4:]}",
                "link":        link_id,
                "institution": {"name": meta.get("bank", "Banco Nación")},
                "category":    "CHECKING_ACCOUNT",
                "currency":    "ARS",
                "name":        meta["name"],
                "balance":     {"current": 3_500_000, "available": 3_200_000},
            }
        name = MOCK_MERCHANTS.get(link_id, {}).get("name", "Mock Business")
        return {
            "id":          f"acc-mock-{link_id[-4:] if len(link_id) >= 4 else '0000'}",
            "link":        link_id,
            "institution": {"name": "Mock Bank Colombia"},
            "category":    "CHECKING_ACCOUNT",
            "currency":    "COP",
            "name":        name,
            "balance":     {"current": 1_250_000, "available": 1_100_000},
        }
