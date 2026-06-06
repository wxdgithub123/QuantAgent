"""OrderIntent execution bridge for PRD stage 2.

This module turns a persisted TradingAgents/coordination decision into a
standardized, manually executable paper-trading intent.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from sqlalchemy import text

from app.services.audit_service import audit_service
from app.services.database import get_db
from app.services.market_data_gateway import market_data_gateway
from app.services.paper_trading_service import paper_trading_service

logger = logging.getLogger(__name__)


@dataclass
class OrderIntent:
    intent_id: str
    decision_id: int
    symbol: str
    direction: str  # long | short | flat
    side: Optional[str]  # BUY | SELL | None
    position_pct: float
    confidence: float
    valid_until: str
    trigger_reason: str
    source: str = "coordination_history"
    exchange_id: str = "okx"
    order_type: str = "MARKET"
    status: str = "READY"


class OrderIntentService:
    """Converts TradingAgents decisions into guarded paper-trading intents."""

    max_position_pct = 0.10
    min_confidence_for_trade = 0.55

    async def preview_from_decision(
        self,
        decision_id: int,
        *,
        exchange_id: str = "okx",
        position_pct: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Create/read the draft intent only; no live price, sizing or RiskGuard."""
        return await self.draft_intent_from_decision(
            decision_id,
            exchange_id=exchange_id,
            position_pct=position_pct,
        )

    async def draft_intent_from_decision(
        self,
        decision_id: int,
        *,
        exchange_id: str = "okx",
        position_pct: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Persist decision-evidence intent draft without realtime dependencies."""
        decision = await self._load_decision(decision_id)
        intent = self._build_intent(decision, exchange_id=exchange_id, position_pct=position_pct)
        return await self._draft_response(decision, intent, exchange_id)

    async def execute_from_decision(
        self,
        decision_id: int,
        *,
        exchange_id: str = "okx",
        position_pct: Optional[float] = None,
    ) -> Dict[str, Any]:
        decision = await self._load_decision(decision_id)
        intent_obj = self._build_intent(decision, exchange_id=exchange_id, position_pct=position_pct)
        draft = await self._draft_response(decision, intent_obj, exchange_id)
        if intent_obj.side is None:
            return draft

        price = await self._get_price(intent_obj.symbol, exchange_id)
        sizing = await self._calculate_quantity(intent_obj, price)
        risk_preview = await self._risk_preview(intent_obj, price, sizing["quantity"])

        preview = {
            **draft,
            "status": "RISK_CHECKED" if risk_preview["allowed"] else "BLOCKED",
            "message": "OrderIntent 已通过实时执行前风控，准备进入本地模拟成交。" if risk_preview["allowed"] else "OrderIntent 草案已生成，但当前实时风控不允许执行。",
            "intent": self._intent_api(intent_obj, quantity=sizing["quantity"]),
            "price": price,
            "sizing": sizing,
            "risk_preview": risk_preview,
            "passed": risk_preview["allowed"],
            "blockedReason": risk_preview.get("reason"),
        }
        await self._audit(
            "RISK_CHECK_PASSED" if risk_preview["allowed"] else "RISK_BLOCKED",
            intent_obj,
            {
                "stage": "execution_preview_or_result",
                "decision": self._decision_audit_payload(decision),
                "price": price,
                "sizing": sizing,
                "risk_preview": risk_preview,
            },
        )
        if not risk_preview["allowed"]:
            return preview

        client_order_id = intent_obj.intent_id
        try:
            execution = await paper_trading_service.create_order(
                symbol=intent_obj.symbol,
                side=str(intent_obj.side),
                quantity=preview["sizing"]["quantity"],
                price=preview["price"],
                order_type=intent_obj.order_type,
                benchmark_price=preview["price"],
                client_order_id=client_order_id,
                strategy_id="tradingagents",
                mode="paper",
                exchange_id=exchange_id,
            )
            duplicate = bool(execution.get("duplicate"))
            result = {
                **preview,
                "status": execution.get("status", "EXECUTED"),
                "message": "该 OrderIntent 已执行过，本次没有重复下单。" if duplicate else "OrderIntent 已通过风控并完成模拟盘执行。",
                "order_id": execution.get("order_id"),
                "execution": execution,
            }
            await self._audit(
                "PAPER_ORDER_FILLED",
                intent_obj,
                {
                    **result,
                    "stage": "execution_preview_or_result",
                    "decision": self._decision_audit_payload(decision),
                },
            )
            return result
        except ValueError as exc:
            result = {
                **preview,
                "status": "BLOCKED",
                "message": str(exc),
                "order_id": None,
                "execution": None,
            }
            await self._audit(
                "PAPER_ORDER_REJECTED",
                intent_obj,
                {
                    **result,
                    "stage": "execution_preview_or_result",
                    "decision": self._decision_audit_payload(decision),
                },
            )
            return result

    async def execute_manual_order(
        self,
        *,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        order_type: str = "MARKET",
        exchange_id: str = "okx",
    ) -> Dict[str, Any]:
        """Wrap a manual paper order in OrderIntent -> RiskGuard -> PaperOrder."""
        normalized_side = side.upper()
        intent = OrderIntent(
            intent_id=f"OI-MANUAL-{int(datetime.now(timezone.utc).timestamp() * 1000)}",
            decision_id=0,
            symbol=symbol.upper(),
            direction="long" if normalized_side == "BUY" else "short",
            side=normalized_side,
            position_pct=0.0,
            confidence=1.0,
            valid_until=(datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
            trigger_reason="用户在本地模拟盘手动下单",
            source="manual",
            exchange_id=exchange_id,
            order_type=order_type,
            status="CREATED",
        )
        sizing = {
            "total_equity": None,
            "target_notional": round(float(quantity) * float(price), 8),
            "quantity": float(quantity),
            "position_pct": None,
        }
        risk_preview = await self._risk_preview(intent, price, quantity)
        await self._audit("ORDER_INTENT_CREATED", intent, {"price": price, "sizing": sizing})
        preview = {
            "status": "RISK_CHECKED" if risk_preview["allowed"] else "BLOCKED",
            "message": "手动 OrderIntent 已通过风控，准备进入本地模拟成交。" if risk_preview["allowed"] else "手动 OrderIntent 已生成，但当前风控不允许执行。",
            "data_lineage": self._data_lineage(exchange_id),
            "intent": self._intent_api(intent, quantity=quantity),
            "price": price,
            "sizing": sizing,
            "risk_preview": risk_preview,
            "passed": risk_preview["allowed"],
            "blockedReason": risk_preview.get("reason"),
        }
        await self._audit("RISK_CHECK_PASSED" if risk_preview["allowed"] else "RISK_BLOCKED", intent, preview)
        if not risk_preview["allowed"]:
            return preview

        try:
            execution = await paper_trading_service.create_order(
                symbol=intent.symbol,
                side=normalized_side,
                quantity=quantity,
                price=price,
                order_type=order_type,
                benchmark_price=price,
                client_order_id=intent.intent_id,
                strategy_id="manual",
                mode="paper",
                exchange_id=exchange_id,
            )
            result = {
                **preview,
                "status": execution.get("status", "EXECUTED"),
                "message": "手动 OrderIntent 已通过风控并完成本地模拟成交。",
                "order_id": execution.get("order_id"),
                "execution": execution,
            }
            await self._audit("PAPER_ORDER_FILLED", intent, result)
            return result
        except ValueError as exc:
            result = {
                **preview,
                "status": "BLOCKED",
                "message": str(exc),
                "blockedReason": str(exc),
                "order_id": None,
                "execution": None,
            }
            await self._audit("PAPER_ORDER_REJECTED", intent, result)
            return result

    async def _preview(
        self,
        decision: Dict[str, Any],
        intent: OrderIntent,
        exchange_id: str,
    ) -> Dict[str, Any]:
        if intent.side is None:
            await self._audit("HOLD_RECORDED", intent, {"decision": self._decision_audit_payload(decision)})
            return {
                "status": "NO_ACTION",
                "message": "该决策为观望/空仓，不生成模拟盘订单。",
                "data_lineage": self._data_lineage(exchange_id),
                "intent": self._intent_api(intent),
                "decision": self._decision_summary(decision),
            }

        price = await self._get_price(intent.symbol, exchange_id)
        sizing = await self._calculate_quantity(intent, price)
        risk_preview = await self._risk_preview(intent, price, sizing["quantity"])

        await self._audit(
            "ORDER_INTENT_CREATED",
            intent,
            {
                "decision": self._decision_audit_payload(decision),
                "price": price,
                "sizing": sizing,
                "risk_preview": risk_preview,
            },
        )
        await self._audit(
            "RISK_CHECK_PASSED" if risk_preview["allowed"] else "RISK_BLOCKED",
            intent,
            {
                "decision": self._decision_audit_payload(decision),
                "price": price,
                "sizing": sizing,
                "risk_preview": risk_preview,
            },
        )
        return {
            "status": "READY" if risk_preview["allowed"] else "BLOCKED",
            "message": "OrderIntent 已生成，等待手动执行。" if risk_preview["allowed"] else "OrderIntent 已生成，但当前风控不允许执行。",
            "data_lineage": self._data_lineage(exchange_id),
            "intent": self._intent_api(intent, quantity=sizing["quantity"]),
            "price": price,
            "sizing": sizing,
            "risk_preview": risk_preview,
            "decision": self._decision_summary(decision),
        }

    async def _draft_response(
        self,
        decision: Dict[str, Any],
        intent: OrderIntent,
        exchange_id: str,
    ) -> Dict[str, Any]:
        action = "HOLD_RECORDED" if intent.side is None else "ORDER_INTENT_CREATED"
        status = "NO_ACTION" if intent.side is None else "READY"
        if intent.status == "BLOCKED":
            status = "BLOCKED"
        details = {
            "stage": "decision_evidence",
            "decision": self._decision_audit_payload(decision),
            "execution_note": "Draft only. No realtime price/account/position lookup and no RiskGuard check.",
        }
        await self._audit_once(action, intent, details)
        return {
            "status": status,
            "message": "该决策为观望/空仓，不生成模拟盘订单。" if intent.side is None else "OrderIntent 草案已生成，等待用户显式执行。",
            "data_lineage": self._data_lineage(exchange_id),
            "intent": self._intent_api(intent),
            "decision": self._decision_summary(decision),
            "draft_only": True,
            "risk_preview": None,
            "price": None,
            "sizing": None,
        }

    async def _load_decision(self, decision_id: int) -> Dict[str, Any]:
        async with get_db() as session:
            row = (
                await session.execute(
                    text(
                        """
                        SELECT id, symbol, timestamp, final_signal, confidence,
                               risk_veto, summary, agent_signals,
                               input_snapshot_ids, role_opinions, position_advice, risk_notes
                        FROM coordination_history
                        WHERE id = :id
                        """
                    ),
                    {"id": decision_id},
                )
            ).fetchone()
        if not row:
            raise ValueError(f"Coordination decision {decision_id} not found")
        return {
            "id": row[0],
            "symbol": row[1],
            "timestamp": row[2],
            "final_signal": row[3],
            "confidence": float(row[4] or 0),
            "risk_veto": bool(row[5]),
            "summary": row[6] or "",
            "agent_signals": row[7] or [],
            "input_snapshot_ids": row[8] or {},
            "role_opinions": row[9] or [],
            "position_advice": row[10] or {},
            "risk_notes": row[11] or "",
        }

    def _build_intent(
        self,
        decision: Dict[str, Any],
        *,
        exchange_id: str,
        position_pct: Optional[float],
    ) -> OrderIntent:
        signal = str(decision.get("final_signal") or "WAIT").upper()
        confidence = float(decision.get("confidence") or 0)
        side: Optional[str]
        direction: str
        status = "READY"

        if decision.get("risk_veto"):
            side = None
            direction = "flat"
            status = "BLOCKED"
        elif signal == "BUY" and confidence >= self.min_confidence_for_trade:
            side = "BUY"
            direction = "long"
        elif signal == "SELL" and confidence >= self.min_confidence_for_trade:
            side = "SELL"
            direction = "short"
        else:
            side = None
            direction = "flat"
            status = "NO_ACTION"

        requested_pct = position_pct
        if requested_pct is None:
            advice = decision.get("position_advice") or {}
            requested_pct = self._read_position_pct(advice) or min(0.05 + max(confidence - 0.55, 0) * 0.20, self.max_position_pct)
        capped_pct = min(max(float(requested_pct), 0.0), self.max_position_pct) if side else 0.0
        valid_until = datetime.now(timezone.utc) + timedelta(minutes=15)
        return OrderIntent(
            intent_id=self._intent_id(decision, exchange_id, capped_pct),
            decision_id=int(decision["id"]),
            symbol=str(decision["symbol"]).upper(),
            direction=direction,
            side=side,
            position_pct=round(capped_pct, 4),
            confidence=round(confidence, 4),
            valid_until=valid_until.isoformat(),
            trigger_reason=decision.get("summary") or f"TradingAgents final_signal={signal}",
            exchange_id=exchange_id,
            status=status,
        )

    @staticmethod
    def _intent_id(decision: Dict[str, Any], exchange_id: str, position_pct: float) -> str:
        pct_bps = int(round(position_pct * 10000))
        return f"OI-{int(decision['id'])}-{exchange_id.lower()}-{pct_bps:04d}"

    @staticmethod
    def _read_position_pct(advice: Dict[str, Any]) -> Optional[float]:
        for key in ("position_pct", "suggested_position_pct", "target_position_pct", "size_pct", "allocation_pct"):
            value = advice.get(key)
            if isinstance(value, (int, float)):
                return float(value) / 100 if value > 1 else float(value)
        return None

    @staticmethod
    def _data_lineage(exchange_id: str) -> Dict[str, str]:
        return {
            "decision_source": "coordination_history / TradingAgents decision",
            "price_source": f"MarketDataGateway: OpenBB/yfinance first, CCXT/{exchange_id.upper()} fallback",
            "risk_guard": "RiskManager.check_order",
            "execution_mode": "paper trading only; never real exchange execution",
            "audit_stream": "audit_logs ORDER_INTENT_*",
        }

    @staticmethod
    def _intent_api(intent: OrderIntent, *, quantity: Optional[float] = None) -> Dict[str, Any]:
        action = "HOLD" if intent.side is None else str(intent.side).upper()
        status_map = {
            "READY": "CREATED",
            "NO_ACTION": "CREATED",
            "BLOCKED": "BLOCKED",
            "CREATED": "CREATED",
            "RISK_CHECKED": "RISK_CHECKED",
            "EXECUTED": "EXECUTED",
            "CANCELLED": "CANCELLED",
        }
        return {
            "id": intent.intent_id,
            "intent_id": intent.intent_id,
            "symbol": intent.symbol,
            "action": action,
            "side": intent.direction,
            "positionRatio": intent.position_pct,
            "position_pct": intent.position_pct,
            "quantity": quantity,
            "confidence": intent.confidence,
            "validUntil": intent.valid_until,
            "valid_until": intent.valid_until,
            "reason": intent.trigger_reason,
            "sourceDecisionId": intent.decision_id if intent.decision_id else None,
            "decision_id": intent.decision_id if intent.decision_id else None,
            "createdAt": datetime.now(timezone.utc).isoformat(),
            "status": status_map.get(intent.status, intent.status),
            "source": intent.source,
            "exchange_id": intent.exchange_id,
            "order_type": intent.order_type,
        }

    async def _get_price(self, symbol: str, exchange_id: str) -> float:
        price = await market_data_gateway.get_price(
            symbol,
            openbb_provider="yfinance",
            allow_ccxt_fallback=True,
            fallback_exchange=exchange_id,
        )
        if not price or price <= 0:
            raise ValueError(f"无法获取 {symbol} 当前价格，不能生成可执行 OrderIntent")
        return float(price)

    async def _calculate_quantity(self, intent: OrderIntent, price: float) -> Dict[str, Any]:
        balance = await paper_trading_service.get_balance()
        total_equity = float(balance.get("total_balance") or balance.get("available_balance") or 0)
        notional = total_equity * intent.position_pct
        quantity = notional / price if price > 0 else 0
        if quantity <= 0:
            raise ValueError("模拟账户权益不足，不能生成有效下单数量")
        return {
            "total_equity": round(total_equity, 8),
            "target_notional": round(notional, 8),
            "quantity": round(quantity, 8),
            "position_pct": intent.position_pct,
        }

    async def _risk_preview(self, intent: OrderIntent, price: float, quantity: float) -> Dict[str, Any]:
        try:
            balance_data = await paper_trading_service.get_balance()
            positions_data = await paper_trading_service.get_positions(exchange_id=intent.exchange_id)
            current_positions = {p["symbol"]: p["quantity"] for p in positions_data}
            available_balance = float(balance_data.get("available_balance", 0.0))
            total_portfolio = available_balance + sum(
                float(p.get("quantity", 0.0)) * float(p.get("mark_price", p.get("avg_price", price)))
                for p in positions_data
            )
            from app.services.risk_manager import risk_manager

            checked_rules = await risk_manager.preview_order_rules(
                symbol=intent.symbol,
                side=str(intent.side),
                quantity=quantity,
                price=price,
                current_balance=available_balance,
                current_positions=current_positions,
                total_portfolio_value=total_portfolio,
                leverage=1,
            )
            risk_result = await risk_manager.check_order(
                symbol=intent.symbol,
                side=str(intent.side),
                quantity=quantity,
                price=price,
                current_balance=available_balance,
                current_positions=current_positions,
                total_portfolio_value=total_portfolio,
                market_price=price,
                leverage=1,
            )
            return {
                "allowed": bool(risk_result.allowed),
                "passed": bool(risk_result.allowed),
                "rule": risk_result.rule,
                "reason": risk_result.reason,
                "blockedReason": risk_result.reason or None,
                "blocked_reason": risk_result.reason or None,
                "checkedRules": checked_rules,
                "checked_rules": checked_rules,
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as exc:
            logger.warning("Risk preview failed for %s: %s", intent.intent_id, exc)
            return {
                "allowed": False,
                "passed": False,
                "rule": "RISK_PREVIEW_ERROR",
                "reason": str(exc),
                "blockedReason": str(exc),
                "blocked_reason": str(exc),
                "checkedRules": [],
                "checked_rules": [],
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }

    async def _audit(self, action: str, intent: OrderIntent, details: Dict[str, Any]) -> None:
        await audit_service.log_event(
            action=action,
            user_id="system",
            resource=intent.symbol,
            details={
                "stage": "prd_stage_2_execution",
                "data_lineage": self._data_lineage(intent.exchange_id),
                "intent": self._intent_api(intent),
                "internal_intent": asdict(intent),
                **details,
            },
            ip_address="internal",
        )

    async def _audit_once(self, action: str, intent: OrderIntent, details: Dict[str, Any]) -> None:
        if await self._has_audit_event(action, intent):
            return
        await self._audit(action, intent, details)

    async def _has_audit_event(self, action: str, intent: OrderIntent) -> bool:
        try:
            async with get_db() as session:
                row = (
                    await session.execute(
                        text(
                            """
                            SELECT id
                            FROM audit_logs
                            WHERE action = :action
                              AND (
                                details->>'orderIntentId' = :intent_id
                                OR details->'intent'->>'id' = :intent_id
                                OR details->'intent'->>'intent_id' = :intent_id
                              )
                            LIMIT 1
                            """
                        ),
                        {"action": action, "intent_id": intent.intent_id},
                    )
                ).first()
            return row is not None
        except Exception:
            return False

    @staticmethod
    def _decision_summary(decision: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id": decision["id"],
            "symbol": decision["symbol"],
            "timestamp": decision["timestamp"].isoformat() if decision.get("timestamp") else None,
            "final_signal": decision["final_signal"],
            "confidence": decision["confidence"],
            "risk_veto": decision["risk_veto"],
            "summary": decision["summary"],
        }

    @staticmethod
    def _decision_audit_payload(decision: Dict[str, Any]) -> Dict[str, Any]:
        payload = OrderIntentService._decision_summary(decision)
        payload["input_snapshot_ids"] = decision.get("input_snapshot_ids") or {}
        payload["role_count"] = len(decision.get("role_opinions") or decision.get("agent_signals") or [])
        return payload


order_intent_service = OrderIntentService()
