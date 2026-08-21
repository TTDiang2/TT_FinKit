from app.services.portfolio_health import compute_health


def test_floating_pnl():
    invs = [
        {"id": "a", "name": "A", "purchase_price": 10, "current_price": 8, "quantity": 100},   # cost 1000, mv 800
        {"id": "b", "name": "B", "purchase_price": 10, "current_price": 12, "quantity": 100},  # cost 1000, mv 1200
    ]
    h = compute_health(invs, [])
    assert h["total_cost"] == 2000
    assert h["total_market_value"] == 2000
    assert h["floating_pnl"] == 0.0
    assert h["floating_pnl_pct"] == 0.0


def test_loss_warning_includes_name_and_prices():
    invs = [{"id": "a", "name": "黄金联接", "purchase_price": 10, "current_price": 8, "quantity": 10}]
    h = compute_health(invs, [])
    w = next(w for w in h["warnings"] if w["type"] == "loss")
    assert w["severity"] == "high"  # -20% <= -10%
    assert "黄金联接" in w["message"]
    assert "8" in w["message"] and "10" in w["message"]


def test_loss_medium_band():
    invs = [{"id": "a", "name": "A", "purchase_price": 10, "current_price": 9.6, "quantity": 10}]  # -4%: below threshold
    h = compute_health(invs, [])
    assert not h["warnings"]
    invs2 = [{"id": "a", "name": "A", "purchase_price": 10, "current_price": 9.4, "quantity": 10}]  # -6%: medium
    h2 = compute_health(invs2, [])
    assert h2["warnings"] and h2["warnings"][0]["severity"] == "medium"


def test_closed_positions_excluded():
    invs = [
        {"id": "a", "name": "A", "purchase_price": 10, "current_price": 0, "quantity": 0, "sell_date": "2026-01-01"},
        {"id": "b", "name": "B", "purchase_price": 10, "current_price": 11, "quantity": 100},
    ]
    h = compute_health(invs, [])
    # closed row must not fire a -100% warning nor count into totals
    assert not any(w["id"] == "a" for w in h["warnings"])
    assert h["total_cost"] == 1000
    assert h["total_market_value"] == 1100


def test_zero_price_excluded_from_loss():
    # current_price=0 (never refreshed) must NOT produce a -100% loss warning
    invs = [{"id": "a", "name": "A", "purchase_price": 10, "current_price": 0, "quantity": 100}]
    h = compute_health(invs, [])
    assert not any(w["type"] == "loss" for w in h["warnings"])


def test_portfolio_level_loss_warning():
    invs = [
        {"id": "a", "name": "A", "purchase_price": 10, "current_price": 8, "quantity": 100},    # -200
        {"id": "b", "name": "B", "purchase_price": 10, "current_price": 8.5, "quantity": 100},  # -150
    ]
    h = compute_health(invs, [])
    # total: cost 2000, mv 1650 → -17.5% portfolio-level warning
    assert any(w["type"] == "portfolio_loss" for w in h["warnings"])
    assert h["floating_pnl_pct"] == -17.5