"""
run_experiments.py – Kör ALLA kvarvarande edge-spår sekventiellt och sammanfattar.

Ett enda bakgrundskommando kör hela svepet och skriver en jämförelsetabell mot
holdout-baslinjen. Körs på Pi:n (data + tränad modell finns bara där):

    cd /opt/momentum/src/momentum_ml
    nohup env PYTHONUNBUFFERED=1 /opt/momentum/venv/bin/python run_experiments.py \
        > /tmp/experiments/RUN.log 2>&1 &
    tail -f /tmp/experiments/RUN.log

Vad som körs:
  A. Config-A/B (rebalans-buffert, EWMA-vol, sidledes-exponering) – dessa rör bara
     BACKTESTEN, inte träningen, så de körs med --predict-only (laddar morgonens
     modell, ~5 min/segment i stället för ~30). Varje variant styrs via env-knoppar
     (se config.py) så inga filer redigeras mellan körningar.
  B. Fristående A/B-harnesses: meta-labeling, horisont-ensemble, PEAD (PEAD hämtar
     MFN-cachen först; hoppas över om nätet inte når mfn.se).

Slutresultat: /tmp/experiments/SUMMARY.txt + utskrift här.
"""
import os, re, sys, shutil, subprocess, time
from pathlib import Path

PY = sys.executable
LOGDIR = Path("/tmp/experiments")
LOGDIR.mkdir(parents=True, exist_ok=True)
SEGMENTS = ["large", "small"]


def setup_isolated_home():
    """
    KRITISKT: --predict-only skriver stats.json/signals.csv + pappershandlar i
    RESULTS_DIR. För att A/B-varianterna INTE ska klobba live-utdatan kör vi dem
    mot ett scratch-MOMENTUM_HOME: data-cachen symlänkas (återanvänds, read-only),
    results kopieras (modellerna följer med, varianterna skriver i kopian).
    Produktionen rörs aldrig.
    """
    real_home = os.environ.get("MOMENTUM_HOME", "").strip()
    if not real_home:
        import config as _c
        rd = str(_c.RESULTS_DIR)
        real_home = os.path.dirname(os.path.abspath(rd.rstrip("/"))) if os.path.isabs(rd) else os.getcwd()
    scratch = str(LOGDIR / "home")
    os.makedirs(scratch, exist_ok=True)
    src_cache, dst_cache = os.path.join(real_home, "cache"), os.path.join(scratch, "cache")
    if os.path.isdir(src_cache) and not os.path.exists(dst_cache):
        os.symlink(src_cache, dst_cache)
    src_res, dst_res = os.path.join(real_home, "results"), os.path.join(scratch, "results")
    if os.path.isdir(src_res) and not os.path.exists(dst_res):
        shutil.copytree(src_res, dst_res)
    print(f"  Scratch-home: {scratch}  (data ← {src_cache}, modeller kopierade)")
    return scratch, real_home

# Config-A/B-varianter (env-knoppar). baseline = kontroll (inga overrides).
VARIANTS = {
    "baseline": {},
    "buffer":   {"MOMENTUM_REBALANCE_BUFFER_PCT": "0.03"},
    "ewma":     {"MOMENTUM_VOL_TARGET_EWMA": "1"},
    "sideways": {"MOMENTUM_SIDEWAYS_EXP": "0.5"},
    "all_on":   {"MOMENTUM_REBALANCE_BUFFER_PCT": "0.03",
                 "MOMENTUM_VOL_TARGET_EWMA": "1",
                 "MOMENTUM_SIDEWAYS_EXP": "0.5"},
}


def _parse_holdout(text: str):
    """Plocka CAGR/Sharpe/MaxDD ur HOLDOUT-blocket + alfa/index-raden."""
    out = {}
    lines = text.splitlines()
    for i, ln in enumerate(lines):
        if "HOLDOUT" in ln and "aldrig sedd" in ln:
            block = "\n".join(lines[i:i + 6])
            m = re.search(r"CAGR\s+(-?[\d.]+)%", block)
            s = re.search(r"Sharpe\s+(-?[\d.]+)", block)
            d = re.search(r"Max Drawdown\s+(-?[\d.]+)%", block)
            out["cagr"] = float(m.group(1)) if m else None
            out["sharpe"] = float(s.group(1)) if s else None
            out["maxdd"] = float(d.group(1)) if d else None
    mi = re.search(r"strategi vs index:\s*([+-]?[\d.]+)%", text)
    out["vs_index"] = float(mi.group(1)) if mi else None
    return out


