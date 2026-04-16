import asyncio
import base64
import hashlib
import hmac
import json
import secrets
import threading
import time
import os
import uuid
from datetime import date, datetime as dt, timedelta
from typing import Optional

import httpx
import stripe
import requests
from dotenv import load_dotenv
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature
from fastapi import BackgroundTasks, Cookie, Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel

from supabase import create_client
from features import extract_features
from scorer import calculate_riel_score
from argentina_features import extract_argentina_features
from argentina_scorer import score_argentina
from argentina_portfolio import build_portfolio, build_merchant_detail
from providers.registry import get_provider

load_dotenv()

AUTH_SECRET_KEY = os.getenv("AUTH_SECRET_KEY", "dev-secret-change-in-prod")
_serializer = URLSafeTimedSerializer(AUTH_SECRET_KEY)
ALLOWED_LENDER_EMAILS: list = [
    e.strip() for e in os.getenv("LENDER_EMAILS", "").split(",") if e.strip()
]

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supa = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL and SUPABASE_KEY else None

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

BELVO_SECRET_ID = os.getenv("BELVO_SECRET_ID")
BELVO_SECRET_PASSWORD = os.getenv("BELVO_SECRET_PASSWORD")
BELVO_ENV = os.getenv("BELVO_ENV", "sandbox")
BELVO_BASE_URL = "https://sandbox.belvo.com"

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
MPP_SECRET = os.getenv("STRIPE_MPP_SECRET", secrets.token_hex(32))

# ── API key auth ──────────────────────────────────────────────────────────────
# API_KEYS env var format: "key1:ClientName1,key2:ClientName2"
def _load_api_keys() -> dict[str, dict]:
    raw = os.getenv("API_KEYS", "")
    keys: dict[str, dict] = {}
    for entry in raw.split(","):
        entry = entry.strip()
        if ":" not in entry:
            continue
        key, _, name = entry.partition(":")
        keys[key.strip()] = {"client": name.strip(), "active": True, "created": "2026-03-24"}
    return keys

VALID_API_KEYS: dict[str, dict] = _load_api_keys()


def verify_api_key(x_api_key: Optional[str] = Header(default=None)) -> dict:
    if not x_api_key:
        raise HTTPException(status_code=401, detail={"error": "Invalid or missing API key"})

    if supa:
        try:
            result = supa.table("api_keys").select("lender_name").eq("key_value", x_api_key).eq("active", True).execute()
            if result.data:
                return {"client": result.data[0]["lender_name"], "active": True}
        except Exception as e:
            print(f"[supabase] api key check error: {e}")

    if x_api_key in VALID_API_KEYS:
        return VALID_API_KEYS[x_api_key]

    raise HTTPException(status_code=401, detail={"error": "Invalid or missing API key"})

COP_TO_USD = 4000  # 1 USD ≈ 4 000 COP (fixed rate for sandbox)

# ── x402 helpers ─────────────────────────────────────────────────────────────

