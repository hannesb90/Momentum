"""
models/lstm_model.py – LSTM sekvensmodell för trend/momentum.

Tar in sekvenser av features (config.LSTM_SEQUENCE_LEN veckor) och förutsäger
samma targets som LightGBM-modellen för enkel ensemble-integrering.
"""

import hashlib
import os
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader
from pathlib import Path
from typing import Tuple, Optional, Dict
import joblib

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
import config
from features.feature_engineering import FEATURE_COLS


# ─────────────────────────────────────────────────────────────────────────────
# Dataset
# ─────────────────────────────────────────────────────────────────────────────

class MomentumDataset(Dataset):
    """
    Skapar sekvens-samples: (seq_len, n_features) → target.
    """

    def __init__(
        self,
        df: pd.DataFrame,
        seq_len: int = config.LSTM_SEQUENCE_LEN,
        scaler=None,
        fit_scaler: bool = False,
    ):
        from sklearn.preprocessing import StandardScaler

        self.seq_len = seq_len
        X_raw = df[FEATURE_COLS].fillna(0).values.astype(np.float32)

        if fit_scaler:
            self.scaler = StandardScaler()
            X_raw = self.scaler.fit_transform(X_raw)
        elif scaler is not None:
            self.scaler = scaler
            X_raw = self.scaler.transform(X_raw)
        else:
            self.scaler = None

        self.X         = X_raw
        self.y_cls     = df["target_signal"].values.astype(np.float32)
        self.y_reg     = df["target_return"].values.astype(np.float32)
        self.dates     = df.index
        self.n_samples = len(df) - seq_len

    def __len__(self):
        return max(0, self.n_samples)

    def __getitem__(self, idx):
        seq   = self.X[idx : idx + self.seq_len]             # (seq_len, features)
        y_cls = self.y_cls[idx + self.seq_len]
        y_reg = self.y_reg[idx + self.seq_len]
        return torch.tensor(seq), torch.tensor(y_cls), torch.tensor(y_reg)

    def get_date(self, idx: int) -> pd.Timestamp:
        return self.dates[idx + self.seq_len]


# ─────────────────────────────────────────────────────────────────────────────
# Nätverksarkitektur
# ─────────────────────────────────────────────────────────────────────────────

