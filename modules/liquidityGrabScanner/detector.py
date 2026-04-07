"""
modules/liquidityGrabScanner/detector.py

Liquidity-Grab-Scanner mit 3 Stufen:

Stufe 1 – Early Grab
    Sweep + Reclaim + Wick + Trendkontext

Stufe 2 – Follow-through
    Stufe 1 + Folgebewegung in Signalrichtung innerhalb eines
    timeframe-abhängigen Lookahead-Fensters

Stufe 3 – MSS / CHOCH
    Stufe 2 + Bruch der relevanten Gegenseiten-Struktur
    (bullish: letztes Pivot-High vor dem Grab,
     bearish: letztes Pivot-Low vor dem Grab)

Wichtig:
- Der Scanner erkennt den Grab auf der Signal-Bar.
- Follow-through und MSS/CHOCH werden über Folge-Bars bewertet.
- Pro Symbol kann später der höchste Stage-Status angezeigt werden.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Literal, Optional, Tuple

import pandas as pd

from .levels import (
    LiquidityLevel,
    build_liquidity_levels,
    _is_pivot_high,
    _is_pivot_low,
)


SignalDirection = Literal["bullish", "bearish"]
SignalType = Literal["grab", "run", "failed_grab"]
TrendState = Literal["uptrend", "downtrend", "range"]


@dataclass
class LiquiditySignal:
    """
    Repräsentiert ein erkanntes Liquidity-Event mit Stage-Ausbau.
    """
    signal_time: pd.Timestamp
    signal_index: int
    direction: SignalDirection
    signal_type: SignalType

    level_side: str
    level_price: float
    reference_time: pd.Timestamp
    reference_index: int

    sweep_percent: float
    reclaimed: bool
    confirmed: bool  # bleibt für Kompatibilität bestehen; entspricht hier Stufe >= 2

    close_position: float
    wick_ratio: float
    score: float
    reason: str

    level_touches: int
    equal_pool: bool
    trend: TrendState
    with_trend: bool

    stage: int
    stage_label: str

    follow_through: bool
    follow_through_time: Optional[pd.Timestamp]
    follow_through_index: Optional[int]

    mss_confirmed: bool
    mss_time: Optional[pd.Timestamp]
    mss_index: Optional[int]
    mss_level: Optional[float]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class LiquidityGrabDetector:
    """
    Erzeugt Liquidity-Levels und scannt Bars auf Sweep-/Grab-/Run-Verhalten
    inkl. Stage-Logik für Early Grab / Follow-through / MSS-Confirm.
    """

    STAGE_LABELS = {
        1: "Stufe 1 – Early Grab",
        2: "Stufe 2 – Follow-through",
        3: "Stufe 3 – MSS / CHOCH",
    }

    def __init__(self, cfg: Dict[str, Any], timeframe: str | None = None):
        lg = cfg.get("liquidity_grab", {})

        self.timeframe = str(timeframe or cfg.get(
            "settings", {}).get("timeframe", "H1")).upper().strip()

        self.pivot_bars = int(lg.get("pivot_bars", 3))
        self.lookback_bars = int(lg.get("lookback_bars", 260))
        self.scan_recent_bars = int(lg.get("scan_recent_bars", 8))
        self.max_reference_age_bars = int(
            lg.get("max_reference_age_bars", 120))
        self.max_levels_per_side = int(lg.get("max_levels_per_side", 12))

        self.use_equal_levels = bool(lg.get("use_equal_levels", True))
        self.equal_level_threshold_percent = float(
            lg.get("equal_level_threshold_percent", 0.08)
        )
        self.equal_level_recent_weight = float(
            lg.get("equal_level_recent_weight", 0.70)
        )

        self.min_sweep_percent = float(lg.get("min_sweep_percent", 0.06))
        self.max_sweep_percent = float(lg.get("max_sweep_percent", 1.20))

        self.reclaim_rule = str(
            lg.get("reclaim_rule", "close_back_inside")
        ).strip()
        self.close_position_threshold = float(
            lg.get("close_position_threshold", 0.45)
        )

        self.confirmation_mode = str(
            lg.get("confirmation_mode", "reclaim_only")
        ).strip()
        self.confirmation_lookahead_bars = int(
            lg.get("confirmation_lookahead_bars", 3)
        )

        self.require_opposite_candle_color = bool(
            lg.get("require_opposite_candle_color", False)
        )
        self.one_sweep_per_level = bool(lg.get("one_sweep_per_level", True))
        self.allow_multiple_signals_per_symbol = bool(
            lg.get("allow_multiple_signals_per_symbol", True)
        )

        self.trend_filter = str(
            lg.get("trend_filter", "structure_bias")).strip()
        self.trend_sma_period = int(lg.get("trend_sma_period", 200))

        self.score_threshold = float(lg.get("score_threshold", 55))
        self.show_runs = bool(lg.get("show_runs", True))
        self.show_failed_grabs = bool(lg.get("show_failed_grabs", False))

        # Wick / Rejection
        self.use_wick_filter = bool(lg.get("use_wick_filter", False))
        self.min_wick_ratio = float(lg.get("min_wick_ratio", 0.40))
        self.wick_score_weight = float(lg.get("wick_score_weight", 10.0))
        self.strong_close_score_bonus = float(
            lg.get("strong_close_score_bonus", 10.0)
        )
        self.strong_close_threshold = float(
            lg.get("strong_close_threshold", 0.70)
        )

        # Trend/Bias-Logik
        self.trend_pivot_lookback = int(lg.get("trend_pivot_lookback", 6))
        self.range_score_penalty = float(lg.get("range_score_penalty", 8.0))
        self.counter_trend_score_penalty = float(
            lg.get("counter_trend_score_penalty", 20.0)
        )
        self.skip_counter_trend_signals = bool(
            lg.get("skip_counter_trend_signals", False)
        )
        self.skip_range_signals = bool(
            lg.get("skip_range_signals", False)
        )

        # Stage-Logik
        self.stage_mode = str(lg.get("stage_mode", "highest_only")).strip()

        self.follow_through_lookahead_bars = int(
            lg.get("follow_through_lookahead_bars",
                   self._default_follow_through_lookahead())
        )
        self.mss_lookahead_bars = int(
            lg.get("mss_lookahead_bars", self._default_mss_lookahead())
        )

        # harte, robuste Definitionen
        self.follow_through_use_close_break = bool(
            lg.get("follow_through_use_close_break", True)
        )
        self.mss_use_close_break = bool(
            lg.get("mss_use_close_break", True)
        )

        # optional: leichte Mindestbewegung zusätzlich zur Break-Regel
        self.follow_through_min_move_percent = float(
            lg.get("follow_through_min_move_percent", 0.0)
        )

        # Stage-Score-Boni
        self.stage2_score_bonus = float(lg.get("stage2_score_bonus", 12.0))
        self.stage3_score_bonus = float(lg.get("stage3_score_bonus", 18.0))

    def _default_follow_through_lookahead(self) -> int:
        if self.timeframe == "D1":
            return 3
        if self.timeframe == "H4":
            return 4
        return 6  # H1 Standard

    def _default_mss_lookahead(self) -> int:
        if self.timeframe == "D1":
            return 6
        if self.timeframe == "H4":
            return 8
        return 12  # H1 Standard

    @staticmethod
    def _close_position_in_range(row: pd.Series) -> float:
        """
        Ermittelt, wo der Schlusskurs innerhalb der Candle liegt:
        0.0 = am Tief, 1.0 = am Hoch.
        """
        high = float(row["high"])
        low = float(row["low"])
        close = float(row["close"])

        if high <= low:
            return 0.5

        return (close - low) / (high - low)

    @staticmethod
    def _wick_ratio(direction: SignalDirection, row: pd.Series) -> float:
        """
        Verhältnis der relevanten Sweep-Lunte zur gesamten Candle-Range.

        bullish:
            untere Lunte / gesamte Range
        bearish:
            obere Lunte / gesamte Range
        """
        high = float(row["high"])
        low = float(row["low"])
        open_ = float(row["open"])
        close = float(row["close"])

        total_range = high - low
        if total_range <= 0:
            return 0.0

        if direction == "bullish":
            wick = min(open_, close) - low
        else:
            wick = high - max(open_, close)

        wick = max(wick, 0.0)
        return wick / total_range

    @staticmethod
    def _sweep_percent(
        direction: SignalDirection,
        row: pd.Series,
        level_price: float,
    ) -> float:
        """
        Berechnet, wie weit die Candle über/unter das Level hinaus sweeped.
        """
        if level_price == 0:
            return 0.0

        if direction == "bearish":
            return max(((float(row["high"]) - level_price) / level_price) * 100.0, 0.0)

        return max(((level_price - float(row["low"])) / level_price) * 100.0, 0.0)

    def _passes_reclaim_rule(
        self,
        direction: SignalDirection,
        row: pd.Series,
        level_price: float,
    ) -> bool:
        """
        Prüft, ob die Kerze das Level nach dem Sweep wieder sauber reclaimt.
        """
        open_ = float(row["open"])
        close = float(row["close"])

        if self.reclaim_rule == "body_back_inside":
            if direction == "bearish":
                return max(open_, close) < level_price
            return min(open_, close) > level_price

        if direction == "bearish":
            return close < level_price
        return close > level_price

    def _passes_opposite_candle_rule(
        self,
        direction: SignalDirection,
        row: pd.Series,
    ) -> bool:
        """
        Optionaler Farbfilter:
        bullish Grab bevorzugt bullishe Kerze,
        bearish Grab bevorzugt bearishe Kerze.
        """
        if not self.require_opposite_candle_color:
            return True

        open_ = float(row["open"])
        close = float(row["close"])

        if direction == "bullish":
            return close > open_
        return close < open_

    def _get_recent_pivots(
        self,
        df: pd.DataFrame,
        current_idx: int,
    ) -> Tuple[List[Tuple[int, float]], List[Tuple[int, float]]]:
        """
        Holt rohe Pivot-Highs und Pivot-Lows bis direkt vor die aktuelle Bar.
        """
        highs: List[Tuple[int, float]] = []
        lows: List[Tuple[int, float]] = []

        start = max(0, current_idx - self.max_reference_age_bars)

        for i in range(start, current_idx):
            if _is_pivot_high(df, i, self.pivot_bars):
                highs.append((i, float(df["high"].iloc[i])))

            if _is_pivot_low(df, i, self.pivot_bars):
                lows.append((i, float(df["low"].iloc[i])))

        return highs, lows

    def _detect_structure_trend(
        self,
        df: pd.DataFrame,
        current_idx: int,
    ) -> TrendState:
        """
        Bestimmt einen einfachen Struktur-Bias.
        """
        highs, lows = self._get_recent_pivots(df, current_idx)

        highs = highs[-self.trend_pivot_lookback:]
        lows = lows[-self.trend_pivot_lookback:]

        if len(highs) < 2 or len(lows) < 2:
            return "range"

        prev_high = highs[-2][1]
        last_high = highs[-1][1]

        prev_low = lows[-2][1]
        last_low = lows[-1][1]

        if last_high > prev_high and last_low > prev_low:
            return "uptrend"

        if last_high < prev_high and last_low < prev_low:
            return "downtrend"

        return "range"

    @staticmethod
    def _is_with_trend(
        direction: SignalDirection,
        trend: TrendState,
    ) -> bool:
        if trend == "uptrend" and direction == "bullish":
            return True
        if trend == "downtrend" and direction == "bearish":
            return True
        return False

    def _passes_trend_filter(
        self,
        direction: SignalDirection,
        trend: TrendState,
        row: pd.Series,
    ) -> bool:
        if self.trend_filter == "none":
            return True

        if self.trend_filter == "sma200":
            sma_col = f"SMA{self.trend_sma_period}"
            if sma_col not in row.index or pd.isna(row[sma_col]):
                return False

            close = float(row["close"])
            sma = float(row[sma_col])

            if direction == "bullish":
                return close >= sma
            return close <= sma

        if self.trend_filter == "structure_bias":
            if self.skip_range_signals and trend == "range":
                return False

            if self.skip_counter_trend_signals and not self._is_with_trend(direction, trend):
                return False

            return True

        return True

    def _level_was_previously_violated(
        self,
        df: pd.DataFrame,
        level: LiquidityLevel,
        current_idx: int,
    ) -> bool:
        """
        Prüft, ob das Level seit seinem Pivot bis direkt vor die aktuelle Signal-Bar
        schon einmal sauber verletzt wurde.
        """
        start = level.pivot_index + 1
        end = current_idx

        if start >= end:
            return False

        if level.side == "buy_side":
            return bool((df["high"].iloc[start:end] > level.price).any())

        if level.side == "sell_side":
            return bool((df["low"].iloc[start:end] < level.price).any())

        return False

    def _confirmation_passed(
        self,
        df: pd.DataFrame,
        idx: int,
        direction: SignalDirection,
        level_price: float,
        reclaimed: bool,
    ) -> bool:
        """
        Bestehende Bestätigungslogik bleibt für Kompatibilität erhalten.
        """
        row = df.iloc[idx]
        close_pos = self._close_position_in_range(row)

        if self.confirmation_mode == "none":
            return True

        if self.confirmation_mode == "reclaim_only":
            return reclaimed

        if self.confirmation_mode == "strong_reclaim":
            if not reclaimed:
                return False
            if direction == "bullish":
                return close_pos >= self.close_position_threshold
            return close_pos <= (1.0 - self.close_position_threshold)

        if self.confirmation_mode == "structure_break":
            if not reclaimed:
                return False

            signal_high = float(row["high"])
            signal_low = float(row["low"])

            start = idx + 1
            end = min(idx + 1 + self.confirmation_lookahead_bars, len(df))

            for future_idx in range(start, end):
                future_close = float(df["close"].iloc[future_idx])

                if direction == "bullish" and future_close > signal_high:
                    return True
                if direction == "bearish" and future_close < signal_low:
                    return True

            return False

        return reclaimed

    def _find_last_opposite_structure_level(
        self,
        df: pd.DataFrame,
        signal_idx: int,
        direction: SignalDirection,
    ) -> Optional[Tuple[int, float]]:
        """
        Für bullish:
            letztes Pivot-High vor dem Grab
        Für bearish:
            letztes Pivot-Low vor dem Grab
        """
        highs, lows = self._get_recent_pivots(df, signal_idx)

        if direction == "bullish":
            if not highs:
                return None
            return highs[-1]

        if not lows:
            return None
        return lows[-1]

    def _follow_through_passed(
        self,
        df: pd.DataFrame,
        idx: int,
        direction: SignalDirection,
    ) -> Tuple[bool, Optional[int], Optional[pd.Timestamp]]:
        """
        Stufe 2:
        Follow-through in Signalrichtung nach dem Grab.

        Robuste Definition:
        bullish:
            Schlusskurs über Hoch der Signal-Kerze
        bearish:
            Schlusskurs unter Tief der Signal-Kerze

        Optional kann zusätzlich ein Mindestweg in % verlangt werden.
        """
        if idx >= len(df) - 1:
            return False, None, None

        row = df.iloc[idx]
        signal_high = float(row["high"])
        signal_low = float(row["low"])
        signal_close = float(row["close"])

        start = idx + 1
        end = min(idx + 1 + self.follow_through_lookahead_bars, len(df))

        for future_idx in range(start, end):
            future_row = df.iloc[future_idx]
            future_close = float(future_row["close"])
            future_high = float(future_row["high"])
            future_low = float(future_row["low"])

            if direction == "bullish":
                broke = future_close > signal_high if self.follow_through_use_close_break else future_high > signal_high

                if self.follow_through_min_move_percent > 0.0:
                    move_percent = ((future_close - signal_close) /
                                    max(signal_close, 1e-9)) * 100.0
                    broke = broke and move_percent >= self.follow_through_min_move_percent

                if broke:
                    return True, future_idx, df.index[future_idx]

            else:
                broke = future_close < signal_low if self.follow_through_use_close_break else future_low < signal_low

                if self.follow_through_min_move_percent > 0.0:
                    move_percent = ((signal_close - future_close) /
                                    max(signal_close, 1e-9)) * 100.0
                    broke = broke and move_percent >= self.follow_through_min_move_percent

                if broke:
                    return True, future_idx, df.index[future_idx]

        return False, None, None

    def _mss_confirmed(
        self,
        df: pd.DataFrame,
        idx: int,
        direction: SignalDirection,
        follow_through_passed: bool,
    ) -> Tuple[bool, Optional[int], Optional[pd.Timestamp], Optional[float]]:
        """
        Stufe 3:
        MSS / CHOCH = Bruch der relevanten Gegenseiten-Struktur nach dem Grab.

        bullish:
            Bruch über letztes Pivot-High vor dem Grab
        bearish:
            Bruch unter letztes Pivot-Low vor dem Grab
        """
        if not follow_through_passed:
            return False, None, None, None

        structure_ref = self._find_last_opposite_structure_level(
            df, idx, direction)
        if structure_ref is None:
            return False, None, None, None

        ref_idx, ref_price = structure_ref
        if ref_idx >= idx:
            return False, None, None, None

        start = idx + 1
        end = min(idx + 1 + self.mss_lookahead_bars, len(df))

        for future_idx in range(start, end):
            future_row = df.iloc[future_idx]
            future_close = float(future_row["close"])
            future_high = float(future_row["high"])
            future_low = float(future_row["low"])

            if direction == "bullish":
                broke = future_close > ref_price if self.mss_use_close_break else future_high > ref_price
                if broke:
                    return True, future_idx, df.index[future_idx], float(ref_price)

            else:
                broke = future_close < ref_price if self.mss_use_close_break else future_low < ref_price
                if broke:
                    return True, future_idx, df.index[future_idx], float(ref_price)

        return False, None, None, float(ref_price)

    def _score_signal(
        self,
        direction: SignalDirection,
        signal_type: SignalType,
        row: pd.Series,
        level: LiquidityLevel,
        sweep_percent: float,
        reclaimed: bool,
        confirmed: bool,
        current_index: int,
        trend: TrendState,
        with_trend: bool,
        stage: int,
    ) -> float:
        """
        Bewertet ein Signal mit Score-Modell + Stage-Boni.
        """
        score = 0.0
        close_pos = self._close_position_in_range(row)
        wick_ratio = self._wick_ratio(direction, row)
        age = level.age_bars(current_index)

        # Basis
        if signal_type == "grab":
            score += 40
        elif signal_type == "failed_grab":
            score += 18
        elif signal_type == "run":
            score += 8

        # Reclaim / Alt-Confirmation
        if reclaimed:
            score += 15
        if confirmed:
            score += 8

        # Equal Pool / Touches
        if level.is_equal_pool:
            score += 10

        score += min(level.touches * 4, 16)

        # Frische
        freshness_bonus = max(
            0.0,
            10.0 - (age / max(self.max_reference_age_bars, 1)) * 10.0,
        )
        score += freshness_bonus

        # Sweep-Größe
        if self.min_sweep_percent <= sweep_percent <= self.max_sweep_percent:
            center = (self.min_sweep_percent + self.max_sweep_percent) / 2.0
            spread = max(
                (self.max_sweep_percent - self.min_sweep_percent) / 2.0,
                0.0001,
            )
            distance_from_center = abs(sweep_percent - center)
            normalized = max(0.0, 1.0 - (distance_from_center / spread))
            score += normalized * 12.0
        else:
            score -= 6.0

        # Schlusslage
        if direction == "bullish":
            score += close_pos * 12.0
            if close_pos >= self.strong_close_threshold:
                score += self.strong_close_score_bonus
        else:
            bearish_close_strength = 1.0 - close_pos
            score += bearish_close_strength * 12.0
            if bearish_close_strength >= self.strong_close_threshold:
                score += self.strong_close_score_bonus

        # Wick-Qualität
        score += wick_ratio * self.wick_score_weight

        # Trend-/Range-Bias
        if trend == "range":
            score -= self.range_score_penalty

        if not with_trend:
            score -= self.counter_trend_score_penalty

        # Stage-Boni
        if stage >= 2:
            score += self.stage2_score_bonus
        if stage >= 3:
            score += self.stage3_score_bonus

        return round(score, 2)

    def _classify_signal(
        self,
        direction: SignalDirection,
        row: pd.Series,
        level_price: float,
        reclaimed: bool,
        sweep_percent: float,
    ) -> SignalType:
        """
        Unterscheidet Grab, Run und Failed Grab.
        """
        close = float(row["close"])

        if sweep_percent > self.max_sweep_percent:
            return "run"

        if direction == "bearish":
            if reclaimed and close < level_price:
                return "grab"
            if close >= level_price:
                return "run"
            return "failed_grab"

        if reclaimed and close > level_price:
            return "grab"
        if close <= level_price:
            return "run"
        return "failed_grab"

    def analyze(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Hauptmethode:
        - erzeugt Liquidity-Levels
        - scannt die letzten Bars auf Grabs / Runs
        - ergänzt Trend/Bias
        - bestimmt Stage 1 / 2 / 3
        - gibt strukturierte Ergebnisse zurück
        """
        if df is None or df.empty:
            return {"df": df, "levels": [], "signals": []}

        required = {"open", "high", "low", "close"}
        if not required.issubset(df.columns):
            return {"df": df, "levels": [], "signals": []}

        data = df.copy()

        if self.trend_filter == "sma200":
            sma_col = f"SMA{self.trend_sma_period}"
            data[sma_col] = data["close"].rolling(self.trend_sma_period).mean()

        levels = build_liquidity_levels(
            df=data,
            pivot_bars=self.pivot_bars,
            max_reference_age_bars=self.max_reference_age_bars,
            max_levels_per_side=self.max_levels_per_side,
            use_equal_levels=self.use_equal_levels,
            equal_level_threshold_percent=self.equal_level_threshold_percent,
            equal_level_recent_weight=self.equal_level_recent_weight,
        )

        signals: List[LiquiditySignal] = []
        consumed_level_keys = set()

        start_idx = max(0, len(data) - self.scan_recent_bars)

        for idx in range(start_idx, len(data)):
            row = data.iloc[idx]
            trend = self._detect_structure_trend(data, idx)

            for level in levels:
                if level.pivot_index >= idx:
                    continue

                level_key = (level.side, level.created_at,
                             round(level.price, 8))
                if self.one_sweep_per_level and level_key in consumed_level_keys:
                    continue

                if level.age_bars(idx) > self.max_reference_age_bars:
                    continue

                if self._level_was_previously_violated(data, level, idx):
                    continue

                direction: SignalDirection
                crossed = False

                # Bearish Grab über buy_side
                if level.side == "buy_side":
                    if float(row["high"]) > level.price:
                        direction = "bearish"
                        crossed = True
                    else:
                        continue

                # Bullish Grab unter sell_side
                elif level.side == "sell_side":
                    if float(row["low"]) < level.price:
                        direction = "bullish"
                        crossed = True
                    else:
                        continue
                else:
                    continue

                if not crossed:
                    continue

                with_trend = self._is_with_trend(direction, trend)

                sweep_percent = self._sweep_percent(
                    direction, row, level.price)
                if sweep_percent < self.min_sweep_percent:
                    continue

                reclaimed = self._passes_reclaim_rule(
                    direction, row, level.price)
                if not self._passes_opposite_candle_rule(direction, row):
                    reclaimed = False

                if not self._passes_trend_filter(direction, trend, row):
                    continue

                wick_ratio = self._wick_ratio(direction, row)
                if self.use_wick_filter and wick_ratio < self.min_wick_ratio:
                    continue

                signal_type = self._classify_signal(
                    direction=direction,
                    row=row,
                    level_price=level.price,
                    reclaimed=reclaimed,
                    sweep_percent=sweep_percent,
                )

                confirmed = self._confirmation_passed(
                    df=data,
                    idx=idx,
                    direction=direction,
                    level_price=level.price,
                    reclaimed=reclaimed,
                )

                follow_through, ft_idx, ft_time = self._follow_through_passed(
                    df=data,
                    idx=idx,
                    direction=direction,
                )

                mss_confirmed, mss_idx, mss_time, mss_level = self._mss_confirmed(
                    df=data,
                    idx=idx,
                    direction=direction,
                    follow_through_passed=follow_through,
                )

                stage = 1
                if follow_through:
                    stage = 2
                if mss_confirmed:
                    stage = 3

                score = self._score_signal(
                    direction=direction,
                    signal_type=signal_type,
                    row=row,
                    level=level,
                    sweep_percent=sweep_percent,
                    reclaimed=reclaimed,
                    confirmed=confirmed,
                    current_index=idx,
                    trend=trend,
                    with_trend=with_trend,
                    stage=stage,
                )

                flags = [
                    f"sweep={sweep_percent:.3f}%",
                    f"reclaimed={reclaimed}",
                    f"confirmed={confirmed}",
                    f"follow_through={follow_through}",
                    f"mss={mss_confirmed}",
                    f"wick_ratio={wick_ratio:.3f}",
                    f"trend={trend}",
                    f"with_trend={with_trend}",
                ]
                if mss_level is not None:
                    flags.append(f"mss_level={mss_level:.5f}")

                reason = (
                    f"{level.side} swept @ {level.price:.5f} | "
                    f"{' | '.join(flags)}"
                )

                signal = LiquiditySignal(
                    signal_time=data.index[idx],
                    signal_index=idx,
                    direction=direction,
                    signal_type=signal_type,
                    level_side=level.side,
                    level_price=float(level.price),
                    reference_time=level.created_at,
                    reference_index=level.pivot_index,
                    sweep_percent=round(sweep_percent, 4),
                    reclaimed=reclaimed,
                    confirmed=bool(follow_through),
                    close_position=round(
                        self._close_position_in_range(row), 4),
                    wick_ratio=round(wick_ratio, 4),
                    score=score,
                    reason=reason,
                    level_touches=level.touches,
                    equal_pool=level.is_equal_pool,
                    trend=trend,
                    with_trend=with_trend,
                    stage=stage,
                    stage_label=self.STAGE_LABELS[stage],
                    follow_through=follow_through,
                    follow_through_time=ft_time,
                    follow_through_index=ft_idx,
                    mss_confirmed=mss_confirmed,
                    mss_time=mss_time,
                    mss_index=mss_idx,
                    mss_level=mss_level,
                )

                if self._should_include_signal(signal):
                    signals.append(signal)
                    if self.one_sweep_per_level:
                        consumed_level_keys.add(level_key)

        signals.sort(
            key=lambda s: (s.stage, s.score, s.signal_time),
            reverse=True,
        )

        return {"df": data, "levels": levels, "signals": signals}

    def _should_include_signal(self, signal: LiquiditySignal) -> bool:
        """
        Filtert die Ausgabe nach Typ und Mindestscore.
        """
        if signal.score < self.score_threshold:
            return False

        if signal.signal_type == "grab":
            return True

        if signal.signal_type == "run":
            return self.show_runs

        if signal.signal_type == "failed_grab":
            return self.show_failed_grabs

        return False
