"""
api/main.py – Lättviktig FastAPI-server som exponerar pipeline-resultaten
(results/*.csv + stats.json) som JSON för frontend-dashboarden.

Servern läser bara redan genererade filer från `python main.py` – den
kör inga modeller eller backtester själv. Kör pipelinen om
`results/`-filerna saknas eller är gamla.

Användning:
  uvicorn api.main:app --reload --port 8000
"""

import json
from pathlib import Path
from typing import Optional

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
import config

app = FastAPI(title="Momentum ML API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

RESULTS_DIR = Path(config.RESULTS_DIR)


def _require(path: Path) -> Path:
    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"{path.name} saknas – kör 'python main.py' först för att generera resultat.",
        )
    return path


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/stats")
def get_stats():
    path = _require(RESULTS_DIR / "stats.json")
    with open(path) as f:
        return json.load(f)


@app.get("/api/signals/latest")
def get_latest_signals():
    path = _require(RESULTS_DIR / "signals.csv")
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    latest = df.groupby("ticker").last().reset_index()
    latest = latest.sort_values("prob_up", ascending=False)
    return latest.to_dict(orient="records")


@app.get("/api/signals/history")
def get_signal_history(ticker: Optional[str] = None, limit: int = 260):
    path = _require(RESULTS_DIR / "signals.csv")
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    if ticker:
        df = df[df["ticker"] == ticker]
        if df.empty:
            raise HTTPException(status_code=404, detail=f"Ingen data för ticker '{ticker}'.")
    df = df.sort_index().tail(limit).reset_index()
    df = df.rename(columns={df.columns[0]: "date"})
    return df.to_dict(orient="records")


@app.get("/api/portfolio")
def get_portfolio(limit: int = 1000):
    path = _require(RESULTS_DIR / "portfolio.csv")
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    pv = df["portfolio_value"]
    df["drawdown"] = pv / pv.cummax() - 1
    df = df.sort_index().tail(limit).reset_index()
    df = df.rename(columns={df.columns[0]: "date"})
    return df.to_dict(orient="records")


@app.get("/api/drift")
def get_drift(limit: int = 260):
    path = _require(RESULTS_DIR / "drift_report.csv")
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    df = df.sort_index().tail(limit).reset_index()
    df = df.rename(columns={df.columns[0]: "date"})
    return df.to_dict(orient="records")


@app.get("/api/regime")
def get_regime_breakdown():
    path = _require(RESULTS_DIR / "regime_breakdown.csv")
    df = pd.read_csv(path, index_col=0).reset_index()
    return df.to_dict(orient="records")
