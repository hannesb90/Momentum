import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from models.lgbm_model import walk_forward_splits  # noqa: E402


def _weekly_dates(n, start="2010-01-01"):
    return pd.date_range(start, periods=n, freq="W")


# ── Grundläggande kronologi (ingen overlap, rätt ordning) ──────────────────

def test_walk_forward_splits_chronological_order():
    """train < val < test inom varje split, strikt kronologiskt."""
    dates = _weekly_dates(300)
    splits = walk_forward_splits(dates, train_weeks=100, val_weeks=20, step_weeks=20, embargo_weeks=0)
    assert len(splits) > 0
    for train_d, val_d, test_d in splits:
        assert train_d.max() < val_d.min()
        assert val_d.max() < test_d.min()


def test_walk_forward_splits_no_date_overlap_between_segments():
    """Inga datum ska förekomma i mer än ett av train/val/test i SAMMA split."""
    dates = _weekly_dates(300)
    splits = walk_forward_splits(dates, train_weeks=100, val_weeks=20, step_weeks=20, embargo_weeks=0)
    for train_d, val_d, test_d in splits:
        assert set(train_d).isdisjoint(set(val_d))
        assert set(val_d).isdisjoint(set(test_d))
        assert set(train_d).isdisjoint(set(test_d))


# ── Embargo: gapet ska faktiskt finnas och ha rätt storlek ─────────────────

def test_walk_forward_embargo_creates_gap_between_train_and_val():
    """Med embargo_weeks=E ska det vara E veckors GAP mellan sista train-
    datumet och första val-datumet (inte bara "ingen overlap", utan ett
    riktigt purgat mellanrum) – annars läcker targets som bär på framtida
    avkastning (FORWARD_WEEKS) in över gränsen. Se docstring i
    walk_forward_splits."""
    dates = _weekly_dates(300)
    embargo = 4
    splits = walk_forward_splits(dates, train_weeks=100, val_weeks=20, step_weeks=20, embargo_weeks=embargo)
    train_d, val_d, _ = splits[0]
    gap_weeks = (val_d.min() - train_d.max()).days // 7
    assert gap_weeks == embargo + 1, (
        f"Förväntade ett embargo-gap på {embargo} veckor (+1 för det egna "
        f"steget), fick {gap_weeks - 1} veckors gap"
    )


def test_walk_forward_embargo_creates_gap_between_val_and_test():
    dates = _weekly_dates(300)
    embargo = 4
    splits = walk_forward_splits(dates, train_weeks=100, val_weeks=20, step_weeks=20, embargo_weeks=embargo)
    _, val_d, test_d = splits[0]
    gap_weeks = (test_d.min() - val_d.max()).days // 7
    assert gap_weeks == embargo + 1


def test_walk_forward_embargo_shrinks_train_and_val_length():
    """train/val ska vara embargo_weeks KORTARE än den nominella fönster-
    längden (de sista veckorna purgas, inte bara "hoppas över" i nästa
    segment)."""
    dates = _weekly_dates(300)
    embargo = 4
    train_weeks, val_weeks = 100, 20
    splits = walk_forward_splits(dates, train_weeks=train_weeks, val_weeks=val_weeks,
                                  step_weeks=20, embargo_weeks=embargo)
    train_d, val_d, _ = splits[0]
    assert len(train_d) == train_weeks - embargo
    assert len(val_d) == val_weeks - embargo


def test_walk_forward_embargo_zero_matches_no_embargo_behaviour():
    """embargo_weeks=0 ska inte lämna något gap alls (bakåtkompatibelt med
    innan purge-fixen infördes)."""
    dates = _weekly_dates(300)
    splits = walk_forward_splits(dates, train_weeks=100, val_weeks=20, step_weeks=20, embargo_weeks=0)
    train_d, val_d, test_d = splits[0]
    assert (val_d.min() - train_d.max()).days == 7   # exakt en vecka, ingen extra purge
    assert (test_d.min() - val_d.max()).days == 7


def test_walk_forward_embargo_larger_than_window_still_leaves_one_observation():
    """Ett orimligt stort embargo (>= fönsterlängden) ska INTE ge ett tomt
    train/val-segment (krasch nedströms i träningen) – golvet `start + 1`/
    `train_end + 1` i walk_forward_splits ska hålla minst en observation."""
    dates = _weekly_dates(300)
    splits = walk_forward_splits(dates, train_weeks=10, val_weeks=10, step_weeks=10, embargo_weeks=50)
    assert len(splits) > 0
    for train_d, val_d, test_d in splits:
        assert len(train_d) >= 1
        assert len(val_d) >= 1


# ── Rullande fönster (step_weeks) ───────────────────────────────────────────

def test_walk_forward_splits_roll_forward_by_step_weeks():
    dates = _weekly_dates(300)
    splits = walk_forward_splits(dates, train_weeks=100, val_weeks=20, step_weeks=20, embargo_weeks=0)
    assert len(splits) >= 2
    # Varje efterföljande splits testfönster ska ligga senare i tiden.
    for (_, _, test_a), (_, _, test_b) in zip(splits, splits[1:]):
        assert test_b.min() > test_a.min()


def test_walk_forward_splits_too_little_data_returns_empty():
    dates = _weekly_dates(50)
    splits = walk_forward_splits(dates, train_weeks=100, val_weeks=20, step_weeks=20, embargo_weeks=4)
    assert splits == []


def test_walk_forward_splits_handles_duplicate_dates():
    """dates kan innehålla dubbletter (en rad per ticker och datum) –
    splittern ska avidentifiera på unika datum, inte räkna rader."""
    base = _weekly_dates(300)
    dup_dates = base.repeat(3)   # simulerar 3 tickers per datum
    splits_dup = walk_forward_splits(pd.DatetimeIndex(dup_dates), train_weeks=100,
                                      val_weeks=20, step_weeks=20, embargo_weeks=4)
    splits_unique = walk_forward_splits(base, train_weeks=100, val_weeks=20,
                                         step_weeks=20, embargo_weeks=4)
    assert len(splits_dup) == len(splits_unique)
    for (t1, v1, te1), (t2, v2, te2) in zip(splits_dup, splits_unique):
        assert list(t1) == list(t2)
        assert list(v1) == list(v2)
        assert list(te1) == list(te2)
