"""
modules/liquidityGrabScanner/detector.py

Erkennt Liquidity Grabs, Sweeps und Runs an zuvor definierten Liquidity-Levels.

Das Modul bewertet jedes Signal, klassifiziert es und liefert eine
strukturierte Rückgabe für Scanner und Chart-Plot.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Literal

import pandas as pd

from .levels import LiquidityLevel, build_liquidity_levels


SignalDirection = Literal["bullish", "bearish"]
SignalType = Literal["grab", "run", "failed_grab"]


@dataclass
class LiquiditySignal:
    """
    Repräsentiert ein erkanntes Liquidity-Event.
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
    confirmed: bool
    close_position: float
    wick_ratio: float
    score: float
    reason: str
    level_touches: int
    equal_pool: bool

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class LiquidityGrabDetector:
    """
    Erzeugt Liquidity-Levels und scannt Bars auf Sweep-/Grab-/Run-Verhalten.
    """

    def __init__(self, cfg: Dict[str, Any]):
        lg = cfg.get("liquidity_grab", {})

        self.pivot_bars = int(lg.get("pivot_bars", 3))
        self.lookback_bars = int(lg.get("lookback_bars", 260))
        self.scan_recent_bars = int(lg.get("scan_recent_bars", 8))
        self.max_reference_age_bars = int(lg.get("max_reference_age_bars", 120))
        self.max_levels_per_side = int(lg.get("max_levels_per_side", 12))

        self.use_equal_levels = bool(lg.get("use_equal_levels", True))
        self.equal_level_threshold_percent = float(
            lg.get("equal_level_threshold_percent", 0.08)
        )
        self.equal_level_recent_weight = float(
            lg.get("equal_level_recent_weight", 0.70)
        )

        self.min_sweep_percent = float(lg.get("min_sweep_percent", 0.03))
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

        self.trend_filter = str(lg.get("trend_filter", "none")).strip()
        self.trend_sma_period = int(lg.get("trend_sma_period", 200))

        self.score_threshold = float(lg.get("score_threshold", 55))
        self.show_runs = bool(lg.get("show_runs", True))
        self.show_failed_grabs = bool(lg.get("show_failed_grabs", False))

        # Neu: Wick / Rejection
        self.use_wick_filter = bool(lg.get("use_wick_filter", False))
        self.min_wick_ratio = float(lg.get("min_wick_ratio", 0.40))
        self.wick_score_weight = float(lg.get("wick_score_weight", 10.0))
        self.strong_close_score_bonus = float(
            lg.get("strong_close_score_bonus", 10.0)
        )
        self.strong_close_threshold = float(
            lg.get("strong_close_threshold", 0.70)
        )

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

    def _passes_trend_filter(
        self,
        direction: SignalDirection,
        row: pd.Series,
    ) -> bool:
        """
        Optionaler Trendfilter, z. B. relativ zum SMA200.
        """
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
        Prüft die gewünschte Signalbestätigung.
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
    ) -> float:
        """
        Bewertet ein Signal mit einem einfachen, aber gut steuerbaren Score-Modell.
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

        # Reclaim / Confirmation
        if reclaimed:
            score += 15
        if confirmed:
            score += 15

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

        # Neu: Wick-Qualität
        score += wick_ratio * self.wick_score_weight

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

            for level in levels:
                if level.pivot_index >= idx:
                    continue

                level_key = (level.side, level.created_at, round(level.price, 8))
                if self.one_sweep_per_level and level_key in consumed_level_keys:
                    continue

                if level.age_bars(idx) > self.max_reference_age_bars:
                    continue

                if self._level_was_previously_violated(data, level, idx):
                    continue

                # Bearish Grab über buy_side
                if level.side == "buy_side":
                    if float(row["high"]) <= level.price:
                        continue

                    direction: SignalDirection = "bearish"
                    sweep_percent = self._sweep_percent(direction, row, level.price)

                    if sweep_percent < self.min_sweep_percent:
                        continue

                    reclaimed = self._passes_reclaim_rule(direction, row, level.price)
                    if not self._passes_opposite_candle_rule(direction, row):
                        reclaimed = False

                    if not self._passes_trend_filter(direction, row):
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

                    score = self._score_signal(
                        direction=direction,
                        signal_type=signal_type,
                        row=row,
                        level=level,
                        sweep_percent=sweep_percent,
                        reclaimed=reclaimed,
                        confirmed=confirmed,
                        current_index=idx,
                    )

                    reason = (
                        f"buy-side liquidity swept @ {level.price:.5f} | "
                        f"sweep={sweep_percent:.3f}% | reclaimed={reclaimed} | "
                        f"confirmed={confirmed} | wick_ratio={wick_ratio:.3f}"
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
                        confirmed=confirmed,
                        close_position=round(self._close_position_in_range(row), 4),
                        wick_ratio=round(wick_ratio, 4),
                        score=score,
                        reason=reason,
                        level_touches=level.touches,
                        equal_pool=level.is_equal_pool,
                    )

                    if self._should_include_signal(signal):
                        signals.append(signal)
                        if self.one_sweep_per_level:
                            consumed_level_keys.add(level_key)

                # Bullish Grab unter sell_side
                if level.side == "sell_side":
                    if float(row["low"]) >= level.price:
                        continue

                    direction = "bullish"
                    sweep_percent = self._sweep_percent(direction, row, level.price)

                    if sweep_percent < self.min_sweep_percent:
                        continue

                    reclaimed = self._passes_reclaim_rule(direction, row, level.price)
                    if not self._passes_opposite_candle_rule(direction, row):
                        reclaimed = False

                    if not self._passes_trend_filter(direction, row):
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

                    score = self._score_signal(
                        direction=direction,
                        signal_type=signal_type,
                        row=row,
                        level=level,
                        sweep_percent=sweep_percent,
                        reclaimed=reclaimed,
                        confirmed=confirmed,
                        current_index=idx,
                    )

                    reason = (
                        f"sell-side liquidity swept @ {level.price:.5f} | "
                        f"sweep={sweep_percent:.3f}% | reclaimed={reclaimed} | "
                        f"confirmed={confirmed} | wick_ratio={wick_ratio:.3f}"
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
                        confirmed=confirmed,
                        close_position=round(self._close_position_in_range(row), 4),
                        wick_ratio=round(wick_ratio, 4),
                        score=score,
                        reason=reason,
                        level_touches=level.touches,
                        equal_pool=level.is_equal_pool,
                    )

                    if self._should_include_signal(signal):
                        signals.append(signal)
                        if self.one_sweep_per_level:
                            consumed_level_keys.add(level_key)

        signals.sort(key=lambda s: (s.score, s.signal_time), reverse=True)

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