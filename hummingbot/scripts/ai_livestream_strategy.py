import os
from decimal import Decimal
from typing import Dict, List, Optional

from hummingbot.connector.connector_base import ConnectorBase
from hummingbot.strategy.strategy_v2_base import StrategyV2Base, StrategyV2ConfigBase
from hummingbot.strategy_v2.models.executor_actions import CreateExecutorAction, StopExecutorAction


class AILivestreamStrategyConfig(StrategyV2ConfigBase):
    script_file_name: str = os.path.basename(__file__)
    max_global_drawdown_quote: Optional[float] = None
    max_controller_drawdown_quote: Optional[float] = None


class AILivestreamStrategy(StrategyV2Base):
    """Simple strategy that runs the ai_livestream controller."""

    def __init__(self, connectors: Dict[str, ConnectorBase], config: AILivestreamStrategyConfig):
        super().__init__(connectors, config)
        self.config = config
        self.max_pnl_by_controller = {}
        self.max_global_pnl = Decimal("0")

    def on_tick(self):
        super().on_tick()

    def create_actions_proposal(self) -> List[CreateExecutorAction]:
        return []

    def stop_actions_proposal(self) -> List[StopExecutorAction]:
        return []

    def apply_initial_setting(self):
        for controller_id, controller in self.controllers.items():
            self.max_pnl_by_controller[controller_id] = Decimal("0")

    def send_performance_report(self):
        if self._pub:
            reports = {cid: self.get_controller_report(cid) for cid in self.controllers}
            self._pub(reports)

    def get_controller_report(self, controller_id: str) -> dict:
        report = self.controller_reports.get(controller_id, {}).get("performance")
        return {
            "performance": report.dict() if report else {},
            "custom_info": self.controllers[controller_id].get_custom_info()
        }
