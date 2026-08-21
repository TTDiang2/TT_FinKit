"""Run active strategy to generate signal using real-time (up-to-today) data."""
import json
from datetime import date

def compute_risk_status(target_weights: dict, asset_exposures: dict) -> dict:
    """Compute risk status summary from target weights and current factor exposures."""
    # For each factor, compute weighted average exposure
    # Check deviation from neutral (0.3 threshold per ADR-14)
    status = {"alerts": [], "warnings": []}

    # Collect all factors
    all_factors = set()
    for exposures in asset_exposures.values():
        all_factors.update(exposures.keys())

    for factor in all_factors:
        weighted_exposure = 0.0
        total_weight = 0.0
        for asset_id, weight in target_weights.items():
            if asset_id in asset_exposures:
                beta = asset_exposures[asset_id].get(factor, 0.0)
                weighted_exposure += weight * beta
                total_weight += abs(weight)

        if total_weight > 0:
            avg_exposure = weighted_exposure / total_weight
            if abs(avg_exposure) >= 0.3:
                status["warnings"].append(f"{factor}: {avg_exposure:.2f}")

    return status


def get_next_rebalance_date(current_date: str, rebalance_freq: str) -> str:
    """Return next rebalance date after current_date.

    monthly: last day of next month
    weekly: next Friday
    """
    from datetime import date, timedelta
    import calendar

    d = date.fromisoformat(current_date)

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
                    db_path: str = "finkit.db", rebalance_freq: str = "monthly") -> dict:
    """Generate signal by running strategy on up-to-today data.

    Uses the same subprocess runner pattern as finkit_strategy/runner.py.
    Returns: {status, target_weights, risk_status, next_rebalance_date, as_of_date}
    """
    from finkit_strategy.runner import run_strategy_in_subprocess
    import tempfile, os, sqlite3

    today = date.today().isoformat()

    # Get asset prices from DB (up to today)
    prices = {}  # asset_id -> {date: nav}
    with sqlite3.connect(db_path) as conn:
        cur = conn.execute(
            "SELECT asset_id, date, nav FROM asset_prices WHERE date <= ? ORDER BY asset_id, date",
            (today,)
        )
        for asset_id, date_val, nav in cur.fetchall():
            if asset_id not in prices:
                prices[asset_id] = {}
            prices[asset_id][date_val] = nav

    # Get asset metadata for pool
    pool = []  # [{id, asset_type, name, mgmt_fee, custody_fee, purchase_fee, redeem_rules}]
    with sqlite3.connect(db_path) as conn:
        cur = conn.execute("SELECT id, symbol, name, asset_type, mgmt_fee, custody_fee, purchase_fee, redeem_rules FROM research_assets WHERE status = 'pooled'")
        for row in cur.fetchall():
            pool.append({
                "id": row[0], "symbol": row[1], "name": row[2], "asset_type": row[3],
                "mgmt_fee": row[4] or 0, "custody_fee": row[5] or 0,
                "purchase_fee": row[6] or 0, "redeem_rules": json.loads(row[7] or "{}")
            })

    # Compute returns from prices
    returns = {}  # asset_id -> {date: return}
    for asset_id, price_dict in prices.items():
        sorted_dates = sorted(price_dict.keys())
        returns[asset_id] = {}
        for i in range(1, len(sorted_dates)):
            prev_price = price_dict[sorted_dates[i-1]]
            curr_price = price_dict[sorted_dates[i]]
            if prev_price != 0:
                returns[asset_id][sorted_dates[i]] = (curr_price - prev_price) / prev_price

    # Get factor exposures (most recent)
    factor_exposures = {}  # asset_id -> {factor_name: beta}
    try:
        with sqlite3.connect(db_path) as conn:
            cur = conn.execute(
                """SELECT ae.asset_id, f.name, ae.beta
                   FROM factor_exposures ae
                   JOIN factors f ON ae.factor_id = f.id
                   WHERE ae.as_of_date = (
                       SELECT MAX(as_of_date) FROM factor_exposures WHERE asset_id = ae.asset_id
                   )"""
            )
            for asset_id, factor_name, beta in cur.fetchall():
                if asset_id not in factor_exposures:
                    factor_exposures[asset_id] = {}
                factor_exposures[asset_id][factor_name] = beta
    except Exception:
        factor_exposures = {}

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
        "current_weights": {},
        "rebalance_dates": rebalance_dates,
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
        json.dump(data, f)
        input_path = f.name

    try:
        result = run_strategy_in_subprocess(input_path, timeout=30)

        if result["status"] != "ok":
            return {"status": "error", "error": result.get("error", "Strategy execution failed")}

        weights = result["weights"].get(today, {})

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
