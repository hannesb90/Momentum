"""REVALIDATION_PRICE_GATE — enda sanktionerade vagen in till prisdata.

All framtida revalidation MASTE ga genom denna gate. Den verifierar prisversion och
restriktionsregister mot manifest innan en enda rad lamnas ut, och den kastar hart fel
nar ett test forsoker rora blockerad data. Tyst filtrering forekommer inte: varje
avvisning loggas med instrument, datumintervall, falt, restriktionstyp och evidence_id.

Blockeringsmodellen har tva niva'er:

  FALTNIVA        RAW_CLOSE_INVALID blockerar faltet 'close' for hela serien.
                  Ingen implicit fallback till 'adj' — det ar ett fel, inte en fallback.

  BOUNDARYNIVA    ADJUSTED_SERIES_UNVERIFIED, SERIES_SPLIT_BOUNDARY och persistenta
                  EXTERNALLY_UNVERIFIED_CORPORATE_ACTION sparrar OVERGANGEN, inte
                  segmenten. Ett fonster som helt ryms inom ett segment ar giltigt.
                  Ett fonster som spanner over en boundary ar det inte.

Anvandning:
    from revalidation_price_gate import PriceGate
    g = PriceGate()                      # verifierar hashar, HARD FAIL vid avvikelse
    s = g.series("VOLV-B", "adj")        # ok
    w = g.window("SSAB-A", "2020-01-02", "2020-06-30", "adj")   # HARD FAIL: boundary
    ok = g.eligible("SSAB-A", "2021-06-01", lookback_days=252)  # True
"""
from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
from pathlib import Path

V2 = Path("/home/hannesb/momentum_v2")
BASE = V2 / "validated/prices_adjustment_repair_v4"
PRICES = BASE / "prices_validated_adjustment_repair_v4.json"
REGISTRY = BASE / "PRICE_RESTRICTION_REGISTRY.json"
MANIFEST = BASE / "REVALIDATION_PRICE_GATE_MANIFEST.json"

BOUNDARY_TYPES = {"ADJUSTED_SERIES_UNVERIFIED", "SERIES_SPLIT_BOUNDARY",
                  "EXTERNALLY_UNVERIFIED_CORPORATE_ACTION"}


class PriceRestrictionError(RuntimeError):
    """Hart fel. Fangas aldrig internt — ett blockerat anrop ska stoppa testet."""


class PriceGateIntegrityError(RuntimeError):
    """Hash- eller versionsavvikelse. Ingen fallback till gammal prisfil."""


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _d(s: str) -> date:
    return date(int(s[:4]), int(s[5:7]), int(s[8:10]))


