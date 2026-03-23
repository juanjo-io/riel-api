import json
import time
import os

import stripe
import requests
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
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

COP_TO_USD = 4000  # 1 USD ≈ 4 000 COP (fixed rate for sandbox)

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
