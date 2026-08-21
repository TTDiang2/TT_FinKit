"""导入转账方向默认逻辑测试（纯函数，不依赖 DB）。"""
from app.routers.transactions import _default_transfer_pair


def test_from_salary_account_goes_to_consumer():
    accounts = {"工资账户": "a", "消费账户": "b"}
    src, dst = _default_transfer_pair(accounts, "工资账户")
    assert (src, dst) == ("工资账户", "消费账户")


def test_from_consumer_account_swaps_to_salary_source():
    accounts = {"工资账户": "a", "消费账户": "b"}
    src, dst = _default_transfer_pair(accounts, "消费账户")
    assert (src, dst) == ("工资账户", "消费账户")


def test_from_other_account_picks_first_other():
    accounts = {"闲置账户": "a", "消费账户": "b"}
    src, dst = _default_transfer_pair(accounts, "闲置账户")
    assert (src, dst) == ("闲置账户", "消费账户")


def test_single_account_returns_empty_dest():
    accounts = {"工资账户": "a"}
    src, dst = _default_transfer_pair(accounts, "工资账户")
    assert (src, dst) == ("工资账户", "")


def test_salary_prefers_consumer_dest():
    accounts = {"工资账户": "a", "闲置账户": "b", "消费账户": "c"}
    src, dst = _default_transfer_pair(accounts, "工资账户")
    assert (src, dst) == ("工资账户", "消费账户")
