"""Nasdaq archive discovery — ra JSON, korrekt paginering. STDLIB ONLY.

Sammanfattare trunkerar. Detta skript laser ra JSON och paginerar tills
servern slutar leverera nya poster, sa ingen trunkering kan dolja manader.

Kor: python3 tools/nasdaq_segment/discovery.py
"""
from __future__ import annotations
import json, pathlib, re, sys, time, urllib.parse, urllib.request

UA = {"User-Agent": "Mozilla/5.0 (compatible; momentum-v2 research data collector)"}
API = "https://api.news.eu.nasdaq.com/news/query.action"
V2 = pathlib.Path("/home/hannesb/momentum_v2")
UT = V2 / "research_k/nasdaq_segment_foundation/archive_discovery.json"

RE_ISO = re.compile(r"Equity[_ ]Trading[_ ]by[_ ]Company[_ ]and[_ ]Instrument[_ ](\d{4})-(\d{2})(_[A-Za-z]+)?\.(xlsx?)$", re.I)
RE_YYMM = re.compile(r"Equity[_ ]Trading[_ ]by[_ ]Company[_ ]and[_ ]Instrument[_ ](\d{2})(\d{2})(_[A-Za-z]+)?\.(xlsx?)$", re.I)


def manad_ur_filnamn(fn):
    m = RE_ISO.search(fn)
    if m:
        return f"{m.group(1)}-{m.group(2)}", m.group(4).lower()
    m = RE_YYMM.search(fn)
    if m:
        return f"20{m.group(1)}-{m.group(2)}", m.group(4).lower()
    return None, None


def fraga(**kw):
    q = {"type": "handleResponse", "showAttachments": "true", "countResults": "true",
         "displayLanguage": "en", "language": "en"}
    q.update(kw)
    u = API + "?" + urllib.parse.urlencode(q)
    for i in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=60) as f:
                b = f.read().decode("utf-8", "ignore")
            s = b.strip()
            if s.startswith("handleResponse("):
                s = s[len("handleResponse("):].rstrip(");")
            d = json.loads(s)
            r = d.get("results", d)
            it = r.get("item") or []
            return [it] if isinstance(it, dict) else it
        except Exception as e:                       # noqa: BLE001
            if i == 3:
                print(f"    FEL {type(e).__name__}: {str(e)[:90]}")
                return []
            time.sleep(2 * (i + 1))
    return []


def skorda(items, ut):
    ny = 0
    for it in items:
        att = it.get("attachment") or []
        if isinstance(att, dict):
            att = [att]
        for a in att:
            fn = a.get("fileName") or ""
            man, ext = manad_ur_filnamn(fn)
            if not man:
                continue
            post = {"report_month": man, "filename": fn,
                    "attachment_url": a.get("attachmentUrl"),
                    "file_type": ext, "headline": it.get("headline"),
                    "release_time": it.get("releaseTime"),
                    "disclosure_id": it.get("disclosureId"),
                    "notice_url": f"https://view.news.eu.nasdaq.com/view?id={it.get('messageUrlId') or ''}&lang=en"
                                  if it.get("messageUrlId") else None,
                    "namnkonvention": "ISO" if RE_ISO.search(fn) else "YYMM",
                    "discovery_status": "FOUND_DIRECT_ATTACHMENT"}
            ut.setdefault(man, []).append(post)
            ny += 1
    return ny


def main():
    hittade = {}
    grupper = [("exchangeNotice", "NordicMainMarketNotices"),
               ("exchangeNotice", None), (None, None)]
    frastexter = ['"Equity Trading by Company and Instrument"',
                  "Equity Trading by Company and Instrument"]
    for gg, gn in grupper:
        for ft in frastexter:
            for start in range(0, 1200, 50):
                kw = {"freeText": ft, "limit": "50", "start": str(start), "dir": "DESC"}
                if gg: kw["globalGroup"] = gg
                if gn: kw["globalName"] = gn
                items = fraga(**kw)
                if not items:
                    break
                n = skorda(items, hittade)
                print(f"  gg={gg} gn={gn} quoted={ft.startswith(chr(34))} start={start:>4} "
                      f"items={len(items):>3} nya_bilagor={n:>3} unika_manader={len(hittade)}")
            time.sleep(0.3)
    # ar-for-ar som komplement
    for ar in range(2011, 2027):
        for start in (0, 50):
            items = fraga(freeText=f'"Equity Trading by Company and Instrument" {ar}',
                          globalGroup="exchangeNotice", limit="50", start=str(start), dir="DESC")
            if not items:
                break
            skorda(items, hittade)
        print(f"  ar {ar}: unika_manader {len(hittade)}")

    def mlist(f, t):
        y, mm = int(f[:4]), int(f[5:7]); ye, me = int(t[:4]), int(t[5:7]); u = []
        while (y, mm) <= (ye, me):
            u.append(f"{y:04d}-{mm:02d}"); mm += 1
            if mm == 13: y, mm = y + 1, 1
        return u

    alla = mlist("2011-01", "2026-07")
    kanon = {}
    for man, lst in hittade.items():
        # canonical = senast publicerade (korrigeringar vinner)
        kanon[man] = sorted(lst, key=lambda x: x.get("release_time") or "")[-1]
    saknade = [m for m in alla if m not in kanon]
    ut = {"schema": "NASDAQ_ARCHIVE_DISCOVERY_V3",
          "metod": "ra JSON fran api.news.eu.nasdaq.com/news/query.action, paginerat "
                   "over flera globalGroup/globalName/freeText-varianter samt ar-for-ar. "
                   "Ingen sammanfattare inblandad.",
          "forvantade_manader": len(alla), "upptackta_manader": len(kanon),
          "saknade": saknade,
          "duplikat": {m: [x["filename"] for x in lst] for m, lst in hittade.items() if len(lst) > 1},
          "discovery_status_per_manad": {m: (kanon[m]["discovery_status"] if m in kanon
                                             else "NOT_FOUND_AFTER_EXHAUSTIVE_DISCOVERY")
                                         for m in alla},
          "poster": [kanon[m] for m in sorted(kanon)]}
    UT.write_text(json.dumps(ut, ensure_ascii=False, indent=1))
    print(f"\nUPPTACKTA: {len(kanon)} av {len(alla)}")
    print(f"SAKNADE:   {len(saknade)}")
    if saknade:
        print(f"  {saknade[:24]}{' ...' if len(saknade) > 24 else ''}")
    print(f"DUPLIKAT:  {len(ut['duplikat'])} manader med flera filer")
    print(f"skrivet: {UT}")


if __name__ == "__main__":
    main()