class MomentumLSTMNet(nn.Module):
    """
    LSTM med dubbla huvuden: klassifikation + regression.
    """

    def __init__(
        self,
        input_size:  int = len(FEATURE_COLS),
        hidden_size: int = config.LSTM_HIDDEN_SIZE,
        num_layers:  int = config.LSTM_NUM_LAYERS,
        dropout:     float = config.LSTM_DROPOUT,
    ):
        super().__init__()
        self.lstm = nn.LSTM(
            input_size=input_size,
            hidden_size=hidden_size,
            num_layers=num_layers,
            dropout=dropout if num_layers > 1 else 0,
            batch_first=True,
        )
        self.norm = nn.LayerNorm(hidden_size)
        self.dropout = nn.Dropout(dropout)

        # Delat MLP-lager
        self.shared = nn.Sequential(
            nn.Linear(hidden_size, 64),
            nn.GELU(),
            nn.Dropout(dropout),
        )
        # Klassifikationshuvud
        self.cls_head = nn.Linear(64, 1)
        # Regressionshuvud
        self.reg_head = nn.Linear(64, 1)

    def forward(self, x: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        # x: (batch, seq_len, features)
        out, _ = self.lstm(x)
        out = self.norm(out[:, -1, :])   # sista tidssteg
        out = self.dropout(out)
        shared = self.shared(out)
        prob   = torch.sigmoid(self.cls_head(shared)).squeeze(-1)
        ret    = self.reg_head(shared).squeeze(-1)
        return prob, ret


# ─────────────────────────────────────────────────────────────────────────────
# Träningswrapper
# ─────────────────────────────────────────────────────────────────────────────

class MomentumLSTM:

    def __init__(self):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        if config.NUM_TRAINING_THREADS and self.device.type == "cpu":
            torch.set_num_threads(config.NUM_TRAINING_THREADS)
        self.net: Optional[MomentumLSTMNet] = None
        self.scaler = None
        # Isotonisk kalibrator (rå sigmoid-sannolikhet → kalibrerad), anpassad
        # på VALIDERINGSFÖNSTRET efter träning – samma princip som LGBM:s
        # kalibrering. Utan den blandade ensemblen kalibrerad (LGBM) med
        # okalibrerad (LSTM) sannolikhet – medelvärdet blev okalibrerat.
        self.calibrator = None
        print(f"[LSTM] Använder: {self.device} "
              f"({torch.get_num_threads()} trådar)")

    # ── Checkpoint/resume (2026-07-24) ──────────────────────────────────────
    # LSTM-träning saknade helt den checkpoint-mekanism LGBM fick 2026-07-22
    # (UTVECKLINGSLOGG #20) efter upprepade nattkrascher mitt i träningen.
    # Verkligt fall 2026-07-24: en LSTM-ablation kördes i 12+ timmar på en
    # ARM-CPU utan GPU (139k rader × 26v-sekvenser - genuint tungt, inte
    # fastfruset) och fick dödas manuellt för att frigöra minne åt annat
    # arbete - all träning gick förlorad, ingen återupptagning möjlig. Samma
    # hash-baserade princip som LGBM (kod+config+data → nyckel, ogiltigförklara
    # tyst vid ändring), atomär temp-fil+os.replace, sparas EFTER varje epok
    # (epok är den naturliga granulariteten - en enskild epok kan i sig ta
    # flera minuter på den här hårdvaran).
    def _checkpoint_path(self) -> Path:
        return Path(config.RESULTS_DIR) / "_lstm_checkpoint.pt"

    def _checkpoint_key(self, train_df: pd.DataFrame, val_df: pd.DataFrame) -> str:
        code = Path(__file__).read_text() + Path(config.__file__).read_text()
        code_hash = hashlib.sha1(code.encode()).hexdigest()[:16]
        data_hash = hashlib.sha1(
            pd.util.hash_pandas_object(train_df, index=True).values.tobytes()
            + pd.util.hash_pandas_object(val_df, index=True).values.tobytes()
        ).hexdigest()[:16]
        return f"{code_hash}_{data_hash}"

    def _save_checkpoint(self, key: str, epoch: int, optimizer, scheduler,
                          best_val: float, best_state: dict, no_improve: int) -> None:
        path = self._checkpoint_path()
        tmp = path.with_suffix(".tmp")
        try:
            torch.save({
                "key": key, "next_epoch": epoch + 1,
                "net_state": self.net.state_dict(),
                "optimizer_state": optimizer.state_dict(),
                "scheduler_state": scheduler.state_dict(),
                "scaler": self.scaler,
                "best_val": best_val, "best_state": best_state, "no_improve": no_improve,
            }, tmp)
            os.replace(tmp, path)
        except Exception as e:  # noqa: BLE001 - checkpointen är en optimering, aldrig kritisk
            print(f"  [WARN] Kunde inte skriva LSTM-checkpoint (icke-kritiskt): {e}", flush=True)

    def _load_checkpoint(self, key: str):
        path = self._checkpoint_path()
        if not path.exists():
            return None
        try:
            saved = torch.load(path, map_location=self.device, weights_only=False)
            if saved.get("key") != key:
                return None
            return saved
        except Exception:  # noqa: BLE001 - korrupt/ofullständig checkpoint, börja om
            return None

    # ── Träning ──────────────────────────────────────────────────────────────

    def fit(
        self,
        train_df: pd.DataFrame,
        val_df:   pd.DataFrame,
        epochs:   int = config.LSTM_EPOCHS,
        patience: int = config.LSTM_PATIENCE,
    ) -> "MomentumLSTM":

        # Determinism (fixad 2026-07-26, pipeline-fingeravtrycksgranskning
        # #10): till skillnad från LGBM (config.LGBM_PARAMS: seed/
        # bagging_seed/feature_fraction_seed/data_random_seed/
        # deterministic=True) satte LSTM-träningen tidigare ALDRIG ett
        # seed - varken för nätverkets viktinitiering eller för
        # DataLoaderns shuffle=True nedan. Två annars identiska körningar
        # (samma kod, config, data) kunde därför ge olika tränade vikter,
        # vilket gjorde ett determinism-/fingeravtryckstest (backtest/
        # pipeline_fingerprint.py) meningslöst för LSTM-benet - inte en
        # riktig pipeline-drift, bara okontrollerad slump.
        torch.manual_seed(config.RANDOM_SEED)
        np.random.seed(config.RANDOM_SEED)

        train_ds = MomentumDataset(train_df, fit_scaler=True)
        self.scaler = train_ds.scaler
        val_ds   = MomentumDataset(val_df,   scaler=self.scaler)

        train_dl = DataLoader(train_ds, batch_size=config.LSTM_BATCH_SIZE,
                              shuffle=True,  drop_last=True,
                              generator=torch.Generator().manual_seed(config.RANDOM_SEED))
        val_dl   = DataLoader(val_ds,   batch_size=config.LSTM_BATCH_SIZE,
                              shuffle=False, drop_last=False)

        self.net = MomentumLSTMNet().to(self.device)
        optimizer = torch.optim.AdamW(self.net.parameters(), lr=config.LSTM_LR,
                                      weight_decay=1e-4)
        scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
            optimizer, T_max=epochs, eta_min=1e-5)

        cls_loss_fn = nn.BCELoss()
        reg_loss_fn = nn.HuberLoss()

        best_val, no_improve, start_epoch = np.inf, 0, 1
        best_state = {k: v.clone() for k, v in self.net.state_dict().items()}

        key = self._checkpoint_key(train_df, val_df)
        checkpoint = self._load_checkpoint(key)
        if checkpoint is not None:
            self.net.load_state_dict(checkpoint["net_state"])
            optimizer.load_state_dict(checkpoint["optimizer_state"])
            scheduler.load_state_dict(checkpoint["scheduler_state"])
            self.scaler = checkpoint["scaler"]
            best_val = checkpoint["best_val"]
            best_state = checkpoint["best_state"]
            no_improve = checkpoint["no_improve"]
            start_epoch = checkpoint["next_epoch"]
            print(f"  [checkpoint] Återupptar LSTM-träning från epoch {start_epoch}/{epochs} "
                  f"(best_val={best_val:.4f}).", flush=True)

        for epoch in range(start_epoch, epochs + 1):
            # Träning
            self.net.train()
            tr_loss = 0.0
            for x, y_cls, y_reg in train_dl:
                x, y_cls, y_reg = x.to(self.device), y_cls.to(self.device), y_reg.to(self.device)
                optimizer.zero_grad()
                prob, ret = self.net(x)
                loss = cls_loss_fn(prob, y_cls) + 0.5 * reg_loss_fn(ret, y_reg)
                loss.backward()
                nn.utils.clip_grad_norm_(self.net.parameters(), 1.0)
                optimizer.step()
                tr_loss += loss.item()
            scheduler.step()

            # Validering
            self.net.eval()
            va_loss = 0.0
            with torch.no_grad():
                for x, y_cls, y_reg in val_dl:
                    x, y_cls, y_reg = x.to(self.device), y_cls.to(self.device), y_reg.to(self.device)
                    prob, ret = self.net(x)
                    va_loss += (cls_loss_fn(prob, y_cls) + 0.5 * reg_loss_fn(ret, y_reg)).item()

            avg_tr = tr_loss / max(len(train_dl), 1)
            avg_va = va_loss / max(len(val_dl), 1)

            # flush=True + varje epok (inte var 10:e): utan flush kan print
            # sitta obuffrad i timmar när stdout går till en fil, inte en
            # terminal (verkligt fall 2026-07-24 - ingen framstegsrad syntes
            # på flera timmar trots att träningen gick på för fullt).
            print(f"  Epoch {epoch:3d}/{epochs} | "
                  f"train={avg_tr:.4f} | val={avg_va:.4f}", flush=True)

            # Early stopping
            if avg_va < best_val - 1e-5:
                best_val = avg_va
                best_state = {k: v.clone() for k, v in self.net.state_dict().items()}
                no_improve = 0
            else:
                no_improve += 1

            self._save_checkpoint(key, epoch, optimizer, scheduler, best_val, best_state, no_improve)

            if no_improve >= patience:
                print(f"  Early stopping vid epoch {epoch}.", flush=True)
                break

        self.net.load_state_dict(best_state)
        # Klart - checkpointen behövs inte längre (samma princip som LGBM:s
        # walk-forward-checkpoint: en avslutad träning ska inte kunna råka
        # återupptas från en gammal, redan färdig körning).
        self._checkpoint_path().unlink(missing_ok=True)

        # Kalibrera på valideringsfönstret (ALDRIG träningsdata – då kalibrerar
        # man bort modellens egen overfitting i stället för att korrigera den).
        # Degenererat fönster (en klass/få rader) ger en grov men ofarlig
        # mappning – IsotonicRegression kraschar inte.
        from sklearn.isotonic import IsotonicRegression
        raw_va, y_va = [], []
        self.net.eval()
        with torch.no_grad():
            for x, y_cls, _ in val_dl:
                p, _r = self.net(x.to(self.device))
                raw_va.append(p.cpu().numpy())
                y_va.append(y_cls.numpy())
        if raw_va and sum(len(a) for a in raw_va) >= 10:
            self.calibrator = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
            self.calibrator.fit(np.concatenate(raw_va), np.concatenate(y_va))
            print(f"  [LSTM] Isotonisk kalibrering anpassad på {sum(len(a) for a in raw_va)} valideringsrader.")
        else:
            print("  [LSTM] För få valideringsrader för kalibrering – kör okalibrerat.")
        return self

    # ── Prediktion ────────────────────────────────────────────────────────────

    def predict(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Returnerar DataFrame med prob_up, pred_signal, pred_return.
        """
        ds = MomentumDataset(df, scaler=self.scaler)
        dl = DataLoader(ds, batch_size=256, shuffle=False)

        probs, rets = [], []
        self.net.eval()
        with torch.no_grad():
            for x, _, _ in dl:
                p, r = self.net(x.to(self.device))
                probs.append(p.cpu().numpy())
                rets.append(r.cpu().numpy())

        probs = np.concatenate(probs)
        rets  = np.concatenate(rets)
        # Kalibrera om kalibrator finns (äldre sparade .pt saknar den → rå,
        # samma beteende som före kalibreringen infördes).
        if self.calibrator is not None:
            probs = self.calibrator.transform(probs)

        # Datum för de predikterade raderna
        dates = [ds.get_date(i) for i in range(len(ds))]

        return pd.DataFrame({
            "prob_up":     probs,
            "pred_signal": (probs > 0.5).astype(int),
            "pred_return": rets,
        }, index=dates)

    # ── Spara/ladda ───────────────────────────────────────────────────────────

    def save(self, path: str = "results/lstm_model.pt"):
        Path(path).parent.mkdir(exist_ok=True, parents=True)
        torch.save({
            "state_dict": self.net.state_dict(),
            "scaler":     self.scaler,
            "calibrator": self.calibrator,
        }, path)
        print(f"[LSTM] Modell sparad: {path}")

    def load(self, path: str = "results/lstm_model.pt") -> "MomentumLSTM":
        # weights_only=False: checkpointen innehåller en sklearn StandardScaler,
        # inte bara tensorer. Filen är vår egen tränade modell, inte extern indata.
        ckpt = torch.load(path, map_location=self.device, weights_only=False)
        self.net = MomentumLSTMNet().to(self.device)
        self.net.load_state_dict(ckpt["state_dict"])
        self.scaler = ckpt["scaler"]
        # Äldre checkpoint (före kalibreringen) → None = okalibrerad prediktion.
        self.calibrator = ckpt.get("calibrator")
        return self
