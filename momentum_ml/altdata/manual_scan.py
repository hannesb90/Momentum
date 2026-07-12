"""
altdata/manual_scan.py – Manuell scenario-skanner: mata in EN aktie (VALFRI –
behöver inte finnas i vårt spårade universum) plus manuell data för fält som
saknas, och få tillbaka SAMMA värdering/rankning som resten av modellerna
använder. Ett engångs "vad om"-svar – sparas ALDRIG till de riktiga CSV-
filerna, påverkar inget annat i appen.

Om tickern redan finns i vårt spårade universum (fundamentals-CSV:er,
kvalitet-/kvant-shortlists) FÖRFYLLS de fälten automatiskt – ange bara det
som saknas, eller skriv över för att testa ett alternativt scenario. INGET
nätanrop görs (varken pris eller fundamenta) – rent lokalt, så en skanning
kan aldrig hänga sig eller kräva Yahoo-åtkomst (till skillnad från
value_screener.py score, som hämtar kurser).

VALUTA: alla belopp anges i Mkr i BOLAGETS EGEN rapportvaluta. Ange dessutom
fx_rate (SEK per enhet utländsk valuta, t.ex. 10.5 för USD/SEK) om bolaget
INTE rapporterar i SEK – annars antas redan-SEK (fx_rate=1.0, default). Detta
är ett EXPLICIT värde DU anger – vi gissar ALDRIG en växelkurs (se
mfn_fundamentals.py:s dokumenterade USD-begränsning: att TYST anta okänd
valuta = SEK gav där en ~8-10x felkälla rakt in i ROE/värdering; här är
risken densamma om man glömmer fx_rate, så fältet är obligatoriskt att
MEDVETET sätta för utländska bolag, aldrig en gissning från vår sida).

    python -m altdata.manual_scan scan TICKER [field=value ...]
    python -m altdata.manual_scan scan NVDA.US net_profit=29800 equity=42800 \
        liabilities=54700 revenue=60900 revenue_prior=44900 \
        shares_outstanding=2470000000 price=135 currency=USD fx_rate=10.5 \
        period=Helår quality=4.2 quant=85 prob_up=0.6

    python -m altdata.manual_scan fields    # lista alla fält + förklaring
"""
import sys
import csv
from pathlib import Path
from typing import Dict, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))
import config
from altdata import value_screener

_FLOAT_FIELDS = {
    "price", "fx_rate", "revenue", "revenue_prior", "net_profit", "equity",
    "liabilities", "depreciation_amortization", "shares_outstanding",
    "quality", "quant", "prob_up",
}
_BOOL_FIELDS = {"research"}
_MONEY_FIELDS = ["revenue", "revenue_prior", "net_profit", "equity",
                  "liabilities", "depreciation_amortization", "price"]

_FIELD_HELP = {
    "name": "Bolagsnamn (valfritt, annars visas tickern)",
    "price": "Aktiekurs, i bolagets EGNA valuta (kr/lokal valuta per aktie)",
    "currency": "Valutakod, bara för visning (t.ex. 'USD') – påverkar inget i beräkningen",
    "fx_rate": "SEK per enhet utländsk valuta (t.ex. 10.5 för USD/SEK). Default 1.0 (redan SEK).",
    "revenue": "Omsättning, Mkr i bolagets egen valuta",
    "revenue_prior": "Omsättning samma period föregående år, Mkr (för tillväxt-beräkning)",
    "net_profit": "Nettoresultat, Mkr",
    "equity": "Eget kapital, Mkr",
    "liabilities": "Summa skulder, Mkr",
    "depreciation_amortization": "Av- och nedskrivningar, Mkr (valfritt, default 0 – konservativt lågt)",
    "shares_outstanding": "Antal utestående aktier (RÅTT antal, INTE i miljoner)",
    "period": "Rapportperiod: Q1/Q2/Q3/Q4/H1/9M/Helår (styr årstakts-skalning av flödesmått)",
    "quality": "Kvalitetsbetyg manuellt (0-5) om bolaget inte redan finns i kvalitet-vyn",
    "quant": "Kvantbetyg manuellt (0-100) om bolaget inte redan finns i kvant-screenern",
    "prob_up": "Momentum-modellens P(upp) manuellt (0-1) om okänt",
    "research": "Har uppdragsanalys/analys-anteckning (true/false)",
}
_ALL_FIELDS = list(_FIELD_HELP.keys())


