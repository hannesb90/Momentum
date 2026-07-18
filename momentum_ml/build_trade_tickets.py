"""
build_trade_tickets.py – konkret köpplan för ett belopp, redo att bli
Montrose-trade-tickets. Ren lokal beräkning (ingen MCP-anrop här) ovanpå
portfolio.py:s befintliga next_buy()-motor – samma logik som Nästa köp-vyn
i appen: bred kärna först, Sverige-satellit från sammanvägd rankning,
tema-satellit bara i risk-on. Ingen försäljning – köp och behåll.

    python build_trade_tickets.py 10000

Skriver results/next_buy_tickets.json:
  {"amount": 10000, "rows": [{"ticker","name","kr","bucket","why","order"}, ...],
   "skipped": [...], "note": "..."}

Steget EFTER detta (orderbookId-uppslag + create_trade_ticket) görs av Claude
i sessionen, inte av scriptet – MCP-verktygen är bara nåbara därifrån, och
varje trade-ticket-URL öppnas i Montrose-appen för din egen bekräftelse innan
något köps. Det här scriptet lägger aldrig någon order.
"""
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import config  # noqa: E402
import portfolio as pf  # noqa: E402


def build(amount=None):
    amount = float(amount) if amount else float(config.NEXT_BUY_DEFAULT_AMOUNT)
    rows = pf.load_holdings()
    if not rows:
        print("[build_trade_tickets] inga innehav i cache/portfolio_holdings.csv – "
              "synka Montrose-innehaven först (sync_montrose_holdings.py).")
        return None
    plan = pf.next_buy(rows, amount=amount)
    out = {"amount": plan["amount"], "rows": plan["rows"], "skipped": plan["skipped"],
           "risk_on": plan["risk_on"], "note": plan["note"]}
    p = pf._results_dir() / "next_buy_tickets.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n  KÖPPLAN – {plan['amount']:,.0f} kr\n".replace(",", " "))
    for r in plan["rows"]:
        print(f"   {r['order']}. {r['kr']:>8,.0f} kr  {r['ticker']:<10} {r['name']}".replace(",", " "))
        print(f"      {r['why']}")
    if plan["skipped"]:
        print("\n  Hoppade hinkar:")
        for s in plan["skipped"]:
            print(f"   · {s['bucket']}: {s['reason']}")
    print(f"\n  {plan['note']}\n")
    print(f"  → {p}")
    return out


if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else None)
