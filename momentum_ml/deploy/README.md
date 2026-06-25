# Deploy på Raspberry Pi

Mål: API + dashboard alltid på, pipelinen (datahämtning → träning → backtest)
körs lågprioriterat en gång per natt så att Pi:n inte blir överbelastad och
dashboarden förblir responsiv under körningen.

## 1. Förberedelser

```bash
sudo mkdir -p /opt/momentum
sudo chown $USER:$USER /opt/momentum
git clone <repo-url> /opt/momentum/src
cp -r /opt/momentum/src/momentum_ml /opt/momentum/src/frontend /opt/momentum/

cd /opt/momentum/momentum_ml
python3 -m venv /opt/momentum/venv
/opt/momentum/venv/bin/pip install -r requirements.txt

cd /opt/momentum/frontend
npm ci
npm run build   # bygger dist/ som nginx servar
```

## 2. API som alltid-på-tjänst

```bash
sudo cp /opt/momentum/momentum_ml/deploy/momentum-api.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now momentum-api.service
```

## 3. Nattlig träning (lågprioriterad)

`momentum-train.service` körs som `Type=oneshot` med:
- `Nice=15` + `IOSchedulingClass=idle` – stjäl inte CPU/disk från API:t.
- `CPUWeight=20` – cgroup-baserad mjuk prioritering (systemd ≥ 240).
- `MemoryMax=2G` – säkerhetsnät mot OOM på en Pi med begränsat RAM.
- `MOMENTUM_TRAINING_THREADS=3` – lämnar en kärna åt API/OS på en 4-kärnig Pi.
  Justera till antal kärnor − 1 för din modell (Pi 5 har också 4 kärnor).

```bash
sudo cp /opt/momentum/momentum_ml/deploy/momentum-train.service /etc/systemd/system/
sudo cp /opt/momentum/momentum_ml/deploy/momentum-train.timer   /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now momentum-train.timer

# Testköra direkt utan att vänta till 02:00:
sudo systemctl start momentum-train.service
journalctl -u momentum-train.service -f
```

## 4. Frontend + reverse proxy

```bash
sudo apt install nginx
sudo cp /opt/momentum/momentum_ml/deploy/nginx-momentum.conf /etc/nginx/sites-available/momentum
sudo ln -s /etc/nginx/sites-available/momentum /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

Lägg på HTTPS (t.ex. `certbot --nginx`) – krävs för att PWA:n ska gå att
installera och för att service workern ska aktiveras utanför `localhost`.

## 5. Auto-sync (git pull + redeploy automatiskt)

`momentum-sync.timer` kör var 15:e minut: hämtar nya commits, kopierar
ändrad `momentum_ml/`- eller `frontend/`-kod till deploy-katalogerna, bygger
om frontend och/eller startar om API:t vid behov. `requirements.txt`-ändringar
flaggas men installeras *inte* automatiskt (för att inte riskera diskutrymmet
vid en oövervakad `pip install`) – kör då steg 1:s pip-kommando manuellt.

Kräver en avgränsad sudo-rättighet för att kunna starta om API-tjänsten utan
lösenord (bara den exakta kommandot, inget annat):

```bash
sudo cp /opt/momentum/momentum_ml/deploy/momentum-sync.sudoers /etc/sudoers.d/momentum-sync
sudo chmod 440 /etc/sudoers.d/momentum-sync
sudo visudo -c   # validera syntaxen
```

Installera och starta timern:

```bash
sudo cp /opt/momentum/momentum_ml/deploy/momentum-sync.service /etc/systemd/system/
sudo cp /opt/momentum/momentum_ml/deploy/momentum-sync.timer   /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now momentum-sync.timer

# Testköra direkt:
systemctl start momentum-sync.service
journalctl -u momentum-sync.service -f
```

Ändringar i `momentum_ml/deploy/` (systemd-units etc) synkas medvetet inte
automatiskt – skriptet skriver bara ut en påminnelse om vad som ska köras
manuellt, eftersom sådana ändringar kan kräva `daemon-reload`/sudo.

## 6. Hälsokontroll på Pi:n

```bash
vcgencmd measure_temp        # håll under ~80°C, sätt kylfläns/fläkt annars
vcgencmd get_throttled       # 0x0 = ingen throttling hittills
free -h                      # kontrollera att MemoryMax=2G inte är för snålt
systemctl status momentum-api.service momentum-train.timer
```

Om träningen behöver mer tid är det ofarligt att låta den ta längre – den
körs ändå på natten utan deadline. Justera istället `MOMENTUM_TRAINING_THREADS`
nedåt eller minska `config.DEFAULT_TICKERS`/historikens längd om Pi:n
fortfarande är på gränsen (hög temp, swap-användning, throttling-flaggor).