def _cast_field(key: str, v):
    if v is None or v == "":
        return None
    if key in _FLOAT_FIELDS:
        try:
            return float(str(v).replace(",", ".").replace(" ", ""))
        except (TypeError, ValueError):
            return None
    if key in _BOOL_FIELDS:
        return str(v).strip().lower() in ("1", "true", "ja", "yes", "y", "på")
    return str(v).strip()


def _prefill(ticker: str, segment: Optional[str] = None) -> dict:
    """Lokal (nätfri) förfyllning: läser samma CSV:er som resten av
    pipelinen om tickern redan är spårad hos oss – annars tomt dict (allt
    fylls då manuellt). Görs ALDRIG mot nätet (ingen Yahoo-kurs hämtas –
    pris är alltid ett manuellt fält, se modulens docstring)."""
    out: Dict[str, object] = {}
    # Fundamentals kan ligga i VILKET segments results_dir som helst (ett bolag
    # hör till exakt ett segment: large ELLER small) – sök i det begärda
    # segmentet först, sedan övriga (en small-cap förfylldes tidigare aldrig
    # eftersom bara default-segmentet lästes).
    seg_names = [segment] if segment in config.SEGMENTS else []
    seg_names += [s for s in config.SEGMENTS if s not in seg_names]
    entry = None
    for s in seg_names:
        entry = value_screener._load_fundamentals(s).get(ticker)
        if entry:
            break
    if entry:
        latest = entry["latest"]
        # PENGAFÄLT konverteras till Mkr via sina enhetskolumner (_to_msek) –
        # det RÅA värdet kan vara i tkr/kkr, och nedströms behandlar scan()
        # alla belopp som Mkr → utan konvertering blev ett tkr-bolag 1000x fel.
        for f in ("revenue", "net_profit", "equity",
                  "liabilities", "depreciation_amortization"):
            v = value_screener._to_msek(latest.get(f), latest.get(f + "_unit"))
            if v is not None:
                out[f] = round(v, 2)
        # revenue_prior delar revenue-fältets enhet (samma mening i rapporten).
        vp = value_screener._to_msek(latest.get("revenue_prior"), latest.get("revenue_unit"))
        if vp is not None:
            out["revenue_prior"] = round(vp, 2)
        sh = value_screener._num(latest.get("shares_outstanding"))
        if sh is not None:
            out["shares_outstanding"] = sh
        # PERIOD är en STRÄNG ("Q1"/"Helår") – den gick tidigare genom _num()
        # och blev därför ALLTID None → förfyllda skanningar tappade perioden →
        # årsfaktor 1.0 på kvartalsdata (≈4x fel ROE/multipel) + en falsk
        # "ange period"-varning. Ta den som sträng.
        per = latest.get("period")
        if per and str(per) != "nan":
            out["period"] = str(per)

    import portfolio as pf
    scores = pf._load_scores()
    e = scores.get(ticker)
    if e:
        if e.get("name") and not out.get("name"):
            out["name"] = e["name"]
        if e.get("quality") is not None:
            out["quality"] = e["quality"]
        if e.get("quant") is not None:
            out["quant"] = e["quant"]
        if e.get("prob_up") is not None:
            out["prob_up"] = e["prob_up"]
        if e.get("research"):
            out["research"] = True
    return out


