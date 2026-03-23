import json
import time
import os

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from features import extract_features
from scorer import calculate_riel_score

load_dotenv()

BELVO_SECRET_ID = os.getenv("BELVO_SECRET_ID")
BELVO_SECRET_PASSWORD = os.getenv("BELVO_SECRET_PASSWORD")
BELVO_ENV = os.getenv("BELVO_ENV", "sandbox")
BELVO_BASE_URL = "https://sandbox.belvo.com"

app = FastAPI(title="Riél API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ScoreRequest(BaseModel):
    link_id: str


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

    with open("sample_transactions.json") as f:
        transactions = json.load(f)

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
    return FileResponse("connect.html")


@app.get("/health")
def health():
    return {"status": "healthy", "belvo_env": BELVO_ENV}