def _make_challenge_id() -> str:
    """Return a self-verifying, HMAC-signed challenge token."""
    ts = str(int(time.time()))
    nonce = secrets.token_hex(8)
    payload = f"{ts}:{nonce}"
    sig = hmac.new(MPP_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(f"{payload}:{sig}".encode()).decode()

def _verify_challenge_id(token: str, max_age: int = 300) -> bool:
    """Return True if the token was issued by this server and is not expired."""
    try:
        decoded = base64.urlsafe_b64decode(token.encode()).decode()
        ts_str, nonce, sig = decoded.split(":", 2)
        payload = f"{ts_str}:{nonce}"
        expected = hmac.new(MPP_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return False
        return (int(time.time()) - int(ts_str)) <= max_age
    except Exception:
        return False

# ── Score history & webhook storage ──────────────────────────────────────────
# TODO: replace these in-memory dicts with Supabase tables when credentials
# are available (SUPABASE_URL + SUPABASE_KEY env vars).

_history_lock = threading.Lock()
# link_id → {score, recommendation, timestamp, bank}
_score_history: dict[str, dict] = {}

_webhook_lock = threading.Lock()
# list of {id, client, callback_url, created}
_webhooks: list[dict] = []


def _generate_explanation(features: dict, result: dict) -> str:
    """Rule-based plain-language explanation of a Riél score."""
    score = result["riel_score"]
    rec   = result["recommendation"]
    limit = result["suggested_limit_cop"]
    pc    = features["payment_consistency"]
    cd    = features["counterparty_diversity"]
    is_   = features["income_stability"]
    rp    = features["repayment_proxy"]
    td    = features["tenure_days"]

    sentences = []

    limit_str = f"COP {int(limit):,}" if limit > 0 else "no credit line"
    sentences.append(
        f"This merchant scores {score}/100, resulting in a {rec} decision "
        f"with a recommended credit limit of {limit_str}."
    )

    pc_pct = round(pc * 100)
    if pc >= 0.85:
        sentences.append(
            f"Payment consistency is strong at {pc_pct}%, indicating reliable "
            f"and regular transaction activity across {td} days of banking history."
        )
    elif pc >= 0.65:
        sentences.append(
            f"Payment consistency is moderate at {pc_pct}% over {td} days, "
            f"suggesting some irregularity that a lender should investigate."
        )
    else:
        sentences.append(
            f"Payment consistency is low at {pc_pct}% over {td} days, "
            f"reflecting irregular activity that materially increases credit risk."
        )

    if cd >= 15:
        sentences.append(
            f"High counterparty diversity ({cd} unique parties) reduces "
            f"concentration risk and indicates a broad, healthy revenue base."
        )
    elif cd >= 8:
        sentences.append(
            f"Moderate counterparty diversity ({cd} unique parties) shows a "
            f"developing customer base with some concentration risk."
        )
    else:
        sentences.append(
            f"Low counterparty diversity ({cd} unique parties) signals high "
            f"concentration risk — revenue depends on very few sources."
        )

    is_pct = round(is_ * 100)
    if is_ >= 0.75 and rp:
        sentences.append(
            f"Income stability of {is_pct}% combined with positive repayment "
            f"signals supports predictable repayment capacity."
        )
    elif is_ >= 0.75:
        sentences.append(
            f"Income stability is {is_pct}%, supporting predictable cash flow; "
            f"no prior repayment-like behavior was detected in the transaction history."
        )
    else:
        sentences.append(
            f"Income volatility (stability: {is_pct}%) may limit reliable "
            f"repayment — lenders should verify seasonal factors before extending credit."
        )

    return " ".join(sentences)


def _fire_webhooks(link_id: str, prev: dict, new_score: int, new_rec: str) -> None:
    """POST score-change event to every registered webhook URL."""
    payload = {
        "event": "score_change",
        "merchant_id": link_id,
        "old_score": prev["score"],
        "new_score": new_score,
        "old_recommendation": prev["recommendation"],
        "new_recommendation": new_rec,
        "timestamp": dt.utcnow().isoformat() + "Z",
    }
    if supa:
        try:
            rows = supa.table("webhooks").select("id,callback_url").execute().data
            hooks = rows or []
        except Exception as e:
            print(f"[supabase] webhook read error: {e}")
            with _webhook_lock:
                hooks = list(_webhooks)
    else:
        with _webhook_lock:
            hooks = list(_webhooks)
    for hook in hooks:
        try:
            httpx.post(hook["callback_url"], json=payload, timeout=5.0)
            print(f"[webhook] delivered to {hook['callback_url']}")
        except Exception as e:
            print(f"[webhook] failed → {hook['callback_url']}: {e}")


def _record_score(link_id: str, score: int, rec: str, bank: str,
                  background_tasks: BackgroundTasks) -> None:
    """Store score in history; schedule webhook delivery if thresholds crossed."""
    now_iso = dt.utcnow().isoformat() + "Z"

    # Read previous score (Supabase first, fall back to in-memory)
    prev = None
    if supa:
        try:
            rows = (supa.table("score_history")
                    .select("score,recommendation")
                    .eq("link_id", link_id)
                    .order("scored_at", desc=True)
                    .limit(1)
                    .execute().data)
            if rows:
                prev = {"score": rows[0]["score"], "recommendation": rows[0]["recommendation"]}
        except Exception as e:
            print(f"[supabase] read error: {e}")
    else:
        with _history_lock:
            prev = _score_history.get(link_id)

    # Write new score
    if supa:
        try:
            supa.table("score_history").insert({
                "link_id": link_id,
                "bank": bank,
                "score": score,
                "recommendation": rec,
                "credit_limit_cop": 300000 if rec == "approve" else (150000 if rec == "review" else 0),
                "scored_at": now_iso,
            }).execute()
        except Exception as e:
            print(f"[supabase] write error: {e}")
    else:
        with _history_lock:
            _score_history[link_id] = {
                "score": score, "recommendation": rec,
                "bank": bank, "timestamp": now_iso,
            }

    if prev:
        delta = abs(score - prev["score"])
        bucket_changed = prev["recommendation"] != rec
        if delta >= 15 or bucket_changed:
            background_tasks.add_task(_fire_webhooks, link_id, prev, score, rec)


app = FastAPI(title="Riél API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# Static seed data — 18 merchants across all risk tiers
_SEED_DATA = [
    {"link_id": "a1b2c3d4-0001-0001-0001-000000000001", "name": "El Patio",                      "bank": "Davivienda",   "score": 77, "rec": "approve",  "limit": 300000},
    {"link_id": "a1b2c3d4-0001-0001-0001-000000000002", "name": "Velásquez",                     "bank": "BBVA México",  "score": 51, "rec": "review",   "limit": 150000},
    {"link_id": "a1b2c3d4-0001-0001-0001-000000000003", "name": "Tienda Nueva",                  "bank": "Banorte",      "score": 22, "rec": "decline",  "limit": 0},
    {"link_id": "a1b2c3d4-0001-0001-0001-000000000004", "name": "Supermercado Familiar Gómez",   "bank": "Bancolombia",  "score": 88, "rec": "approve",  "limit": 800000},
    {"link_id": "a1b2c3d4-0001-0001-0001-000000000005", "name": "Farmacia San Rafael",            "bank": "BBVA México",  "score": 92, "rec": "approve",  "limit": 950000},
    {"link_id": "a1b2c3d4-0001-0001-0001-000000000006", "name": "Hotel Boutique Casa Azul",       "bank": "Davivienda",   "score": 85, "rec": "approve",  "limit": 700000},
    {"link_id": "a1b2c3d4-0001-0001-0001-000000000007", "name": "Restaurante La Fogata",          "bank": "Bancolombia",  "score": 74, "rec": "approve",  "limit": 350000},
    {"link_id": "a1b2c3d4-0001-0001-0001-000000000008", "name": "Tienda Doña Rosa",               "bank": "Davivienda",   "score": 68, "rec": "approve",  "limit": 280000},
    {"link_id": "a1b2c3d4-0001-0001-0001-000000000009", "name": "Ferretería El Tornillo",         "bank": "BBVA México",  "score": 72, "rec": "approve",  "limit": 320000},
    {"link_id": "a1b2c3d4-0001-0001-0001-000000000010", "name": "Panadería San José",             "bank": "Banorte",      "score": 65, "rec": "approve",  "limit": 260000},
    {"link_id": "a1b2c3d4-0001-0001-0001-000000000011", "name": "Miscelánea El Sol",              "bank": "Nequi",        "score": 71, "rec": "approve",  "limit": 300000},
    {"link_id": "a1b2c3d4-0001-0001-0001-000000000012", "name": "Talleres Mecánicos García",      "bank": "Bancolombia",  "score": 55, "rec": "review",   "limit": 100000},
    {"link_id": "a1b2c3d4-0001-0001-0001-000000000013", "name": "Papelería Central",              "bank": "Davivienda",   "score": 48, "rec": "review",   "limit": 80000},
    {"link_id": "a1b2c3d4-0001-0001-0001-000000000014", "name": "Distribuidora Ortiz",            "bank": "BBVA México",  "score": 52, "rec": "review",   "limit": 90000},
    {"link_id": "a1b2c3d4-0001-0001-0001-000000000015", "name": "Lavandería Expres",              "bank": "Banorte",      "score": 44, "rec": "review",   "limit": 70000},
    {"link_id": "a1b2c3d4-0001-0001-0001-000000000016", "name": "Cantina El Refugio",             "bank": "Nequi",        "score": 31, "rec": "decline",  "limit": 0},
    {"link_id": "a1b2c3d4-0001-0001-0001-000000000017", "name": "Taquería Los Compadres",         "bank": "Bancolombia",  "score": 25, "rec": "decline",  "limit": 0},
    {"link_id": "a1b2c3d4-0001-0001-0001-000000000018", "name": "Servicio Técnico Rápido",        "bank": "Davivienda",   "score": 38, "rec": "decline",  "limit": 0},
]

@app.on_event("startup")
def _seed_score_history() -> None:
    """Pre-populate score history with 18 mock profiles spread across last 8 weeks."""
    import random
    random.seed(42)
    now = dt.utcnow()
    if supa:
        try:
            existing = supa.table("score_history").select("id").limit(1).execute()
            if existing.data:
                return  # already seeded
            rows = []
            for m in _SEED_DATA:
                days_ago = random.randint(0, 56)
                ts = (now - timedelta(days=days_ago)).isoformat() + "Z"
                rows.append({
                    "link_id": m["link_id"],
                    "merchant_name": m["name"],
                    "bank": m["bank"],
                    "score": m["score"],
                    "recommendation": m["rec"],
                    "credit_limit_cop": m["limit"],
                    "scored_at": ts,
                })
            supa.table("score_history").insert(rows).execute()
        except Exception as e:
            print(f"[supabase] seed error: {e}")
    else:
        for m in _SEED_DATA:
            days_ago = random.randint(0, 56)
            ts = (now - timedelta(days=days_ago)).isoformat() + "Z"
            with _history_lock:
                _score_history[m["link_id"]] = {
                    "score": m["score"],
                    "recommendation": m["rec"],
                    "bank": m["bank"],
                    "timestamp": ts,
                }


class WebhookRequest(BaseModel):
    callback_url: str


class ScoreRequest(BaseModel):
    link_id: str


class EvaluateRequest(BaseModel):
    link_id: str
    requested_amount: float


class ProcureRequest(BaseModel):
    requested_amount_cop: float


class ConnectRequest(BaseModel):
    bank: str
    username: str
    password: str
    otp: Optional[str] = None


@app.get("/")
def root():
    return {"status": "Riél API is running", "version": "0.1.0"}


@app.post("/belvo-token")
def belvo_token():
    response = requests.post(
        f"{BELVO_BASE_URL}/api/token/",
        json={
            "id": BELVO_SECRET_ID,
            "password": BELVO_SECRET_PASSWORD,
            "scopes": "read_institutions,read_links",
        },
    )
    if response.status_code not in (200, 201):
        raise HTTPException(status_code=response.status_code, detail=response.json())
    return response.json()


@app.post("/score")
def score(request: ScoreRequest, background_tasks: BackgroundTasks,
          provider: Optional[str] = None, _key: dict = Depends(verify_api_key)):
    t_start = time.time()

    try:
        dp = get_provider(provider)
    except (ValueError, Exception) as e:
        raise HTTPException(status_code=400 if isinstance(e, ValueError) else 502,
                            detail=str(e))

    try:
        transactions = dp.get_transactions(request.link_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Provider error: {e}")

    features = extract_features(transactions)
    result = calculate_riel_score(features)

    latency_ms = round((time.time() - t_start) * 1000, 2)
    confidence = "high" if len(transactions) > 30 else "medium"

    _record_score(request.link_id, result["riel_score"],
                  result["recommendation"], dp.provider_name(), background_tasks)

    return {
        "riel_score": result["riel_score"],
        "recommendation": result["recommendation"],
        "suggested_limit_cop": result["suggested_limit_cop"],
        "confidence": confidence,
        "features": features,
        "data_cost_usd": 0.08,
        "latency_ms": latency_ms,
        "provider": dp.provider_name(),
    }


@app.post("/agent/evaluate")
def agent_evaluate(request: EvaluateRequest):
    # 1. Score
    t_start = time.time()

    dp = get_provider()
    try:
        transactions = dp.get_transactions(request.link_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Provider error: {e}")
    demo = False

    features = extract_features(transactions)
    score_result = calculate_riel_score(features)

    latency_ms = round((time.time() - t_start) * 1000, 2)

    recommendation = score_result["recommendation"]
    suggested_limit_cop = score_result["suggested_limit_cop"]

    # 2. Decline path
    if recommendation == "decline":
        return {
            "decision": "decline",
            "message": "Application does not meet minimum credit criteria.",
            "riel_score": score_result["riel_score"],
            "recommendation": recommendation,
            "features": features,
            "latency_ms": latency_ms,
            "demo": demo,
        }

    # 3. Approve path — create Stripe Payment Link
    if not stripe.api_key:
        raise HTTPException(status_code=503, detail="Stripe not configured. Set STRIPE_SECRET_KEY.")

    disbursement_cop = min(request.requested_amount, suggested_limit_cop)
    disbursement_usd_cents = max(1, round((disbursement_cop / COP_TO_USD) * 100))

    try:
        price = stripe.Price.create(
            currency="usd",
            unit_amount=disbursement_usd_cents,
            product_data={"name": f"Riél Credit · COP {int(disbursement_cop):,}"},
        )
        payment_link = stripe.PaymentLink.create(
            line_items=[{"price": price.id, "quantity": 1}],
        )
    except stripe.StripeError as e:
        raise HTTPException(status_code=502, detail=f"Stripe error: {e.user_message}")

    return {
        "decision": "approve",
        "riel_score": score_result["riel_score"],
        "recommendation": recommendation,
        "requested_amount_cop": request.requested_amount,
        "approved_amount_cop": disbursement_cop,
        "approved_amount_usd": round(disbursement_usd_cents / 100, 2),
        "payment_url": payment_link.url,
        "features": features,
        "latency_ms": latency_ms,
        "demo": demo,
    }


# ── x402 Data Aggregator ────────────────────────────────────────────────────

@app.get("/data/transactions")
def data_transactions(authorization: Optional[str] = Header(default=None)):
    """
    Returns transaction data for $0.08 USD via x402 / Stripe MPP (SPT).
    Callers without a valid payment credential receive HTTP 402 with a
    signed challengeId to complete payment before retrying.
    """
    token = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:]

    if not token or not _verify_challenge_id(token):
        challenge_id = _make_challenge_id()
        return JSONResponse(
            status_code=402,
            content={
                "type": "https://riel.dev/problems/payment-required",
                "title": "Payment Required",
                "status": 402,
                "detail": "This endpoint costs $0.08 USD per call via Stripe MPP (SPT). "
                          "Sign the challengeId and retry with Authorization: Bearer <challengeId>.",
                "price_usd": 0.08,
                "method": "x402/stripe-spt",
                "challengeId": challenge_id,
            },
        )

    with open(os.path.join(BASE_DIR, "sample_transactions.json")) as f:
        transactions = json.load(f)
    return {"transactions": transactions, "count": len(transactions)}


# ── Autonomous Procurement Agent ─────────────────────────────────────────────

@app.post("/agent/procure")
def agent_procure(request: ProcureRequest, provider: Optional[str] = None,
                  _key: dict = Depends(verify_api_key)):
    """
    Autonomously procures transaction data via the x402 challenge/response
    protocol, scores it, and returns the credit decision.
    The 402 handshake runs in-process to avoid self-HTTP calls that break
    in deployed environments without a SELF_BASE_URL.
    """
    t_start = time.time()

    try:
        dp = get_provider(provider)
    except (ValueError, Exception) as e:
        raise HTTPException(status_code=400 if isinstance(e, ValueError) else 502,
                            detail=str(e))

    # Step 1 — x402 challenge (in-process)
    challenge_id = _make_challenge_id()
    print(f"[procure] 402 received — paying for data... (challengeId: {challenge_id[:16]}…)")

    # Step 2 — verify the challenge (simulates SPT payment + retry)
    if not _verify_challenge_id(challenge_id):
        raise HTTPException(status_code=502, detail="x402 challenge verification failed.")

    try:
        transactions = dp.get_transactions("procure")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Provider error: {e}")
    print(f"[procure] {len(transactions)} transactions acquired via {dp.provider_name()}.")

    # Step 3 — score
    features = extract_features(transactions)
    result = calculate_riel_score(features)
    latency_ms = round((time.time() - t_start) * 1000, 2)
    confidence = "high" if len(transactions) > 30 else "medium"

    return {
        "riel_score": result["riel_score"],
        "recommendation": result["recommendation"],
        "suggested_limit_cop": result["suggested_limit_cop"],
        "requested_amount_cop": request.requested_amount_cop,
        "confidence": confidence,
        "features": features,
        "data_source": "x402_aggregator",
        "provider": dp.provider_name(),
        "payment_usd": 0.08,
        "autonomous": True,
        "latency_ms": latency_ms,
    }


@app.post("/connect/score")
def connect_score(request: ConnectRequest):
    """
    Bank-linking score endpoint for the /connect flow.
    In mock mode: returns El Patio profile (score 77, approve) regardless of credentials.
    In prometeo mode: logs in with the provided credentials and scores the first account.
    """
    t_start = time.time()
    provider_key = os.getenv("DATA_PROVIDER", "prometeo").lower()

    if provider_key not in ("mock", "prometeo"):
        raise HTTPException(status_code=400, detail=f"Unsupported provider '{provider_key}'. Valid options: mock, prometeo.")

    if provider_key == "mock":
        from providers.mock_provider import MockProvider
        dp = MockProvider()
        transactions = dp.get_transactions("a1b2c3d4-0001-0001-0001-000000000001")
        provider_used = "mock"
    else:
        try:
            # AnyIO worker threads have no event loop; give this thread one
            # so the Prometeo SDK's internal asyncio.get_event_loop() calls succeed.
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            from prometeo import Client as PrometeoClient
            client = PrometeoClient(os.getenv("PROMETEO_API_KEY"), environment="sandbox")
            login_kwargs = dict(
                provider=request.bank,
                username=request.username,
                password=request.password,
            )
            if request.otp:
                login_kwargs["otp"] = request.otp
            session = client.banking.login(**login_kwargs)
            accounts = session.get_accounts()
            if not accounts:
                raise HTTPException(status_code=422, detail="No accounts found for this user.")
            account = accounts[0]
            date_to = date.today()
            date_from = date_to - timedelta(days=90)
            movements = account.get_movements(date_from, date_to)
            transactions = [
                {
                    "detail": m.detail,
                    "debit": m.debit,
                    "credit": m.credit,
                    "date": str(m.date) if hasattr(m, "date") else None,
                }
                for m in movements
            ]
            provider_used = "prometeo"
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Bank connection error: {e}")

    features = extract_features(transactions)
    result = calculate_riel_score(features)
    latency_ms = round((time.time() - t_start) * 1000, 2)
    confidence = "high" if len(transactions) > 30 else "medium"

    return {
        "riel_score": result["riel_score"],
        "recommendation": result["recommendation"],
        "suggested_limit_cop": result["suggested_limit_cop"],
        "confidence": confidence,
        "features": features,
        "provider": provider_used,
        "bank": request.bank,
        "latency_ms": latency_ms,
    }


@app.post("/create-widget-session")
def create_widget_session():
    response = requests.post(
        f"{BELVO_BASE_URL}/api/token/",
        json={
            "id": BELVO_SECRET_ID,
            "password": BELVO_SECRET_PASSWORD,
            "scopes": "read_institutions,read_links,write_links",
        },
    )
    if response.status_code not in (200, 201):
        raise HTTPException(status_code=response.status_code, detail=response.json())
    return response.json()


@app.get("/me")
def me(key_info: dict = Depends(verify_api_key)):
    return {**key_info}


@app.get("/merchants")
def list_merchants():
    """Returns merchant profiles from Supabase score_history, falling back to MockProvider."""
    if supa:
        try:
            rows = (supa.table("score_history")
                    .select("link_id,merchant_name,bank")
                    .execute().data)
            if rows:
                return {"merchants": [
                    {"link_id": r["link_id"], "name": r["merchant_name"], "bank": r["bank"]}
                    for r in rows
                ]}
        except Exception as e:
            print(f"[supabase] merchants read error: {e}")
    from providers.mock_provider import MockProvider
    return {"merchants": MockProvider().list_merchants()}


@app.get("/connect")
def connect():
    return FileResponse(os.path.join(BASE_DIR, "connect.html"))


@app.get("/demo")
def demo():
    return FileResponse(os.path.join(BASE_DIR, "demo.html"))


@app.get("/health")
def health():
    return {"status": "healthy", "provider": os.getenv("DATA_PROVIDER", "prometeo")}


# ── Score Explainability ───────────────────────────────────────────────────────

@app.get("/score/{link_id}/explain")
def score_explain(link_id: str, provider: Optional[str] = None,
                  _key: dict = Depends(verify_api_key)):
    """
    Returns a plain-language explanation of why a merchant received their score.
    Re-runs the scoring pipeline; no caching.
    """
    try:
        dp = get_provider(provider)
    except (ValueError, Exception) as e:
        raise HTTPException(status_code=400 if isinstance(e, ValueError) else 502,
                            detail=str(e))

    try:
        transactions = dp.get_transactions(link_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Provider error: {e}")

    features = extract_features(transactions)
    result = calculate_riel_score(features)
    explanation = _generate_explanation(features, result)

    return {
        "link_id": link_id,
        "riel_score": result["riel_score"],
        "recommendation": result["recommendation"],
        "suggested_limit_cop": result["suggested_limit_cop"],
        "explanation": explanation,
        "features": features,
        "provider": dp.provider_name(),
    }


# ── Argentina Scoring ──────────────────────────────────────────────────────────

@app.get("/argentina/score/{link_id}")
def argentina_score(link_id: str, _key: dict = Depends(verify_api_key)):
    """
    Run the Argentina 5-metric risk pipeline for a given link_id.
    Returns metrics + action (healthy/monitor/review_now/reduce_exposure/opportunity).
    """
    try:
        dp = get_provider()
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))

    try:
        transactions = dp.get_transactions(link_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Provider error: {e}")

    metrics = extract_argentina_features(transactions)
    result = score_argentina(metrics)

    return {
        "link_id": link_id,
        "survival_runway_days": metrics["survival_runway_days"],
        "real_cash_coverage": metrics["real_cash_coverage"],
        "fx_mismatch_exposure": metrics["fx_mismatch_exposure"],
        "revenue_concentration": metrics["revenue_concentration"],
        "deterioration_index": metrics["deterioration_index"],
        "action": result["action"],
        "metric_lights": result["metric_lights"],
        "provider": dp.provider_name(),
    }


@app.get("/argentina/portfolio")
def argentina_portfolio(_key: dict = Depends(verify_api_key)):
    """
    Return portfolio-level aggregates + per-merchant rows for all Argentina merchants.
    Runs the full 5-metric pipeline for each merchant via the configured provider.
    """
    try:
        dp = get_provider()
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))

    from providers.mock_provider import MOCK_MERCHANTS_AR
    merchants = []
    for link_id, meta in MOCK_MERCHANTS_AR.items():
        try:
            txs = dp.get_transactions(link_id)
        except Exception as e:
            continue  # skip merchants that fail; don't abort the whole portfolio
        merchants.append({
            "link_id":      link_id,
            "name":         meta["name"],
            "sector":       meta.get("sector", "other"),
            "bank":         meta.get("bank", ""),
            "transactions": txs,
        })

    return build_portfolio(merchants)


@app.get("/argentina/merchant/{link_id}/data")
def argentina_merchant_data(link_id: str, _key: dict = Depends(verify_api_key)):
    """
    Full metrics + 30/60/90d trend for a single Argentina merchant.
    """
    try:
        dp = get_provider()
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))

    try:
        txs = dp.get_transactions(link_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Provider error: {e}")

    from providers.mock_provider import MOCK_MERCHANTS_AR
    meta = MOCK_MERCHANTS_AR.get(link_id, {})
    name   = meta.get("name",   link_id)
    sector = meta.get("sector", "other")
    bank   = meta.get("bank",   "")

    return build_merchant_detail(link_id, name, sector, bank, txs)


# ── Webhooks ───────────────────────────────────────────────────────────────────

@app.post("/webhooks", status_code=201)
def register_webhook(request: WebhookRequest,
                     key_info: dict = Depends(verify_api_key)):
    """Register a callback URL to receive score-change events."""
    if supa:
        try:
            row = supa.table("webhooks").insert({
                "client": key_info["client"],
                "callback_url": request.callback_url,
            }).execute().data[0]
            return {"id": row["id"], "client": row["client"],
                    "callback_url": row["callback_url"], "created": row["created_at"]}
        except Exception as e:
            print(f"[supabase] webhook insert error: {e}")
    hook = {
        "id": str(uuid.uuid4()),
        "client": key_info["client"],
        "callback_url": request.callback_url,
        "created": dt.utcnow().isoformat() + "Z",
    }
    with _webhook_lock:
        _webhooks.append(hook)
    return hook


@app.get("/webhooks")
def list_webhooks(key_info: dict = Depends(verify_api_key)):
    """List webhooks registered by the calling API key's client."""
    if supa:
        try:
            rows = (supa.table("webhooks")
                    .select("id,client,callback_url,created_at")
                    .eq("client", key_info["client"])
                    .execute().data)
            hooks = [{"id": r["id"], "client": r["client"],
                      "callback_url": r["callback_url"], "created": r["created_at"]}
                     for r in (rows or [])]
            return {"webhooks": hooks, "count": len(hooks)}
        except Exception as e:
            print(f"[supabase] webhook list error: {e}")
    with _webhook_lock:
        hooks = [h for h in _webhooks if h["client"] == key_info["client"]]
    return {"webhooks": hooks, "count": len(hooks)}


@app.post("/webhooks/test")
def test_webhook_delivery(key_info: dict = Depends(verify_api_key)):
    """
    Immediately fires a test payload to every webhook registered by this client.
    Use this to verify your callback_url is reachable without waiting for a score change.
    """
    payload = {
        "event": "test",
        "message": "Test webhook delivery from Riél API.",
        "timestamp": dt.utcnow().isoformat() + "Z",
    }
    if supa:
        try:
            rows = (supa.table("webhooks")
                    .select("id,callback_url")
                    .eq("client", key_info["client"])
                    .execute().data)
            hooks = rows or []
        except Exception as e:
            print(f"[supabase] webhook read error: {e}")
            with _webhook_lock:
                hooks = [h for h in _webhooks if h["client"] == key_info["client"]]
    else:
        with _webhook_lock:
            hooks = [h for h in _webhooks if h["client"] == key_info["client"]]

    results = []
    for hook in hooks:
        try:
            r = httpx.post(hook["callback_url"], json=payload, timeout=5.0)
            results.append({"id": hook["id"], "url": hook["callback_url"],
                            "status": r.status_code, "ok": True})
        except Exception as e:
            results.append({"id": hook["id"], "url": hook["callback_url"],
                            "error": str(e), "ok": False})

    return {"fired": len(results), "results": results}


@app.delete("/webhooks/{webhook_id}", status_code=204)
def delete_webhook(webhook_id: str, key_info: dict = Depends(verify_api_key)):
    """Delete a webhook registration."""
    if supa:
        try:
            rows = (supa.table("webhooks")
                    .delete()
                    .eq("id", webhook_id)
                    .eq("client", key_info["client"])
                    .execute().data)
            if not rows:
                raise HTTPException(status_code=404, detail="Webhook not found.")
            return
        except HTTPException:
            raise
        except Exception as e:
            print(f"[supabase] webhook delete error: {e}")
    with _webhook_lock:
        before = len(_webhooks)
        _webhooks[:] = [
            h for h in _webhooks
            if not (h["id"] == webhook_id and h["client"] == key_info["client"])
        ]
        removed = before - len(_webhooks)
    if not removed:
        raise HTTPException(status_code=404, detail="Webhook not found.")


# ── Lender magic-link auth ────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    email: str


def get_current_lender(lender_session: Optional[str] = Cookie(default=None)) -> str:
    if not lender_session:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        return _serializer.loads(lender_session, max_age=86400)
    except (SignatureExpired, BadSignature):
        raise HTTPException(status_code=401, detail="Session invalid or expired")


@app.post("/lender/login-request")
def lender_login_request(body: LoginRequest):
    if body.email in ALLOWED_LENDER_EMAILS:
        token = _serializer.dumps(body.email)
        base = os.getenv("SELF_BASE_URL", "http://localhost:8000")
        link = f"{base}/lender/magic-login?token={token}"
        print(f"[magic-link] {link}")
        return {"message": "If the email exists, we sent a link", "link": link}
    return {"message": "If the email exists, we sent a link"}


@app.get("/lender/magic-login")
def lender_magic_login(token: str):
    try:
        email = _serializer.loads(token, max_age=900)
    except SignatureExpired:
        raise HTTPException(status_code=400, detail="Magic link expired")
    except BadSignature:
        raise HTTPException(status_code=400, detail="Magic link invalid")
    resp = RedirectResponse(url="/dashboard", status_code=302)
    session_token = _serializer.dumps(email)
    resp.set_cookie("lender_session", session_token, httponly=True,
                    secure=False, max_age=86400, samesite="lax")
    return resp


@app.post("/lender/logout")
def lender_logout():
    resp = JSONResponse({"message": "Logged out"})
    resp.delete_cookie("lender_session")
    return resp


# ── Lender Dashboard ──────────────────────────────────────────────────────────

@app.get("/dashboard")
def dashboard(lender: str = Depends(get_current_lender)):
    return FileResponse(os.path.join(BASE_DIR, "dashboard.html"))


@app.get("/dashboard/stats")
def dashboard_stats(_key: dict = Depends(verify_api_key),
                    lender: str = Depends(get_current_lender)):
    """
    Returns aggregated stats for the lender dashboard charts.
    Reads from Supabase score_history table if configured, else in-memory fallback.
    """
    if supa:
        try:
            rows = supa.table("score_history").select("score,recommendation,bank").execute().data
            history = rows or []
        except Exception as e:
            print(f"[supabase] stats read error: {e}")
            with _history_lock:
                history = list(_score_history.values())
    else:
        with _history_lock:
            history = list(_score_history.values())

    # 1 — Score distribution
    buckets = {"0-20": 0, "21-40": 0, "41-60": 0, "61-80": 0, "81-100": 0}
    for entry in history:
        s = entry["score"]
        if s <= 20:    buckets["0-20"] += 1
        elif s <= 40:  buckets["21-40"] += 1
        elif s <= 60:  buckets["41-60"] += 1
        elif s <= 80:  buckets["61-80"] += 1
        else:          buckets["81-100"] += 1

    # 2 — Approval rate over last 8 weeks (synthetic for demo;
    #     in production: GROUP BY week from Supabase scores table)
    today = date.today()
    weekly_labels, weekly_rates = [], []
    # Seed deterministic synthetic rates from history
    approval_counts = [entry["recommendation"] == "approve" for entry in history]
    base_rate = round((sum(approval_counts) / len(approval_counts) * 100) if history else 60, 1)
    for w in range(7, -1, -1):
        week_start = today - timedelta(weeks=w)
        weekly_labels.append(week_start.strftime("%b %d"))
        # Vary ±8 pts around base to simulate weekly movement
        variance = ((w * 3) % 17) - 8
        weekly_rates.append(min(100, max(0, round(base_rate + variance, 1))))

    # 3 — Average credit limit by bank (from score history)
    bank_totals: dict[str, list] = {}
    for entry in history:
        bank = entry.get("bank", "Unknown")
        limit = 300000 if entry["recommendation"] == "approve" else (
            150000 if entry["recommendation"] == "review" else 0
        )
        bank_totals.setdefault(bank, []).append(limit)
    avg_by_bank = {
        bank: round(sum(limits) / len(limits))
        for bank, limits in bank_totals.items()
    }

    return {
        "score_distribution": buckets,
        "approval_rate_weekly": {
            "labels": weekly_labels,
            "data": weekly_rates,
        },
        "avg_limit_by_bank": avg_by_bank,
        "total_merchants_scored": len(history),
        "overall_approval_rate": round(
            sum(1 for e in history if e["recommendation"] == "approve") / len(history) * 100
            if history else 0, 1
        ),
    }

