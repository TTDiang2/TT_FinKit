"""portfolio_health: aggregate health metrics for a portfolio of investments.

Pure stdlib, no DB / async / network. Designed for FinKit's HealthPanel
which is fed via routers/investments.py -> /portfolio-health.
"""

from __future__ import annotations

from typing import Any


def _market_value(inv: dict[str, Any]) -> float:
    price = float(inv.get("current_price") or 0)
    qty = float(inv.get("quantity") or 0)
    return price * qty


def _loss_pct(inv: dict[str, Any]) -> float | None:
    purchase = inv.get("purchase_price")
    current = inv.get("current_price")
    if purchase is None or purchase == 0:
        return None
    return (float(current) - float(purchase)) / float(purchase) * 100.0


def _loss_severity(loss_pct: float) -> str:
    # loss_pct is negative for losses
    if loss_pct <= -10.0:
        return "high"
    if loss_pct < -5.0:  # -10% ~ -5% (exclusive)
        return "medium"
    return "low"


_SEVERITY_RANK = {"high": 3, "medium": 2, "low": 1}


def _sort_key(w: dict[str, Any]) -> tuple[int, str]:
    return (-_SEVERITY_RANK.get(w.get("severity", "low"), 0), str(w.get("id", "")))


def compute_health(investments: list[dict], metrics: list[dict]) -> dict:
    """Compute portfolio health metrics.

    Returns:
        {
          "concentration": {"max_single_pct": float, "top3_pct": float},
          "allocation": {asset_class: pct_float},
          "warnings": [{"id":..., "type":..., "severity":..., "message":...}, ...]
        }
    """
    # metrics is reserved for future per-fund extended metrics (e.g. max_drawdown)
    _ = metrics

    # ---- market values ----
    values: list[tuple[str, float]] = []
    for inv in investments:
        inv_id = inv.get("id")
        mv = _market_value(inv)
        values.append((inv_id, mv))

    total = sum(v for _, v in values)

    # ---- concentration ----
    if total > 0 and values:
        # sort values desc by market value
        sorted_vals = sorted((v for _, v in values), reverse=True)
        max_single = sorted_vals[0]
        top3 = sum(sorted_vals[:3])
        max_single_pct = max_single / total * 100.0
        top3_pct = top3 / total * 100.0
    else:
        max_single_pct = 0.0
        top3_pct = 0.0

    # ---- allocation by asset_class ----
    allocation_map: dict[str, float] = {}
    for inv in investments:
        cls = inv.get("asset_class") or "其他"
        allocation_map[cls] = allocation_map.get(cls, 0.0) + _market_value(inv)
    if total > 0:
        allocation = {k: v / total * 100.0 for k, v in allocation_map.items()}
    else:
        allocation = {}

    # ---- warnings ----
    warnings: list[dict[str, Any]] = []

    # 1) per-fund loss warnings
    for inv in investments:
        inv_id = inv.get("id")
        lp = _loss_pct(inv)
        if lp is None:
            continue
        if lp <= -10.0:
            sev = "high"
        elif lp < -5.0:
            sev = "medium"
        else:
            continue
        warnings.append({
            "id": inv_id,
            "type": "loss",
            "severity": sev,
            "message": f"浮亏 {lp:.2f}%",
        })

    # 2) concentration warning (can co-exist with per-fund loss warnings)
    if max_single_pct > 60.0:
        warnings.append({
            "id": None,
            "type": "concentration",
            "severity": "medium",
            "message": f"单基金占比 {max_single_pct:.2f}% 超过 60% 阈值",
        })

    # sort: high > medium > low, then by id
    warnings.sort(key=_sort_key)

    return {
        "concentration": {
            "max_single_pct": round(max_single_pct, 2),
            "top3_pct": round(top3_pct, 2),
        },
        "allocation": {k: round(v, 2) for k, v in allocation.items()},
        "warnings": warnings,
    }
