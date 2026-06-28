# Momentum

ML-baserad momentum-/trendhandelsapp för svenska aktier (FastAPI-backend +
React/Vite-PWA), driftad på Raspberry Pi. Mål: *tillräckligt bra för att fungera
som referens för handel åt en bred publik.*

## Var börjar jag? (för människor och AI-agenter)

| Vill du... | Läs |
|---|---|
| Förstå *varför* koden ser ut som den gör – allt resonemang, alla tester och resultat, vad som är prövat & förkastat | **[`docs/UTVECKLINGSLOGG.md`](docs/UTVECKLINGSLOGG.md)** |
| Se den externa kvalitets-/forskningsgranskningen (rigor, brister, roadmap) | [`docs/MODELLANALYS.md`](docs/MODELLANALYS.md) |
| Köra/ändra modellen | [`momentum_ml/README.md`](momentum_ml/README.md) + `momentum_ml/config.py` (alla parametrar med inline-rationale) |
| Förstå alt-data-spåret (MFN-pressmeddelande-sentiment) | [`momentum_ml/altdata/README.md`](momentum_ml/altdata/README.md) |

> **Start här om du är en agent som tar över:** `docs/UTVECKLINGSLOGG.md` är den
> destillerade kontexten (ersätter chatthistoriken). Den sammanfattar bl.a. den
> viktigaste insikten – att pris-only-edgen inte slår OMXS30 i den moderna
> algo-eran – och varför nästa steg är alt-data, inte fler pris-features.

## Struktur

```
momentum_ml/   # backend: modeller, features, backtester, API, analysverktyg, altdata/
frontend/      # React/Vite PWA
docs/          # kunskaps- och beslutsdokument
```

## Disciplin

Behåll bara ändringar som bevisar sig på den **frusna holdouten / rent OOS**.
Allt som bara ser bra ut in-sample reverteras. Det är så projektet kommit hit
utan att lura sig självt.
