from app.services.portfolio_health import compute_health


def test_concentration():
    invs = [
        {"id": "a", "current_price": 10, "quantity": 100, "asset_class": "黄金"},   # 1000
        {"id": "b", "current_price": 10, "quantity": 300, "asset_class": "A股"},    # 3000
    ]
    h = compute_health(invs, [])
    assert h["concentration"]["max_single_pct"] == 75.0
    assert h["concentration"]["top3_pct"] == 100.0


def test_allocation_by_asset_class():
    invs = [{"current_price": 10, "quantity": 100, "asset_class": "黄金"},
            {"current_price": 10, "quantity": 100, "asset_class": "A股"}]
    h = compute_health(invs, [])
    assert h["allocation"]["黄金"] == 50.0
    assert h["allocation"]["A股"] == 50.0


def test_loss_warning():
    invs = [{"id": "a", "purchase_price": 10, "current_price": 8, "quantity": 10}]  # -20%
    h = compute_health(invs, [])
    assert any(w["id"] == "a" for w in h["warnings"])
    assert h["warnings"][0]["severity"] == "high"  # <-10% high


def test_concentration_warning():
    invs = [{"id": "a", "current_price": 10, "quantity": 400, "asset_class": "黄金"},
            {"current_price": 10, "quantity": 100, "asset_class": "A股"}]  # a占80%
    h = compute_health(invs, [])
    assert any(w["type"] == "concentration" for w in h["warnings"])
