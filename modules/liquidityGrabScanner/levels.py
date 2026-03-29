"""
modules/liquidityGrabScanner/levels.py

Erzeugt relevante Liquidity-Levels aus Pivot Highs und Pivot Lows.

Optional werden nahe beieinander liegende Hochs oder Tiefs zu Equal-High-
bzw. Equal-Low-Pools zusammengefasst, damit nicht jedes einzelne Pivot
als separates Level behandelt wird.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Literal, Optional

import pandas as pd


LevelSide = Literal["buy_side", "sell_side"]


@dataclass
class LiquidityLevel:
    """
    Repräsentiert ein relevantes Liquiditätslevel.

    buy_side:
        Liquidität über Hochs (Stops der Short-Trader / Buy Stops)
    sell_side:
        Liquidität unter Tiefs (Stops der Long-Trader / Sell Stops)
    """
    side: LevelSide
    price: float
    created_at: pd.Timestamp
    pivot_index: int
    source_indexes: List[int] = field(default_factory=list)
    touches: int = 1
    swept_at: Optional[pd.Timestamp] = None
    is_equal_pool: bool = False

    def age_bars(self, current_index: int) -> int:
        return max(current_index - self.pivot_index, 0)


def _is_pivot_high(df: pd.DataFrame, idx: int, n: int) -> bool:
    """
    Ein Pivot High liegt vor, wenn das Hoch der aktuellen Kerze höher ist
    als die Hochs der n Kerzen links und rechts.
    """
    if idx - n < 0 or idx + n >= len(df):
        return False

    pivot = df["high"].iloc[idx]
    left = df["high"].iloc[idx - n: idx]
    right = df["high"].iloc[idx + 1: idx + n + 1]

    return pivot > left.max() and pivot > right.max()


def _is_pivot_low(df: pd.DataFrame, idx: int, n: int) -> bool:
    """
    Ein Pivot Low liegt vor, wenn das Tief der aktuellen Kerze tiefer ist
    als die Tiefs der n Kerzen links und rechts.
    """
    if idx - n < 0 or idx + n >= len(df):
        return False

    pivot = df["low"].iloc[idx]
    left = df["low"].iloc[idx - n: idx]
    right = df["low"].iloc[idx + 1: idx + n + 1]

    return pivot < left.min() and pivot < right.min()


def _percent_distance(a: float, b: float) -> float:
    """
    Prozentuale Distanz zweier Preise relativ zu b.
    """
    if b == 0:
        return 0.0
    return abs((a - b) / b) * 100.0


def _merge_into_existing_level(
    levels: List[LiquidityLevel],
    side: LevelSide,
    price: float,
    created_at: pd.Timestamp,
    pivot_index: int,
    equal_threshold_percent: float,
    recent_weight: float,
) -> bool:
    """
    Fügt ein Pivot in einen bestehenden Equal-High-/Equal-Low-Pool ein,
    falls der Preis nah genug an einem vorhandenen Level liegt.

    Verbesserung gegenüber dem simplen Mittelwert:
    - neuerer Pivot bekommt mehr Gewicht
    - Pool wird auf den letzten Pivot "frisch" gesetzt
    """
    for level in levels:
        if level.side != side:
            continue

        if _percent_distance(price, level.price) <= equal_threshold_percent:
            recent_weight = min(max(recent_weight, 0.0), 1.0)
            old_weight = 1.0 - recent_weight

            level.price = (level.price * old_weight) + (price * recent_weight)
            level.touches += 1
            level.source_indexes.append(pivot_index)
            level.is_equal_pool = True

            # WICHTIG:
            # Pool gilt ab dem letzten berührenden Pivot als "frisch"
            level.created_at = created_at
            level.pivot_index = pivot_index

            return True

    return False


def build_liquidity_levels(
    df: pd.DataFrame,
    pivot_bars: int,
    max_reference_age_bars: int,
    max_levels_per_side: int,
    use_equal_levels: bool,
    equal_level_threshold_percent: float,
    equal_level_recent_weight: float = 0.70,
) -> List[LiquidityLevel]:
    """
    Baut aus dem DataFrame eine Liste relevanter Liquidity-Levels.

    Es werden nur relativ frische Pivots berücksichtigt, damit der Scanner
    nicht auf sehr alte und oft irrelevante Hochs/Tiefs reagiert.
    """
    if df is None or df.empty:
        return []

    required = {"high", "low"}
    if not required.issubset(df.columns):
        return []

    levels: List[LiquidityLevel] = []
    last_index = len(df) - 1

    for idx in range(len(df)):
        age = last_index - idx
        if age > max_reference_age_bars:
            continue

        ts = df.index[idx]

        if _is_pivot_high(df, idx, pivot_bars):
            price = float(df["high"].iloc[idx])

            if use_equal_levels:
                merged = _merge_into_existing_level(
                    levels=levels,
                    side="buy_side",
                    price=price,
                    created_at=ts,
                    pivot_index=idx,
                    equal_threshold_percent=equal_level_threshold_percent,
                    recent_weight=equal_level_recent_weight,
                )
                if not merged:
                    levels.append(
                        LiquidityLevel(
                            side="buy_side",
                            price=price,
                            created_at=ts,
                            pivot_index=idx,
                            source_indexes=[idx],
                        )
                    )
            else:
                levels.append(
                    LiquidityLevel(
                        side="buy_side",
                        price=price,
                        created_at=ts,
                        pivot_index=idx,
                        source_indexes=[idx],
                    )
                )

        if _is_pivot_low(df, idx, pivot_bars):
            price = float(df["low"].iloc[idx])

            if use_equal_levels:
                merged = _merge_into_existing_level(
                    levels=levels,
                    side="sell_side",
                    price=price,
                    created_at=ts,
                    pivot_index=idx,
                    equal_threshold_percent=equal_level_threshold_percent,
                    recent_weight=equal_level_recent_weight,
                )
                if not merged:
                    levels.append(
                        LiquidityLevel(
                            side="sell_side",
                            price=price,
                            created_at=ts,
                            pivot_index=idx,
                            source_indexes=[idx],
                        )
                    )
            else:
                levels.append(
                    LiquidityLevel(
                        side="sell_side",
                        price=price,
                        created_at=ts,
                        pivot_index=idx,
                        source_indexes=[idx],
                    )
                )

    buy_levels = sorted(
        [lvl for lvl in levels if lvl.side == "buy_side"],
        key=lambda x: x.pivot_index,
        reverse=True,
    )[:max_levels_per_side]

    sell_levels = sorted(
        [lvl for lvl in levels if lvl.side == "sell_side"],
        key=lambda x: x.pivot_index,
        reverse=True,
    )[:max_levels_per_side]

    result = sorted(buy_levels + sell_levels, key=lambda x: x.pivot_index)
    return result
