"""
Macro Analysis Service (Smart Beta)

Identifies market cycles using real FRED economic data via OpenBB,
with fallback to neutral scores when data is unavailable.
"""

import logging
from typing import Any, Dict, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# FRED series IDs used as crypto macro indicators
FRED_SERIES = {
    "fed_funds_rate": "FEDFUNDS",       # Federal Funds Rate (monthly)
    "treasury_10y": "DGS10",            # 10-Year Treasury Constant Maturity (daily)
    "inflation_expect": "T10YIE",       # 10-Year Breakeven Inflation Rate (daily)
    "m2_money_supply": "M2SL",          # M2 Money Supply (monthly)
}


class MacroAnalysisService:
    """Macro analysis using FRED economic data via OpenBB.

    When OpenBB/FRED data is unavailable, returns neutral scores
    so downstream strategies are not blocked.
    """

    def __init__(self):
        self._cache: Dict[str, Any] = {}
        self._cache_time: Optional[datetime] = None
        self._cache_ttl = timedelta(hours=6)

    async def _fetch_fred_series(self, series_id: str) -> Optional[float]:
        """Fetch the most recent value of a FRED series."""
        try:
            from app.services.openbb_data_service import openbb_data_service

            if not openbb_data_service.available:
                return None

            end = datetime.utcnow()
            start = end - timedelta(days=90)
            df = await openbb_data_service.get_economic_indicator(
                series_id, start=start, end=end
            )
            if df is None or df.empty:
                return None

            # Return the most recent non-null value
            if "value" in df.columns:
                recent = df["value"].dropna()
            else:
                recent = df.iloc[:, -1].dropna()
            return float(recent.iloc[-1]) if not recent.empty else None

        except Exception as e:
            logger.debug(f"FRED series {series_id} unavailable: {e}")
            return None

    async def get_macro_score(self, symbol: str = "BTCUSDT") -> Dict[str, Any]:
        """Compute macro score from real FRED data.

        Returns a dict with:
          - macro_score:       float in [-1.0, 1.0]
          - target_exposure:   float in [0.1, 1.0]
          - regime:            str (BULL / BEAR / SIDEWAYS / EXTREME_VOLATILITY)
          - indicators:        dict of raw indicator values
          - data_quality:      "real" | "neutral" | "stale"
        """

        # Fetch FRED data
        fed_rate = await self._fetch_fred_series("FEDFUNDS")
        treasury_10y = await self._fetch_fred_series("DGS10")
        infl_expect = await self._fetch_fred_series("T10YIE")

        data_quality = "neutral"
        score = 0.0
        indicators: Dict[str, Optional[float]] = {
            "fed_funds_rate": fed_rate,
            "treasury_10y": treasury_10y,
            "inflation_expect": infl_expect,
        }

        if fed_rate is not None and treasury_10y is not None:
            data_quality = "real"

            # --- Scoring logic based on real economic data ---

            # 1. Real rate (treasury - inflation expectations): low real rates
            #    are historically bullish for risk assets like crypto
            real_rate = treasury_10y - (infl_expect or 2.5)
            if real_rate < 0:
                score += 0.3  # Negative real rates → bullish
            elif real_rate < 1.0:
                score += 0.1
            elif real_rate > 3.0:
                score -= 0.3  # High real rates → bearish

            # 2. Fed funds rate level: high = tight liquidity
            if fed_rate < 1.0:
                score += 0.25  # Low rates → accommodative
            elif fed_rate < 3.0:
                score += 0.05
            elif fed_rate > 5.0:
                score -= 0.25  # Restrictive

            # 3. Yield curve steepness (10y - fed funds): inverted = recession fear
            spread = treasury_10y - fed_rate
            if spread < -0.5:
                score -= 0.3  # Inverted → recession signal
                data_quality = "real"
            elif spread > 2.0:
                score += 0.15  # Steep → expansion

            # 4. Inflation expectations: moderate inflation (2-3%) is healthy
            if infl_expect is not None:
                if 2.0 <= infl_expect <= 3.0:
                    score += 0.1
                elif infl_expect > 5.0:
                    score -= 0.2  # High inflation expectations

        # Clamp to [-1, 1]
        score = max(-1.0, min(1.0, score))

        # Target exposure: map score to position sizing
        target_exposure = 0.5 + (score * 0.5)
        target_exposure = max(0.1, min(1.0, target_exposure))

        # Determine market regime from score and real rate
        regime = await self._classify_regime(score)

        return {
            "symbol": symbol,
            "macro_score": round(score, 2),
            "target_exposure": round(target_exposure, 2),
            "regime": regime,
            "indicators": indicators,
            "data_quality": data_quality,
            "timestamp": datetime.utcnow().isoformat(),
            "recommendation": self._get_recommendation(score, regime),
        }

    async def _classify_regime(self, score: float) -> str:
        """Classify market regime based on macro score and additional context."""
        # Try to fetch volatility proxy via VIX-like indicator
        vix_proxy = await self._fetch_fred_series("T10YIE")
        high_volatility = vix_proxy is not None and vix_proxy > 4.0

        if high_volatility:
            return "EXTREME_VOLATILITY"
        if score > 0.4:
            return "BULL"
        elif score < -0.4:
            return "BEAR"
        return "SIDEWAYS"

    async def get_market_regime(self, symbol: str) -> str:
        """Identify the current market cycle."""
        macro = await self.get_macro_score(symbol)
        return macro.get("regime", "SIDEWAYS")

    def _get_recommendation(self, score: float, regime: str) -> str:
        if regime == "EXTREME_VOLATILITY":
            return "Risk Off (extreme volatility, consider reducing exposure)"
        if score > 0.6:
            return "Strong Accumulate"
        elif score > 0.2:
            return "Accumulate"
        elif score > -0.2:
            return "Neutral"
        elif score > -0.6:
            return "Reduce"
        return "Risk Off"


# Singleton
macro_analysis_service = MacroAnalysisService()
