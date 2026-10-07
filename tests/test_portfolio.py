from datetime import date, datetime, timezone

import pytest

from uzse_agent.portfolio import (
    NegativePositionError,
    Position,
    Transaction,
    compute_position,
    today_local,
)


def buy(qty, price, day="2026-10-01", fee=0.0, tx_id=None):
    return Transaction(tx_id, "buy", qty, price, fee, day)


def sell(qty, price, day="2026-10-02", fee=0.0, tx_id=None):
    return Transaction(tx_id, "sell", qty, price, fee, day)


def test_empty():
    assert compute_position([]) == Position(quantity=0, avg_cost=None, realized_pnl=0.0)


def test_weighted_average_with_fee():
    pos = compute_position([buy(10, 6000, fee=100), buy(20, 5000, day="2026-10-03")])
    assert pos.quantity == 30
    assert pos.avg_cost == pytest.approx(160100 / 30)
    assert pos.realized_pnl == 0


def test_partial_sell_keeps_average_and_realizes():
    pos = compute_position([buy(10, 100), sell(4, 150, fee=5)])
    assert pos.quantity == 6
    assert pos.avg_cost == pytest.approx(100)
    assert pos.realized_pnl == pytest.approx(4 * 50 - 5)


def test_full_sell_then_rebuy_starts_fresh_average():
    pos = compute_position([buy(10, 100), sell(10, 120), buy(5, 200, day="2026-10-05")])
    assert pos.quantity == 5
    assert pos.avg_cost == pytest.approx(200)
    assert pos.realized_pnl == pytest.approx(200)


def test_full_sell_gives_no_average():
    pos = compute_position([buy(10, 100), sell(10, 90)])
    assert pos.quantity == 0
    assert pos.avg_cost is None
    assert pos.realized_pnl == pytest.approx(-100)


def test_oversell_raises():
    with pytest.raises(NegativePositionError) as info:
        compute_position([buy(5, 100), sell(6, 100)])
    assert info.value.available == 5
    assert "2026-10-02" in str(info.value)


def test_backdated_sell_before_buy_raises():
    with pytest.raises(NegativePositionError) as info:
        compute_position([buy(10, 100, day="2026-10-05"), sell(5, 100, day="2026-10-01")])
    assert info.value.available == 0


def test_same_day_ordered_by_id_and_unsaved_last():
    # bir kunda: avval xarid (id=1), keyin sotuv (id=None — hali saqlanmagan)
    pos = compute_position([sell(5, 100, day="2026-10-01"), buy(5, 100, day="2026-10-01", tx_id=1)])
    assert pos.quantity == 0


def test_unrealized_pnl():
    pos = compute_position([buy(10, 100)])
    assert pos.unrealized_pnl(120) == pytest.approx(200)
    assert compute_position([]).unrealized_pnl(120) is None


def test_unknown_side_raises():
    with pytest.raises(ValueError):
        compute_position([Transaction(None, "gift", 1, 1.0, 0.0, "2026-10-01")])


def test_today_local_uses_tashkent_date():
    # UTC 20:30 = Toshkentda ertasi kuni 01:30
    assert today_local(datetime(2026, 10, 6, 20, 30, tzinfo=timezone.utc)) == date(2026, 10, 7)
