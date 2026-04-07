"""
modules/liquidityGrabScanner/pattern_overlay.py

Erkennt dezente Zusatzmuster für den Chart:
- Engulfings
- Fair Value Gaps (FVG)

Die Ausgabe ist bewusst einfach gehalten, damit der Plotter die Muster
leicht und dezent visualisieren kann.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Literal

import pandas as pd


PatternDirection = Literal["bullish", "bearish"]


@dataclass
class EngulfingPattern:
    time: pd.Timestamp
    index: int
    direction: PatternDirection


@dataclass
class FairValueGap:
    start_time: pd.Timestamp
    end_time: pd.Timestamp
    start_index: int
    end_index: int
    direction: PatternDirection
    top: float
    bottom: float


def _required_ohlc(df: pd.DataFrame) -> bool:
    required = {"open", "high", "low", "close"}
    return df is not None and not df.empty and required.issubset(df.columns)


def find_engulfings(df: pd.DataFrame) -> List[EngulfingPattern]:
    """
    Einfache Body-Engulfing-Definition:

    Bullish Engulfing:
    - Vorherige Kerze bearish
    - Aktuelle Kerze bullish
    - Aktueller Body umschließt den vorherigen Body

    Bearish Engulfing:
    - Vorherige Kerze bullish
    - Aktuelle Kerze bearish
    - Aktueller Body umschließt den vorherigen Body
    """
    if not _required_ohlc(df) or len(df) < 2:
        return []

    patterns: List[EngulfingPattern] = []

    for i in range(1, len(df)):
        prev = df.iloc[i - 1]
        curr = df.iloc[i]

        prev_open = float(prev["open"])
        prev_close = float(prev["close"])
        curr_open = float(curr["open"])
        curr_close = float(curr["close"])

        prev_body_low = min(prev_open, prev_close)
        prev_body_high = max(prev_open, prev_close)
        curr_body_low = min(curr_open, curr_close)
        curr_body_high = max(curr_open, curr_close)

        prev_bearish = prev_close < prev_open
        prev_bullish = prev_close > prev_open
        curr_bullish = curr_close > curr_open
        curr_bearish = curr_close < curr_open

        if (
            prev_bearish
            and curr_bullish
            and curr_body_low <= prev_body_low
            and curr_body_high >= prev_body_high
        ):
            patterns.append(
                EngulfingPattern(
                    time=df.index[i],
                    index=i,
                    direction="bullish",
                )
            )
            continue

        if (
            prev_bullish
            and curr_bearish
            and curr_body_low <= prev_body_low
            and curr_body_high >= prev_body_high
        ):
            patterns.append(
                EngulfingPattern(
                    time=df.index[i],
                    index=i,
                    direction="bearish",
                )
            )

    return patterns


def find_fair_value_gaps(
    df: pd.DataFrame,
    min_gap_percent: float = 0.0,
) -> List[FairValueGap]:
    """
    Standard-3-Candle-FVG:

    Bullish FVG:
        low der 3. Kerze > high der 1. Kerze

    Bearish FVG:
        high der 3. Kerze < low der 1. Kerze
    """
    if not _required_ohlc(df) or len(df) < 3:
        return []

    gaps: List[FairValueGap] = []

    for i in range(2, len(df)):
        c1 = df.iloc[i - 2]
        c3 = df.iloc[i]

        c1_high = float(c1["high"])
        c1_low = float(c1["low"])
        c3_high = float(c3["high"])
        c3_low = float(c3["low"])

        if c3_low > c1_high:
            gap_bottom = c1_high
            gap_top = c3_low
            ref_price = c1_high if c1_high != 0 else 1.0
            gap_percent = ((gap_top - gap_bottom) / ref_price) * 100.0

            if gap_percent >= min_gap_percent:
                gaps.append(
                    FairValueGap(
                        start_time=df.index[i - 2],
                        end_time=df.index[i],
                        start_index=i - 2,
                        end_index=i,
                        direction="bullish",
                        top=gap_top,
                        bottom=gap_bottom,
                    )
                )
            continue

        if c3_high < c1_low:
            gap_top = c1_low
            gap_bottom = c3_high
            ref_price = c1_low if c1_low != 0 else 1.0
            gap_percent = ((gap_top - gap_bottom) / ref_price) * 100.0

            if gap_percent >= min_gap_percent:
                gaps.append(
                    FairValueGap(
                        start_time=df.index[i - 2],
                        end_time=df.index[i],
                        start_index=i - 2,
                        end_index=i,
                        direction="bearish",
                        top=gap_top,
                        bottom=gap_bottom,
                    )
                )

    return gaps