class PriceGate:
    def __init__(self, prices: Path = PRICES, registry: Path = REGISTRY,
                 manifest: Path = MANIFEST, log: list | None = None):
        self.log = log if log is not None else []
        if not manifest.exists():
            raise PriceGateIntegrityError(f"manifest saknas: {manifest}")
        man = json.loads(manifest.read_text())
        self.manifest = man
        for name, path, key in (("prisfil", prices, "price_sha256"),
                                ("restriktionsregister", registry, "registry_sha256")):
            if not path.exists():
                raise PriceGateIntegrityError(f"{name} saknas: {path}")
            got = _sha(path)
            if got != man[key]:
                raise PriceGateIntegrityError(
                    f"HARD FAIL — {name} matchar inte manifestet.\n"
                    f"  fil      : {path}\n  forvantad: {man[key]}\n  faktisk  : {got}\n"
                    f"  Ingen fallback till gammal prisfil ar tillaten.")
        reg = json.loads(registry.read_text())
        if reg["registry_version"] != man["registry_version"]:
            raise PriceGateIntegrityError(
                f"HARD FAIL — registerversion {reg['registry_version']} "
                f"matchar inte manifestets {man['registry_version']}")
        if reg["canonical_price_sha256"] != man["price_sha256"]:
            raise PriceGateIntegrityError(
                "HARD FAIL — registret pekar pa en annan prisversion an manifestet")
        self.identity_mapping_version = man["identity_mapping_version"]
        self.prices = json.loads(prices.read_text())
        self.registry = reg
        self._field_blocks: dict[str, list[dict]] = {}
        self._boundaries: dict[str, list[dict]] = {}
        for e in reg["entries"]:
            t = e["ticker"]
            if e["blocked_fields"]:
                self._field_blocks.setdefault(t, []).append(e)
            if e["blocked_operation"] == "BOUNDARY_CROSSING" and e.get("boundary_date"):
                self._boundaries.setdefault(t, []).append(e)

    # ---------- introspektion ----------
    def boundaries(self, kod: str) -> list[str]:
        return sorted(e["boundary_date"] for e in self._boundaries.get(kod, []))

    def blocked_fields(self, kod: str) -> set[str]:
        return {f for e in self._field_blocks.get(kod, []) for f in e["blocked_fields"]}

    def restrictions(self, kod: str) -> list[dict]:
        return [e for e in self.registry["entries"] if e["ticker"] == kod]

    # ---------- atkomst ----------
    def _check_field(self, kod: str, field: str) -> None:
        for e in self._field_blocks.get(kod, []):
            if field in e["blocked_fields"]:
                self.log.append({"denied": "FIELD", "instrument": kod, "field": field,
                                 "restriction_type": e["restriction_type"],
                                 "evidence_id": e["evidence_id"]})
                raise PriceRestrictionError(
                    f"HARD FAIL — blockerat prisfalt.\n"
                    f"  instrument     : {kod}\n  falt           : {field}\n"
                    f"  datumintervall : {e['valid_from']} .. {e['valid_to']}\n"
                    f"  restriction    : {e['restriction_type']}\n"
                    f"  evidence_id    : {e['evidence_id']}\n"
                    f"  skal           : {e['reason']}\n"
                    f"  Ingen implicit fallback till 'adj' sker.")

    def _crossed(self, kod: str, start: str, end: str) -> list[dict]:
        return [e for e in self._boundaries.get(kod, [])
                if start < e["boundary_date"] <= end]

    def series(self, kod: str, field: str = "adj") -> list[dict]:
        self._check_field(kod, field)
        rows = self.prices.get(kod)
        if rows is None:
            raise PriceRestrictionError(f"HARD FAIL — instrument saknas i lagret: {kod}")
        b = self.boundaries(kod)
        if b:
            self.log.append({"denied": "FULL_SERIES", "instrument": kod, "boundaries": b})
            raise PriceRestrictionError(
                f"HARD FAIL — hela serien far inte lasas i ett stycke.\n"
                f"  instrument : {kod}\n  boundaries : {b}\n"
                f"  Anvand window() per segment. Kumulativ avkastning far inte lankas "
                f"over en oavstamd boundary.")
        return rows

    def window(self, kod: str, start: str, end: str, field: str = "adj") -> list[dict]:
        self._check_field(kod, field)
        rows = self.prices.get(kod)
        if rows is None:
            raise PriceRestrictionError(f"HARD FAIL — instrument saknas i lagret: {kod}")
        crossed = self._crossed(kod, start, end)
        if crossed:
            e = crossed[0]
            self.log.append({"denied": "BOUNDARY", "instrument": kod, "window": [start, end],
                             "field": field, "boundary": e["boundary_date"],
                             "restriction_type": e["restriction_type"],
                             "evidence_id": e["evidence_id"]})
            raise PriceRestrictionError(
                f"HARD FAIL — fonstret korsar en oavstamd boundary.\n"
                f"  instrument     : {kod}\n  datumintervall : {start} .. {end}\n"
                f"  falt           : {field}\n  boundary       : {e['boundary_date']}\n"
                f"  restriction    : {e['restriction_type']}\n"
                f"  evidence_id    : {e['evidence_id']}\n"
                f"  skal           : {e['reason']}\n"
                f"  Segmenten var for sig ar giltiga — dela fonstret vid boundaryn.")
        return [r for r in rows if start <= r["d"] <= end]

    def eligible(self, kod: str, asof: str, lookback_days: int, field: str = "adj") -> bool:
        """Ryms hela lookbackfonstret inom ett giltigt segment?"""
        if field in self.blocked_fields(kod):
            return False
        rows = self.prices.get(kod)
        if not rows:
            return False
        start = (_d(asof) - timedelta(days=lookback_days)).isoformat()
        if self._crossed(kod, start, asof):
            return False
        # kraver aven att fonstret faktiskt innehaller data
        return any(start <= r["d"] <= asof for r in rows)

    def eligible_universe(self, asof: str, lookback_days: int, field: str = "adj") -> list[str]:
        return sorted(k for k in self.prices if self.eligible(k, asof, lookback_days, field))
