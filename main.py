import base64
import hashlib
import hmac
import json
import secrets
import time
import os
from typing import Optional

import stripe
import requests
from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from features import extract_features
from scorer import calculate_riel_score

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

BELVO_SECRET_ID = os.getenv("BELVO_SECRET_ID")
BELVO_SECRET_PASSWORD = os.getenv("BELVO_SECRET_PASSWORD")
BELVO_ENV = os.getenv("BELVO_ENV", "sandbox")
BELVO_BASE_URL = "https://sandbox.belvo.com"

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
MPP_SECRET = os.getenv("STRIPE_MPP_SECRET", secrets.token_hex(32))
SELF_BASE_URL = os.getenv("SELF_BASE_URL", "http://localhost:8000")

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

app = FastAPI(title="Riél API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ScoreRequest(BaseModel):
    link_id: str


class EvaluateRequest(BaseModel):
    link_id: str
    requested_amount: float


class ProcureRequest(BaseModel):
    requested_amount_cop: float


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
def score(request: ScoreRequest):
    t_start = time.time()

    if request.link_id == "demo":
        with open(os.path.join(BASE_DIR, "sample_transactions.json")) as f:
            transactions = json.load(f)
        demo = True
    else:
        raise HTTPException(status_code=501, detail="Live Belvo scoring not yet implemented. Use link_id='demo' to run the demo.")

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
        "data_cost_usd": 0.08,
        "latency_ms": latency_ms,
        "demo": demo,
    }


@app.post("/agent/evaluate")
def agent_evaluate(request: EvaluateRequest):
    # 1. Score
    t_start = time.time()

    if request.link_id == "demo":
        with open(os.path.join(BASE_DIR, "sample_transactions.json")) as f:
            transactions = json.load(f)
        demo = True
    else:
        raise HTTPException(status_code=501, detail="Live Belvo scoring not yet implemented. Use link_id='demo'.")

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
def agent_procure(request: ProcureRequest):
    """
    Autonomously procures transaction data via the x402 /data/transactions
    endpoint, pays the $0.08 SPT challenge, scores the data, and returns
    the credit decision.
    """
    t_start = time.time()
    url = f"{SELF_BASE_URL}/data/transactions"

    # Step 1 — attempt without credential
    r1 = requests.get(url)

    if r1.status_code == 402:
        challenge = r1.json()
        challenge_id = challenge.get("challengeId")
        print(f"[procure] 402 received — paying for data... (challengeId: {challenge_id[:16]}…)")

        # Step 2 — retry with the challengeId as Bearer token (simulates SPT payment)
        r2 = requests.get(url, headers={"Authorization": f"Bearer {challenge_id}"})

        if r2.status_code != 200:
            raise HTTPException(status_code=502, detail="Data provider rejected payment credential.")
        payload = r2.json()
    elif r1.status_code == 200:
        payload = r1.json()
    else:
        raise HTTPException(status_code=502, detail=f"Data provider error: {r1.status_code}")

    transactions = payload["transactions"]
    print(f"[procure] {len(transactions)} transactions acquired.")

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
        "payment_usd": 0.08,
        "autonomous": True,
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


@app.get("/connect")
def connect():
    return FileResponse(os.path.join(BASE_DIR, "connect.html"))


@app.get("/demo")
def demo():
    return FileResponse(os.path.join(BASE_DIR, "demo.html"))


@app.get("/health")
def health():
    return {"status": "healthy", "belvo_env": BELVO_ENV}
