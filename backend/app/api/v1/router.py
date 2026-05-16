"""
API V1 Router
"""

from fastapi import APIRouter

from app.api.v1.endpoints import market, trading, auth, strategy, analytics, risk, replay, profiles, composition, skill, dynamic_selection, walk_forward, hummingbot, paper_bot_equity, testnet_bot

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(market.router, prefix="/market", tags=["Market Data"])
api_router.include_router(trading.router, prefix="/trading", tags=["Trading"])
api_router.include_router(risk.router, prefix="/risk", tags=["Risk Management"])
api_router.include_router(strategy.router, prefix="/strategy", tags=["Strategy"])
api_router.include_router(profiles.router, prefix="/profiles", tags=["Strategy Profiles"])
api_router.include_router(analytics.router, prefix="/analytics", tags=["Analytics"])
api_router.include_router(replay.router, prefix="/replay", tags=["Historical Replay"])
api_router.include_router(composition.router, prefix="/strategy", tags=["Strategy"])
api_router.include_router(skill.router, prefix="/skills", tags=["Skills"])
api_router.include_router(dynamic_selection.router, prefix="/dynamic-selection", tags=["Dynamic Selection"])
api_router.include_router(walk_forward.router, prefix="/walk-forward", tags=["Walk-Forward Optimization"])
api_router.include_router(hummingbot.router, prefix="/hummingbot", tags=["Hummingbot"])
# Paper Bot Equity endpoints — 挂载在 hummingbot 路径下
api_router.include_router(paper_bot_equity.router, prefix="/hummingbot", tags=["Hummingbot"])
# Testnet Perpetual Bot endpoints — 挂载在 hummingbot/testnet-bots 路径下
api_router.include_router(testnet_bot.router, prefix="/hummingbot", tags=["Hummingbot Testnet"])
