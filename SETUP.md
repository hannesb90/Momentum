# Setup – köra egen instans (eget konto, egen data)

Repot innehåller ingen hårdkodad personlig data – allt kontobundet läses ur
miljövariabler/en lokal `~/.momentum.env`-fil, ALDRIG från git. Den här
guiden listar EXAKT vad du (en ny användare, inte den ursprungliga ägaren)
behöver fylla i själv för att få en fungerande egen instans.

## 1. Krävs för att appen ska starta överhuvudtaget

| Vad | Var | Krävs? |
|---|---|---|
| `MOMENTUM_HOME` | Miljövariabel, t.ex. `export MOMENTUM_HOME=/opt/momentum/momentum_ml` i `.bashrc`/systemd | **Ja** – `config.anchor()` använder den för att slå upp alla relativa sökvägar (data/, cache/, results/). Utan den antas nuvarande arbetskatalog, vilket funkar för lokal utveckling men inte för en tjänst som körs från en annan katalog. |

Utan API-nycklar/kontobunden data fungerar hela kärnan (momentum-modellen,
backtest, signaler, "Nästa köp") direkt – all kursdata hämtas gratis via
`yfinance`, inget konto krävs.

## 2. Din egen portfölj (inte en kodändring – matas in i appen)

`cache/portfolio_holdings.csv` (gitignorerad, personlig data) skapas första
gången du sparar dina innehav under fliken **Innehav** i appen. Fram tills
dess visar "Nästa köp" bara den breda kärnan (den behöver inga befintliga
innehav för att fungera).

## 3. Valfria API-nycklar (bara om du vill ha den funktionaliteten)

Lägg i `~/.momentum.env` (skapa filen, `chmod 600 ~/.momentum.env` – läses
av `os.environ.get(...)`-fallbacken i respektive modul, ALDRIG committad):

```bash
# Bara om du vill köra alt-data-sentimentanalysen (altdata/sentiment.py)
ANTHROPIC_API_KEY=sk-ant-...

# Bara om du vill köra BörsAPI-baserad fundamenta-/insynsforskning
# (altdata/borsapi.py, Piotroski F-score m.m.) - gratis engångskvot (100
# rapporter), skaffa egen nyckel på borsapi.se
BORSAPI_API_KEY=...

# Bara om du vill testa Börsdata.se-fundamenta (avvisad i det här projektet
# av ekonomiska skäl, se docs/UTVECKLINGSLOGG.md #12 - men koden finns kvar
# om DIN kalkyl ser annorlunda ut)
BORSDATA_API_KEY=...

# Bara om du vill köra EODHD som alternativ kursdatakälla
EODHD_API_TOKEN=...
```

Ingen av dessa krävs för kärnfunktionaliteten (momentum-modell, backtest,
"Nästa köp", Bolag-vyn) – bara för respektive alt-data-forskningsspår.

## 4. Köp-biljett-knappen ("Skapa ticket" i Nästa köp) – valfri, kräver eget mäklarkonto

Den här funktionen skapar en förifylld handelslänk via Montrose (headless
Claude + Montrose-MCP). Kräver att DU har ett eget Montrose-kopplat
mäklarkonto (t.ex. Avanza ISK) – annars fungerar resten av appen utan
problem, knappen visar bara ett tydligt felmeddelande.

1. Registrera Montrose-MCP:n lokalt med DITT konto:
   ```bash
   claude mcp add --transport http montrose https://mcp.montrose.io
   claude mcp login montrose
   ```
2. Ta reda på ditt eget konto-ID: `python momentum_ml/montrose_ticket.py fetch_holdings`
3. Sätt `MONTROSE_ACCOUNT_ID` – se `momentum_ml/deploy/README.md` avsnitt 1b
   för hur du gör det via en systemd drop-in i stället för en committad fil.

## 5. Om du driftsätter på egen server (inte bara kör lokalt)

`momentum_ml/deploy/` innehåller systemd-units och `nginx-momentum.conf` som
förutsätter sökvägen `/opt/momentum/momentum_ml` – byt ut den mot din egen
installationssökväg i respektive `.service`-fil om du inte speglar samma
layout. `nginx-momentum.conf` har `server_name _;` (generisk, inget
hårdkodat domännamn) – lägg till ditt eget om du kör bakom en riktig domän.
En eventuell reverse-proxy-tunnel (t.ex. Cloudflare Tunnel) är helt separat
från det här repot – dess token/config hör hemma i `/etc/systemd/system/`
på din server, aldrig i git (se `momentum_ml/deploy/README.md`).

## 6. Sammanfattning: vad MÅSTE du göra, minimalt?

För att bara köra modellen/backtesten lokalt: **ingenting** utöver
`pip install -r momentum_ml/requirements.txt` (se `momentum_ml/README.md`).
Allt annat i den här guiden är opt-in beroende på vilka funktioner du vill
ha aktiva.
