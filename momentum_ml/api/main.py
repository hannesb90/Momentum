"""
api/main.py – Lättviktig FastAPI-server som exponerar pipeline-resultaten
(results/*.csv + stats.json) som JSON för frontend-dashboarden.

Servern läser bara redan genererade filer från `python main.py` – den
kör inga modeller eller backtester själv. Kör pipelinen om
`results/`-filerna saknas eller är gamla.

Användning:
  uvicorn api.main:app --reload --port 8001
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


def _seg_dir(segment: Optional[str]) -> Path:
    """Resultatkatalog för ett segment (storbolag/småbolag). Okänt/None faller
    tillbaka på default-segmentet, så befintliga anrop utan ?segment fungerar."""
    cfg = config.SEGMENTS.get(segment) if segment else None
    if cfg is None:
        cfg = config.SEGMENTS[config.DEFAULT_SEGMENT]
    return Path(cfg["results_dir"])


def _require(path: Path) -> Path:
    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"{path.name} saknas – kör 'python main.py' först för att generera resultat.",
        )
    return path


@app.get("/api/segments")
def get_segments():
    """Tillgängliga segment för frontend-toggeln."""
    return {
        "default": config.DEFAULT_SEGMENT,
        "segments": [{"id": k, "label": v["label"]} for k, v in config.SEGMENTS.items()],
    }


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/stats")
def get_stats(segment: Optional[str] = None):
    path = _require(_seg_dir(segment) / "stats.json")
    with open(path) as f:
        return json.load(f)


@app.get("/api/signals/latest")
def get_latest_signals(segment: Optional[str] = None):
    path = _require(_seg_dir(segment) / "signals.csv")
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    latest = df.groupby("ticker").last().reset_index()
    latest = latest.sort_values("prob_up", ascending=False)
    return latest.to_dict(orient="records")


@app.get("/api/signals/history")
def get_signal_history(ticker: Optional[str] = None, limit: int = 260, segment: Optional[str] = None):
    path = _require(_seg_dir(segment) / "signals.csv")
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    if ticker:
        df = df[df["ticker"] == ticker]
        if df.empty:
            raise HTTPException(status_code=404, detail=f"Ingen data för ticker '{ticker}'.")
    df = df.sort_index().tail(limit).reset_index()
    df = df.rename(columns={df.columns[0]: "date"})
    return df.to_dict(orient="records")


@app.get("/api/portfolio")
def get_portfolio(limit: int = 1000, segment: Optional[str] = None):
    path = _require(_seg_dir(segment) / "portfolio.csv")
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    pv = df["portfolio_value"]
    df["drawdown"] = pv / pv.cummax() - 1
    df = df.sort_index().tail(limit).reset_index()
    df = df.rename(columns={df.columns[0]: "date"})
    return df.to_dict(orient="records")


@app.get("/api/drift")
def get_drift(limit: int = 260, segment: Optional[str] = None):
    path = _require(_seg_dir(segment) / "drift_report.csv")
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    df = df.sort_index().tail(limit).reset_index()
    df = df.rename(columns={df.columns[0]: "date"})
    return df.to_dict(orient="records")


@app.get("/api/regime")
def get_regime_breakdown(segment: Optional[str] = None):
    path = _require(_seg_dir(segment) / "regime_breakdown.csv")
    df = pd.read_csv(path, index_col=0).reset_index()
    return df.to_dict(orient="records")


@app.get("/api/sector-momentum")
def get_sector_momentum(segment: Optional[str] = None):
    path = _require(_seg_dir(segment) / "sector_momentum.csv")
    df = pd.read_csv(path)
    return df.to_dict(orient="records")


@app.get("/api/prices")
def get_prices(ticker: str, limit: int = 260, segment: Optional[str] = None):
    """Per-ticker prishistorik (close) för aktiedetaljvyns kursgraf."""
    path = _seg_dir(segment) / "prices.csv"
    if not path.exists():
        return []
    df = pd.read_csv(path)
    df = df[df["ticker"] == ticker].sort_values("date").tail(limit)
    return df[["date", "close"]].to_dict(orient="records")


@app.get("/api/paper-ledger")
def get_paper_ledger(limit: int = 520, segment: Optional[str] = None):
    """
    Framåtblickande pappershandels-historik (live track record). Returnerar
    en tom lista om liggaren ännu inte börjat byggas (första körningarna) i
    stället för 404 – frontend visar då ett 'ingen historik än'-tillstånd.
    """
    path = _seg_dir(segment) / "paper_ledger.csv"
    if not path.exists():
        return []
    df = pd.read_csv(path).tail(limit)
    return df.to_dict(orient="records")
