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

# Argentina profiles (ARS)
MOCK_MERCHANTS_AR = {
    "a1b2c3d4-0004-0004-0004-000000000004": {"name": "Panadería San Martín",  "bank": "Banco Nación"},
    "a1b2c3d4-0005-0005-0005-000000000005": {"name": "Ferretería López",       "bank": "Banco Galicia"},
    "a1b2c3d4-0006-0006-0006-000000000006": {"name": "Almacén El Toro",        "bank": "Brubank"},
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


_GENERATORS = {
    "a1b2c3d4-0001-0001-0001-000000000001": _generate_el_patio,
    "a1b2c3d4-0002-0002-0002-000000000002": _generate_velasquez,
    "a1b2c3d4-0003-0003-0003-000000000003": _generate_tienda_nueva,
    "a1b2c3d4-0004-0004-0004-000000000004": _generate_panaderia_san_martin,
    "a1b2c3d4-0005-0005-0005-000000000005": _generate_ferreteria_lopez,
    "a1b2c3d4-0006-0006-0006-000000000006": _generate_almacen_el_toro,
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