def run_cmd(name, args, env_extra=None, timeout=5400):
    """Kör ett subprocess-kommando, logga stdout, returnera (rc, text)."""
    env = dict(os.environ)
    if env_extra:
        env.update(env_extra)
    log = LOGDIR / f"{name}.log"
    print(f"\n[{time.strftime('%H:%M:%S')}] ► {name}: {' '.join(args)}"
          + (f"   env={env_extra}" if env_extra else ""))
    sys.stdout.flush()
    try:
        p = subprocess.run([PY, *args], env=env, capture_output=True, text=True, timeout=timeout)
        log.write_text(p.stdout + "\n---STDERR---\n" + p.stderr, encoding="utf-8")
        if p.returncode != 0:
            print(f"    [FEL] rc={p.returncode} (se {log})")
        return p.returncode, p.stdout
    except subprocess.TimeoutExpired:
        print(f"    [TIMEOUT] efter {timeout}s (se {log})")
        return -1, ""
    except Exception as e:
        print(f"    [UNDANTAG] {e}")
        return -1, ""


def main():
    results = {}   # variant -> segment -> holdout dict

    # ── A. Config-A/B (predict-only, snabbt, ISOLERAT från produktionen) ─────
    print("=" * 70)
    print("  A. CONFIG-A/B (rör backtesten, ej träningen → --predict-only)")
    print("=" * 70)
    scratch_home, _ = setup_isolated_home()
    for vname, env_extra in VARIANTS.items():
        results[vname] = {}
        for seg in SEGMENTS:
            env_v = {"MOMENTUM_HOME": scratch_home, **env_extra}
            rc, out = run_cmd(
                f"cfg_{vname}_{seg}",
                ["main.py", "--predict-only", "--segment", seg, "--skip-lstm"],
                env_extra=env_v, timeout=1800,
            )
            results[vname][seg] = _parse_holdout(out) if rc == 0 else {}

    # ── B. Fristående harnesses ──────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("  B. A/B-HARNESSES (meta-labeling, horisont-ensemble, PEAD)")
    print("=" * 70)
    run_cmd("metalabel", ["tune_metalabel.py"], timeout=5400)
    run_cmd("horizon_ensemble", ["tune_horizon_ensemble.py"], timeout=7200)
    # PEAD kräver MFN-cache – hämta först (kan misslyckas om nätet inte når mfn.se)
    run_cmd("mfn_fetch",
            ["-c", "from altdata import mfn_fetch; mfn_fetch.fetch_universe('large')"],
            timeout=3600)
    run_cmd("pead", ["tune_pead.py"], timeout=1800)

    # ── Sammanfattning ───────────────────────────────────────────────────────
    lines = []
    lines.append("=" * 70)
    lines.append("  SAMMANFATTNING – HOLDOUT (frusen, aldrig sedd)")
    lines.append("=" * 70)
    for seg in SEGMENTS:
        lines.append(f"\n  ── {seg.upper()} ──")
        lines.append(f"  {'variant':<12}{'CAGR':>8}{'Sharpe':>9}{'MaxDD':>9}{'vs index':>10}")
        lines.append("  " + "-" * 46)
        base = results.get("baseline", {}).get(seg, {})
        for vname in VARIANTS:
            h = results.get(vname, {}).get(seg, {})
            if not h:
                lines.append(f"  {vname:<12}{'(saknas)':>36}")
                continue
            cagr = f"{h.get('cagr'):>6.1f}%" if h.get('cagr') is not None else "   n/a"
            shrp = f"{h.get('sharpe'):>8.2f}" if h.get('sharpe') is not None else "     n/a"
            dd   = f"{h.get('maxdd'):>7.1f}%" if h.get('maxdd') is not None else "    n/a"
            vi   = f"{h.get('vs_index'):>8.1f}%" if h.get('vs_index') is not None else "     n/a"
            flag = ""
            if base and h.get("sharpe") is not None and base.get("sharpe") is not None:
                if h["sharpe"] > base["sharpe"] + 0.03:
                    flag = "  ← bättre"
                elif h["sharpe"] < base["sharpe"] - 0.03:
                    flag = "  ← sämre"
            lines.append(f"  {vname:<12}{cagr}{shrp}{dd}{vi}{flag}")
    lines.append("\n  Harness-resultat: se /tmp/experiments/{metalabel,horizon_ensemble,pead}.log")
    lines.append("  (sök efter 'HJÄLPER' / 'prediktiv kraft' i respektive logg)")
    summary = "\n".join(lines)
    print("\n" + summary)
    (LOGDIR / "SUMMARY.txt").write_text(summary, encoding="utf-8")
    print(f"\n[KLAR] Sammanfattning sparad: {LOGDIR / 'SUMMARY.txt'}")


if __name__ == "__main__":
    main()
