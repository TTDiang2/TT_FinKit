"""Run active strategy to generate signal using real-time (up-to-today) data.

All asset-keyed data (prices / returns / factor_exposures / target_weights)
uses SYMBOLS (e.g. "000300") — never the internal ResearchAsset.id UUID.
"""
import json
from datetime import date


def compute_risk_status(target_weights: dict, asset_exposures: dict) -> dict:
    """Compute risk status summary from target weights and current factor exposures."""
    status = {"alerts": [], "warnings": []}

    all_factors = set()
    for exposures in asset_exposures.values():
        all_factors.update(exposures.keys())

    for factor in all_factors:
        weighted_exposure = 0.0
        total_weight = 0.0
        for symbol, weight in target_weights.items():
            if symbol in asset_exposures:
                beta = asset_exposures[symbol].get(factor, 0.0)
                weighted_exposure += weight * beta
                total_weight += abs(weight)

        if total_weight > 0:
            avg_exposure = weighted_exposure / total_weight
            if abs(avg_exposure) >= 0.3:
                status["warnings"].append(f"{factor}: {avg_exposure:.2f}")

    return status


def get_next_rebalance_date(current_date: str, rebalance_freq: str) -> str:
    """Return next rebalance date after current_date.

    daily: tomorrow
    monthly: last day of next month
    weekly: next Friday
    """
    from datetime import date, timedelta
    import calendar

    d = date.fromisoformat(current_date)

    if rebalance_freq == "daily":
        return (d + timedelta(days=1)).isoformat()
    if rebalance_freq == "monthly":
        # Last day of next month
        if d.month == 12:
            next_month = date(d.year + 1, 1, 1)
        else:
            next_month = date(d.year, d.month + 1, 1)
        last_day = calendar.monthrange(next_month.year, next_month.month)[1]
        return date(next_month.year, next_month.month, last_day).isoformat()
    else:  # weekly
        # Next Friday (weekday 4)
        days_ahead = (4 - d.weekday()) % 7
        if days_ahead == 0:
            days_ahead = 7
        return (d + timedelta(days_ahead)).isoformat()


