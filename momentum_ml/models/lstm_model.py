"""
models/lstm_model.py – LSTM sekvensmodell för trend/momentum.

Tar in sekvenser av features (config.LSTM_SEQUENCE_LEN veckor) och förutsäger
samma targets som LightGBM-modellen för enkel ensemble-integrering.
"""

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
        print(f"[LSTM] Använder: {self.device} "
              f"({torch.get_num_threads()} trådar)")

    # ── Träning ──────────────────────────────────────────────────────────────

    def fit(
        self,
        train_df: pd.DataFrame,
        val_df:   pd.DataFrame,
        epochs:   int = config.LSTM_EPOCHS,
        patience: int = config.LSTM_PATIENCE,
    ) -> "MomentumLSTM":

        train_ds = MomentumDataset(train_df, fit_scaler=True)
        self.scaler = train_ds.scaler
        val_ds   = MomentumDataset(val_df,   scaler=self.scaler)

        train_dl = DataLoader(train_ds, batch_size=config.LSTM_BATCH_SIZE,
                              shuffle=True,  drop_last=True)
        val_dl   = DataLoader(val_ds,   batch_size=config.LSTM_BATCH_SIZE,
                              shuffle=False, drop_last=False)

        self.net = MomentumLSTMNet().to(self.device)
        optimizer = torch.optim.AdamW(self.net.parameters(), lr=config.LSTM_LR,
                                      weight_decay=1e-4)
        scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
            optimizer, T_max=epochs, eta_min=1e-5)

        cls_loss_fn = nn.BCELoss()
        reg_loss_fn = nn.HuberLoss()

        best_val, no_improve = np.inf, 0

        for epoch in range(1, epochs + 1):
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

            if epoch % 10 == 0:
                print(f"  Epoch {epoch:3d}/{epochs} | "
                      f"train={avg_tr:.4f} | val={avg_va:.4f}")

            # Early stopping
            if avg_va < best_val - 1e-5:
                best_val = avg_va
                best_state = {k: v.clone() for k, v in self.net.state_dict().items()}
                no_improve = 0
            else:
                no_improve += 1
                if no_improve >= patience:
                    print(f"  Early stopping vid epoch {epoch}.")
                    break

        self.net.load_state_dict(best_state)
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
        }, path)
        print(f"[LSTM] Modell sparad: {path}")

    def load(self, path: str = "results/lstm_model.pt") -> "MomentumLSTM":
        ckpt = torch.load(path, map_location=self.device)
        self.net = MomentumLSTMNet().to(self.device)
        self.net.load_state_dict(ckpt["state_dict"])
        self.scaler = ckpt["scaler"]
        return self
