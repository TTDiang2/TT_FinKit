"""portfolio_health: aggregate health metrics for a portfolio of investments.

Pure stdlib, no DB / async / network. Designed for FinKit's HealthPanel
which is fed via routers/investments.py -> /portfolio-health.
"""
from __future__ import annotations

from typing import Any, Optional


def _market_value(inv: dict[str, Any]) -> float:
    price = float(inv.get("current_price") or 0)
    qty = float(inv.get("quantity") or 0)
    return price * qty


def _loss_pct(inv: dict[str, Any]) -> Optional[float]:
    purchase = inv.get("purchase_price")
    current = inv.get("current_price")
    if purchase is None or purchase == 0:
        return None
    if current is None or current <= 0:
        return None
    return (float(current) - float(purchase)) / float(purchase) * 100.0


def _is_open_position(inv: dict[str, Any]) -> bool:
    return not inv.get("sell_date") and float(inv.get("quantity") or 0) > 0


def compute_health(investments: list[dict], metrics: list[dict]) -> dict:
    """Compute portfolio health: per-fund loss warnings + portfolio-level
    floating P&L. Closed positions (sell_date set) and zero-share rows are
    excluded from floating-P&L warnings — their P&L is already realized.
    """
    _ = metrics

    open_positions = [inv for inv in investments if _is_open_position(inv)]
    total_market_value = sum(_market_value(inv) for inv in open_positions)
    total_cost = sum(
        float(inv.get("purchase_price") or 0) * float(inv.get("quantity") or 0)
        for inv in open_positions
    )

    floating_pnl = total_market_value - total_cost
    floating_pnl_pct = (
        floating_pnl / total_cost * 100.0 if total_cost > 0 else 0.0
    )

    warnings: list[dict[str, Any]] = []

    # 1) per-fund loss warnings (open positions only, name included)
    for inv in open_positions:
        lp = _loss_pct(inv)
        if lp is None:
            continue
        if lp <= -10.0:
            sev = "high"
        elif lp < -5.0:
            sev = "medium"
        else:
            continue
        name = inv.get("name") or "未命名持仓"
        warnings.append({
            "id": inv.get("id"),
            "type": "loss",
            "severity": sev,
            "message": f"「{name}」浮亏 {lp:.2f}%（现价 {inv.get('current_price')} vs 摊薄成本 {inv.get('purchase_price')}）",
        })

    # 2) portfolio-level floating loss warning
    if total_cost > 0 and floating_pnl_pct <= -10.0:
        warnings.append({
            "id": None,
            "type": "portfolio_loss",
            "severity": "high",
            "message": f"组合整体浮亏 {floating_pnl_pct:.2f}%（市值 {total_market_value:,.2f} vs 成本 {total_cost:,.2f}）",
        })

    sev_rank = {"high": 3, "medium": 2, "low": 1}
    warnings.sort(key=lambda w: (-sev_rank.get(w.get("severity", "low"), 0), str(w.get("id") or "")))

    return {
        "floating_pnl": round(floating_pnl, 2),
        "floating_pnl_pct": round(floating_pnl_pct, 2),
        "total_market_value": round(total_market_value, 2),
        "total_cost": round(total_cost, 2),
        "warnings": warnings,
    }