def generate_signal(strategy_code: str, params: dict, universe: list[str],
                    db_path: str = "", rebalance_freq: str = "monthly",
                    current_weights: dict | None = None, timeout: int = 60,
                    max_history_days: int = 750) -> dict:
    """Generate signal by running strategy on up-to-today data.

    Uses the same subprocess runner pattern as finkit_strategy/runner.py.
    Returns: {status, target_weights, risk_status, next_rebalance_date, as_of_date}
    """
    if not db_path:
        from ..config import public_db_path
        db_path = public_db_path()
    from finkit_strategy.runner import run_strategy_in_subprocess
    import tempfile, os, sqlite3

    today = date.today().isoformat()
    # 信号只需要回看窗口（动量/波动），不载全部历史——池子扩到数千只时
    # 全量加载会让 JSON 与子进程时间爆炸。750 天覆盖 min_history≤500+252 窗。
    from datetime import timedelta
    history_floor = (date.today() - timedelta(days=max_history_days)).isoformat()

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row

        # Pool: pooled research assets, keyed by symbol for the strategy.
        # When the strategy binds a universe (universe 非空), ONLY load those —
        # 否则绑定组合的策略会在全池上跑出错误信号。
        uni_set = {u for u in (universe or []) if u}
        pool = []
        symbol_to_id: dict[str, str] = {}
        arows = conn.execute(
            "SELECT id, symbol, name, asset_type, mgmt_fee, custody_fee, "
            "purchase_fee, redeem_rules FROM research_assets "
            "WHERE status = 'pooled'"
        ).fetchall()
        for a in arows:
            if uni_set and a["symbol"] not in uni_set:
                continue
            symbol_to_id[a["symbol"]] = a["id"]
            pool.append({
                "id": a["id"], "symbol": a["symbol"], "name": a["name"],
                "asset_type": a["asset_type"],
                "mgmt_fee": a["mgmt_fee"] or 0, "custody_fee": a["custody_fee"] or 0,
                "purchase_fee": a["purchase_fee"] or 0,
                "redeem_rules": json.loads(a["redeem_rules"] or "{}"),
            })

        # Prices: research_prices JOIN assets → symbol-keyed {date: price}
        # nav is NULL for all warehouse rows (data lives in `close`) — use
        # COALESCE so a future nav backfill doesn't break this either.
        prices: dict[str, dict[str, float]] = {}
        id_to_symbol = {v: k for k, v in symbol_to_id.items()}
        if symbol_to_id:
            ids = list(symbol_to_id.values())
            id_placeholders = ",".join("?" for _ in ids)
            rows = conn.execute(
                "SELECT asset_id, date, COALESCE(nav, close) AS px FROM research_prices "
                f"WHERE asset_id IN ({id_placeholders}) AND date <= ? AND date >= ? "
                "ORDER BY asset_id, date",
                [*ids, today, history_floor],
            ).fetchall()
            for r in rows:
                sym = id_to_symbol.get(r["asset_id"])
                if sym is None or r["px"] is None:
                    continue
                if sym not in prices:
                    prices[sym] = {}
                prices[sym][r["date"]] = float(r["px"])

        # Factor exposures: latest as_of per asset → symbol → {factor KEY: beta}
        factor_exposures: dict[str, dict[str, float]] = {}
        try:
            rows = conn.execute(
                """SELECT ra.symbol, f.key, ae.beta
                   FROM factor_exposures ae
                   JOIN factors f ON ae.factor_id = f.id
                   JOIN research_assets ra ON ra.id = ae.asset_id
                   WHERE ae.as_of_date = (
                       SELECT MAX(as_of_date) FROM factor_exposures
                       WHERE asset_id = ae.asset_id
                   )"""
            ).fetchall()
            for sym, factor_key, beta in rows:
                if not factor_key:
                    continue
                if sym not in factor_exposures:
                    factor_exposures[sym] = {}
                factor_exposures[sym][factor_key] = beta
        except Exception:
            factor_exposures = {}

    # Compute returns from prices (symbol-keyed)
    returns: dict[str, dict[str, float]] = {}
    for sym, price_dict in prices.items():
        sorted_dates = sorted(price_dict.keys())
        returns[sym] = {}
        for i in range(1, len(sorted_dates)):
            prev_price = price_dict[sorted_dates[i - 1]]
            curr_price = price_dict[sorted_dates[i]]
            if prev_price != 0:
                returns[sym][sorted_dates[i]] = (curr_price - prev_price) / prev_price

    # Run strategy
    rebalance_dates = [today]  # Only run for today
    data = {
        "strategy_code": strategy_code,
        "params": params,
        "pool": pool,
        "prices": prices,
        "returns": returns,
        "factor_values": {},
        "factor_exposures": factor_exposures,
        # 真实持仓权重（按最新净值计），让缓冲带等持仓感知逻辑在线上同样生效
        "current_weights": current_weights or {},
        "rebalance_dates": rebalance_dates,
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
        json.dump(data, f)
        input_path = f.name

    try:
        result = run_strategy_in_subprocess(input_path, timeout=timeout)

        if result["status"] != "ok":
            return {"status": "error", "error": result.get("error", "Strategy execution failed")}

        weights = result["weights"].get(today, {})
        # 与回测引擎同口径归一化：负权重截 0 后除以总和，防止信号权重超 100%
        gross = sum(max(0.0, float(v)) for v in weights.values())
        if gross > 0:
            weights = {k: max(0.0, float(v)) / gross for k, v in weights.items()}
        else:
            weights = {k: 0.0 for k in weights}

        # Compute risk status
        risk_status = compute_risk_status(weights, factor_exposures)

        return {
            "status": "ok",
            "target_weights": weights,
            "risk_status": risk_status,
            "next_rebalance_date": get_next_rebalance_date(today, rebalance_freq),
            "as_of_date": today,
        }
    finally:
        os.unlink(input_path)
