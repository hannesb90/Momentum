"""
macro_data.py – Bakgrunds-/makrodata (räntor, obligationer, index, VIX, FX, råvaror).

Hämtar fria Yahoo-serier (config.MACRO_SERIES) och cachar dem, med en enkel
load() som andra moduler kan räkna på: regim, ränte-/kreditstress, flight-to-safety
osv. Helt token-fritt, dagsfärsk EOD-data.

Körs på Pi:n (molncontainern når inte Yahoo):
    python macro_data.py fetch     # hämta/uppdatera alla serier → cache
    python macro_data.py show      # nyckel-indikatorer (räntekurva, kreditspread, VIX...)
"""
import sys
import json
import pickle
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import config

try:
    import yfinance as yf
except ImportError:
    yf = None


def _cache_file() -> Path:
    d = Path(config.MACRO_CACHE_DIR)
    d.mkdir(parents=True, exist_ok=True)
    return d / "macro_weekly.pkl"


def fetch(interval: str = "1wk") -> pd.DataFrame:
    """Hämtar alla MACRO_SERIES (justerad Close) → wide DataFrame (datum × namn), cachas."""
    if yf is None:
        raise RuntimeError("paketet 'yfinance' saknas – pip install yfinance")
    names = list(config.MACRO_SERIES)
    tickers = list(config.MACRO_SERIES.values())
    print(f"[macro] hämtar {len(tickers)} serier från Yahoo ({interval})...")
    raw = yf.download(tickers, start=config.START_DATE, interval=interval,
                      auto_adjust=True, progress=False, threads=True)
    cols = {}
    for name, tk in config.MACRO_SERIES.items():
        try:
            s = raw["Close"][tk] if isinstance(raw.columns, pd.MultiIndex) else raw["Close"]
            s = s.dropna()
            if len(s):
                cols[name] = s
            else:
                print(f"  [WARN] {name} ({tk}): ingen data")
        except (KeyError, TypeError):
            print(f"  [WARN] {name} ({tk}): saknas i svaret")
    df = pd.DataFrame(cols).sort_index()
    df.index = pd.to_datetime(df.index)
    with open(_cache_file(), "wb") as f:
        pickle.dump(df, f)
    print(f"[macro] {df.shape[1]} serier, {len(df)} veckor → {_cache_file()}")
    return df


def load() -> pd.DataFrame:
    """Laddar den cachade makrodatan (wide DataFrame). Kör fetch() först om tom."""
    p = _cache_file()
    if not p.exists():
        raise FileNotFoundError(f"{p} saknas – kör 'python macro_data.py fetch' först.")
    with open(p, "rb") as f:
        return pickle.load(f)


def _chg(s: pd.Series, weeks: int):
    s = s.dropna()
    if len(s) <= weeks:
        return None
    return float(s.iloc[-1] / s.iloc[-1 - weeks] - 1)


def indicators(df: pd.DataFrame = None) -> dict:
    """Härledda, token-fria makro-indikatorer för regim/stress-beräkningar."""
    df = df if df is not None else load()

    def last(name):
        return float(df[name].dropna().iloc[-1]) if name in df and df[name].dropna().size else None

    out = {"date": str(df.index[-1].date())}
    tnx, irx = last("UST10Y"), last("UST3M")
    # ^IRX/^TNX rapporteras i procent (t.ex. 4.30). Kurva 10y - 3m (< 0 = inverterad).
    out["yield_curve_10y_3m"] = round(tnx - irx, 2) if (tnx is not None and irx is not None) else None
    out["ust10y"] = tnx
    out["vix"] = last("VIX")
    # VIX-percentil (1 år) – var i sitt spann rädslan ligger.
    if "VIX" in df:
        v = df["VIX"].dropna().tail(52)
        if len(v) > 10:
            out["vix_pctile_1y"] = round(float((v <= v.iloc[-1]).mean()), 2)
    # Kreditstress: HYG (high yield) relativt IEF (statsobl.) senaste 13v.
    hy, ief = _chg(df.get("HYG", pd.Series(dtype=float)), 13), _chg(df.get("IEF", pd.Series(dtype=float)), 13)
    out["credit_hyg_vs_ief_13w"] = round(hy - ief, 3) if (hy is not None and ief is not None) else None
    # USD-trend: DXY mot 40v-snitt (stigande = flight to dollar).
    if "DXY" in df:
        d = df["DXY"].dropna()
        if len(d) > 40:
            out["usd_above_40w"] = bool(d.iloc[-1] > d.tail(40).mean())
            out["usd_13w"] = _chg(d, 13)
    out["gold_13w"] = _chg(df.get("GOLD", pd.Series(dtype=float)), 13)
    out["oil_13w"] = _chg(df.get("OIL", pd.Series(dtype=float)), 13)
    out["copper_gold_13w"] = None
    cg, gg = _chg(df.get("COPPER", pd.Series(dtype=float)), 13), out["gold_13w"]
    if cg is not None and gg is not None:
        out["copper_gold_13w"] = round(cg - gg, 3)   # koppar/guld = cyklisk aptit vs rädsla
    return out


def show():
    ind = indicators()
    print(f"\n  MAKRO-INDIKATORER ({ind['date']})  – token-fritt, dagsfärsk EOD\n")
    yc = ind.get("yield_curve_10y_3m")
    if yc is not None:
        flag = "INVERTERAD ⚠ (recessionsvarning)" if yc < 0 else "normal (positiv lutning)"
        print(f"  Räntekurva 10y–3m:   {yc:+.2f} %-enh   {flag}")
    if ind.get("vix") is not None:
        lvl = ind["vix"]
        reg = "lugnt" if lvl < 20 else ("förhöjt" if lvl < 30 else "STRESS")
        pc = ind.get("vix_pctile_1y")
        print(f"  VIX:                 {lvl:>5.1f}   {reg}" + (f"   (percentil 1å: {pc:.0%})" if pc else ""))
    cs = ind.get("credit_hyg_vs_ief_13w")
    if cs is not None:
        print(f"  Kreditstress (HYG–IEF 13v): {cs:+.1%}   " +
              ("high yield UNDER statsobl → risk-off" if cs < 0 else "high yield leder → risk-on"))
    if ind.get("usd_above_40w") is not None:
        print(f"  USD (DXY) över 40v-snitt: {'JA – flight to dollar' if ind['usd_above_40w'] else 'nej'}"
              + (f"   (13v {ind['usd_13w']:+.1%})" if ind.get('usd_13w') is not None else ""))
    for k, lbl in (("gold_13w", "Guld 13v"), ("oil_13w", "Olja 13v"),
                   ("copper_gold_13w", "Koppar–guld 13v (cyklisk aptit)")):
        if ind.get(k) is not None:
            print(f"  {lbl:<32} {ind[k]:+.1%}")
    out = Path("results/macro_snapshot.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(ind, ensure_ascii=False))
    print(f"\n  Snapshot sparad: {out}")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "show"
    if cmd == "fetch":
        fetch()
    elif cmd == "show":
        show()
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