def _rank_value_against_universe(vmetrics: dict, segment: Optional[str] = None) -> Optional[float]:
    """Percentilrankar scenario-aktiens value-nyckeltal MOT det befintliga
    value_shortlist.csv-universumet, med EXAKT samma vikt-formel som
    value_screener.score() (_WEIGHTS/_ranks) – scenariot "smygs in" i
    fördelningen så value_score blir jämförbart med riktiga bolags.
    Returnerar None om inget universum finns (score() ej körd än) – de
    absoluta barren (ROE/skuld, se scan()) fungerar ändå utan detta."""
    seg_name = segment or config.DEFAULT_SEGMENT
    seg_cfg = config.SEGMENTS.get(seg_name, config.SEGMENTS[config.DEFAULT_SEGMENT])
    vp = Path(config.anchor(seg_cfg["results_dir"])) / "value_shortlist.csv"
    if not vp.exists():
        return None

    roe_vals, debt_vals, growth_vals, value_vals = {}, {}, {}, {}
    with open(vp, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            t = (r.get("ticker") or "").strip()
            if not t:
                continue
            roe_vals[t] = value_screener._num(r.get("roe"))
            de = value_screener._num(r.get("debt_equity"))
            debt_vals[t] = -de if de is not None else None
            growth_vals[t] = value_screener._num(r.get("rev_growth_yoy"))
            value_vals[t] = value_screener._num(r.get("owner_earnings_yield"))

    sc = "__SCENARIO__"
    roe_vals[sc] = vmetrics["roe"]
    de = vmetrics["debt_equity"]
    debt_vals[sc] = -de if de is not None else None
    growth_vals[sc] = vmetrics["rev_growth_yoy"]
    value_vals[sc] = vmetrics["owner_earnings_yield"]

    roe_rank, debt_rank = value_screener._ranks(roe_vals), value_screener._ranks(debt_vals)
    growth_rank, value_rank = value_screener._ranks(growth_vals), value_screener._ranks(value_vals)
    w = value_screener._WEIGHTS
    comp = (w["quality"] * roe_rank[sc] + w["safety"] * debt_rank[sc]
            + w["growth"] * growth_rank[sc] + w["value"] * value_rank[sc])
    return round(comp * 100, 1)


def _warnings(merged: dict, vmetrics: dict) -> list:
    w = []
    fx = merged.get("fx_rate")
    if fx is not None and float(fx) != 1.0 and not merged.get("currency"):
        w.append("fx_rate angiven men ingen valutakod satt – dubbelkolla att kursen stämmer.")
    if not merged.get("period"):
        w.append("Ingen rapportperiod angiven → årstakts-faktor 1.0 antas. Om siffrorna egentligen "
                  "är från en delårsrapport blir ROE/multipel missvisande (för låg ROE, för dyr "
                  "multipel) – ange period för korrekt uppräkning till årstakt.")
    if vmetrics.get("roe") is not None and vmetrics["roe"] < 0:
        w.append("Negativ ROE – bolaget gick med förlust perioden.")
    eq = merged.get("equity")
    if eq is not None and float(eq) <= 0:
        w.append("Eget kapital ≤ 0 → ROE/Skuld-EK kan inte beräknas (matematiskt meningslöst vid negativt kapital).")
    if vmetrics.get("mcap_msek") is None:
        w.append("Inget börsvärde beräkningsbart (saknar pris eller aktieantal) → ingen värderings-multipel/zon.")
    return w


def _verdict(vmetrics: dict, equity_sek, qn, kn, prob_up, models_out: dict) -> dict:
    """Ett samlat, transparent betyg för resultatsidans 'hastighetsmätare':
    overall_score (0-100, snitt av de rank-modeller som faktiskt kunde
    poängsätta scenariot) + två listor – positives ('vad gynnar aktien') och
    negatives ('vad sänker betyget') – byggda ur SAMMA trösklar som resten av
    Buffett-screenern (config.VALUE_ROE_GOOD/VALUE_DEBT_EQUITY_SAFE/
    VALUE_MULT_CHEAP/FAIR), inte nya påhittade gränser. Varje delfaktor
    hamnar i EXAKT en av listorna (aldrig båda, aldrig tyst utelämnad om
    data finns) så resultatet är begripligt utan att dubbelräkna."""
    pos, neg = [], []

    roe = vmetrics.get("roe")
    if roe is not None:
        if roe >= config.VALUE_ROE_GOOD:
            pos.append(f"ROE {roe:.0%} klarar kvalitetsbarren (≥{config.VALUE_ROE_GOOD:.0%})")
        else:
            neg.append(f"ROE {roe:.0%} under kvalitetsbarren (≥{config.VALUE_ROE_GOOD:.0%})")
    elif equity_sek is not None and float(equity_sek) <= 0:
        neg.append("Negativt eget kapital gör ROE och skuldsättning obestämbara – finansiell varningssignal")
    else:
        neg.append("ROE går inte att beräkna (saknar nettoresultat och/eller eget kapital)")

    de = vmetrics.get("debt_equity")
    if de is not None:
        if de <= config.VALUE_DEBT_EQUITY_SAFE:
            pos.append(f"Skuldsättning {de:.2f} är konservativ (≤{config.VALUE_DEBT_EQUITY_SAFE})")
        else:
            neg.append(f"Skuldsättning {de:.2f} över trygghetsbarren (≤{config.VALUE_DEBT_EQUITY_SAFE})")

    if vmetrics.get("meets_roe_bar") and vmetrics.get("meets_debt_bar"):
        pos.append("Klarar Buffett-modellens hårda grind (ROE OCH skuldsättning samtidigt)")

    zone, mult = vmetrics.get("zone"), vmetrics.get("mult")
    if zone == "billig":
        pos.append(f"Värderas billigt: {mult}x owner earnings (≤{config.VALUE_MULT_CHEAP}x)")
    elif zone == "rimlig":
        pos.append(f"Värderas rimligt: {mult}x owner earnings (≤{config.VALUE_MULT_FAIR}x)")
    elif zone == "dyr":
        neg.append(f"Värderas dyrt: {mult}x owner earnings (>{config.VALUE_MULT_FAIR}x)")
    elif zone == "förlust":
        neg.append("Går med förlust (negativa owner earnings) – ingen värderings-multipel meningsfull")

    rg = vmetrics.get("rev_growth_yoy")
    if rg is not None:
        if rg > 0:
            pos.append(f"Intäkterna växer {rg:+.0%} mot samma period föregående år")
        else:
            neg.append(f"Intäkterna krymper {rg:+.0%} mot samma period föregående år")

    if qn is not None:
        if qn >= 0.6:
            pos.append(f"Kvalitetsbetyg i övre delen av universumet (percentil {qn:.0%})")
        elif qn < 0.4:
            neg.append(f"Kvalitetsbetyg i nedre delen av universumet (percentil {qn:.0%})")
    if kn is not None:
        if kn >= 0.6:
            pos.append(f"Kvantbetyg i övre delen av universumet (percentil {kn:.0%})")
        elif kn < 0.4:
            neg.append(f"Kvantbetyg i nedre delen av universumet (percentil {kn:.0%})")
    if prob_up is not None:
        if prob_up >= 0.55:
            pos.append(f"Modellens P(upp) pekar uppåt ({prob_up:.0%})")
        elif prob_up < 0.45:
            neg.append(f"Modellens P(upp) pekar nedåt ({prob_up:.0%})")

    scores = [mo["score"] for mo in models_out.values() if mo.get("score") is not None]
    overall = round(max(0.0, min(1.0, sum(scores) / len(scores))) * 100) if scores else None

    return {"overall_score": overall, "positives": pos, "negatives": neg}


def scan(ticker: str, overrides: Optional[dict] = None, segment: Optional[str] = None) -> dict:
    """Kärnan: slå ihop förfyllnad + manuella overrides, kör SAMMA
    value_screener._metrics()-beräkning som den riktiga pipelinen, och
    testa scenariot mot alla tre rank-modeller (balanced/buffett/momentum)
    via portfolio._composite_score() – samma formel som _unified_rank."""
    ticker = (ticker or "").strip().upper()
    if not ticker:
        raise ValueError("ticker saknas")

    pre = _prefill(ticker, segment)
    merged: Dict[str, object] = dict(pre)
    field_source = {k: "cachad (redan spårad hos oss)" for k in pre}
    for k, v in (overrides or {}).items():
        if k not in _ALL_FIELDS:
            continue
        cv = _cast_field(k, v)
        if cv is None:
            continue
        merged[k] = cv
        field_source[k] = "manuell"

    fx_rate = float(merged.get("fx_rate") or 1.0)
    currency = str(merged.get("currency") or "SEK")

    def money(field):
        v = merged.get(field)
        return None if v is None else float(v) * fx_rate

    latest = {
        "net_profit": money("net_profit"), "net_profit_unit": "Mkr",
        "equity": money("equity"), "equity_unit": "Mkr",
        "liabilities": money("liabilities"), "liabilities_unit": "Mkr",
        "depreciation_amortization": money("depreciation_amortization"), "depreciation_amortization_unit": "Mkr",
        "shares_outstanding": merged.get("shares_outstanding"),
        "revenue": money("revenue"), "revenue_unit": "Mkr",
        "revenue_prior": money("revenue_prior"),
        "period": merged.get("period"),
        "published": None,
    }
    entry = {"latest": latest, "n_reports": 1, "growth_consistency": None}
    price_sek = money("price")
    vmetrics = value_screener._metrics(entry, price_sek)
    vmetrics["meets_roe_bar"] = bool(vmetrics["roe"] is not None and vmetrics["roe"] >= config.VALUE_ROE_GOOD)
    vmetrics["meets_debt_bar"] = bool(vmetrics["debt_equity"] is not None
                                       and vmetrics["debt_equity"] <= config.VALUE_DEBT_EQUITY_SAFE)

    value_score = _rank_value_against_universe(vmetrics, segment)

    quality = merged.get("quality")
    quant = merged.get("quant")
    prob_up = merged.get("prob_up")
    research = bool(merged.get("research"))

    scenario_entry = {
        "name": merged.get("name") or ticker,
        # EBITDA/P-S-zonen ('zone') kräver hela quality_screener-pipelinen
        # (LLM-tratt + kvant) – går inte att återskapa ur manuell indata,
        # så balanced/momentum-modellernas "dyr"-uteslutning kan inte
        # utvärderas här (bara buffett-modellens egen value_zone kan).
        "quality": quality, "zone": None,
        "quant": quant,
        "value_score": value_score, "value_zone": vmetrics["zone"],
        "meets_roe_bar": vmetrics["meets_roe_bar"], "meets_debt_bar": vmetrics["meets_debt_bar"],
        "prob_up": prob_up, "research": research,
    }

    import portfolio as pf
    scores = pf._load_scores()
    q_all = [e.get("quality") for e in scores.values()] + [quality]
    k_all = [e.get("quant") for e in scores.values()] + [quant]
    v_all = [e.get("value_score") for e in scores.values()] + [value_score]
    q_sorted = sorted(x for x in q_all if x is not None)
    k_sorted = sorted(x for x in k_all if x is not None)
    v_sorted = sorted(x for x in v_all if x is not None)

    models_out = {}
    for m, w in pf._MODEL_WEIGHTS.items():
        is_buffett = (m == "buffett")
        excluded = None
        if is_buffett and vmetrics["zone"] == "dyr":
            excluded = "skulle uteslutas: owner-earnings-värdering 'dyr'"
        elif is_buffett and value_score is None:
            excluded = "skulle uteslutas: ingen value-universum-data att jämföra mot (kör value_screener score)"
        elif is_buffett and not (vmetrics["meets_roe_bar"] and vmetrics["meets_debt_bar"]):
            excluded = "skulle uteslutas: klarar inte ROE-/skuld-barren (Buffett-grinden)"
        res = pf._composite_score(scenario_entry, m, w, q_sorted, k_sorted, v_sorted)
        if res is None:
            models_out[m] = {"score": None, "why": None,
                              "excluded_reason": excluded or "inget fundament-betyg (kvalitet/kvant/value) alls angivet"}
            continue
        score, why, pctls = res
        models_out[m] = {
            "score": round(score, 3), "why": " · ".join(why),
            "excluded_reason": excluded,
            "quality_percentile": pctls["quality_pctl"],
            "quant_percentile": pctls["quant_pctl"],
            "value_percentile": pctls["value_pctl"],
        }

    # Percentilerna är delade mellan modellerna (samma q_sorted/k_sorted –
    # bara VIKTEN skiljer per modell), så en enda beräkning här räcker för
    # verdikten i stället för att gräva i models_out efter första träffen.
    qn = pf._pct_rank(q_sorted, quality)
    kn = pf._pct_rank(k_sorted, quant)
    verdict = _verdict(vmetrics, latest.get("equity"), qn, kn, prob_up, models_out)

    return {
        "ticker": ticker, "name": scenario_entry["name"],
        "currency": currency, "fx_rate": fx_rate,
        "fields": {k: {"value": merged.get(k), "source": field_source.get(k, "saknas")} for k in _ALL_FIELDS},
        "value_metrics": vmetrics,
        "value_score": value_score,
        "models": models_out,
        "overall_score": verdict["overall_score"],
        "positives": verdict["positives"],
        "negatives": verdict["negatives"],
        "warnings": _warnings(merged, vmetrics),
    }


def _print_report(r: dict) -> None:
    print(f"\n=== {r['ticker']} – {r['name']} ===")
    os = r.get("overall_score")
    print(f"HELHETSBETYG: {os}/100" if os is not None else "HELHETSBETYG: otillräcklig data")
    if r.get("positives"):
        print("  Gynnar aktien:")
        for p in r["positives"]:
            print(f"    + {p}")
    if r.get("negatives"):
        print("  Sänker betyget:")
        for n in r["negatives"]:
            print(f"    - {n}")
    if r.get("warnings"):
        print("VARNINGAR:")
        for w in r["warnings"]:
            print(f"  ! {w}")
    print("\nFÄLT (källa):")
    for k, v in r["fields"].items():
        if v["value"] is not None:
            print(f"  {k:<28} {v['value']}  [{v['source']}]")
    vm = r["value_metrics"]
    print("\nVÄRDE-NYCKELTAL:")
    print(f"  ROE                {vm['roe']:.1%}" if vm["roe"] is not None else "  ROE                okänd")
    print(f"  Skuld/EK           {vm['debt_equity']:.2f}" if vm["debt_equity"] is not None else "  Skuld/EK           okänd")
    print(f"  Owner earnings     {vm['owner_earnings_msek']:.1f} Mkr" if vm["owner_earnings_msek"] is not None else "  Owner earnings     okänd")
    print(f"  Börsvärde          {vm['mcap_msek']:.0f} Mkr" if vm["mcap_msek"] is not None else "  Börsvärde          okänt")
    print(f"  Multipel/zon       {vm['mult']}x [{vm['zone']}]" if vm["mult"] is not None else f"  Zon                [{vm['zone']}]")
    print(f"  Klarar ROE-bar     {vm['meets_roe_bar']}")
    print(f"  Klarar skuld-bar   {vm['meets_debt_bar']}")
    print(f"  value_score        {r['value_score']}" if r["value_score"] is not None else "  value_score        okänt (inget universum – kör value_screener score)")
    print("\nMODELLER:")
    for m, mo in r["models"].items():
        if mo["score"] is not None:
            extra = f"   [{mo['excluded_reason']}]" if mo.get("excluded_reason") else ""
            print(f"  {m:<10} {mo['score']:.3f}  {mo['why']}{extra}")
        else:
            print(f"  {m:<10} —  ({mo['excluded_reason']})")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    cmd = sys.argv[1]
    if cmd == "fields":
        for k, help_text in _FIELD_HELP.items():
            print(f"  {k:<28} {help_text}")
        return
    if cmd != "scan" or len(sys.argv) < 3:
        print(__doc__)
        return
    ticker = sys.argv[2]
    overrides = {}
    for arg in sys.argv[3:]:
        if "=" not in arg:
            continue
        k, v = arg.split("=", 1)
        overrides[k.strip()] = v.strip()
    result = scan(ticker, overrides)
    _print_report(result)


if __name__ == "__main__":
    main()
