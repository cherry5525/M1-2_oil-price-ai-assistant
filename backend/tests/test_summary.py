"""요약/통계 계산(services/data_service.py) 테스트."""
import datetime as dt

from services import data_service


def daily(start, values):
    """start부터 하루 간격으로 (날짜, 가격) 목록을 만든다."""
    first = dt.date.fromisoformat(start)
    return [((first + dt.timedelta(days=i)).isoformat(), v) for i, v in enumerate(values)]


def test_summary_basic_metrics(db):
    db.seed_prices(daily("2025-01-01", [1600, 1700, 1500, 1650, 1550]))
    s = data_service.compute_summary()
    assert s["count"] == 5
    assert s["period"] == "2025-01-01 ~ 2025-01-05"
    m = s["metrics"]
    assert m["average"] == 1600.0
    assert (m["max"], m["max_date"]) == (1700.0, "2025-01-02")
    assert (m["min"], m["min_date"]) == (1500.0, "2025-01-03")
    assert (m["latest"], m["latest_date"]) == (1550.0, "2025-01-05")


def test_summary_respects_date_range(db):
    db.seed_prices(daily("2025-01-01", [1600, 1700, 1500, 1650, 1550]))
    s = data_service.compute_summary("2025-01-02", "2025-01-03")
    assert s["count"] == 2 and s["metrics"]["average"] == 1600.0


def test_summary_empty(db):
    s = data_service.compute_summary()
    assert s["count"] == 0 and s["metrics"] is None


def test_trend_up(db):
    db.seed_prices(daily("2025-01-01", [1600] * 30 + [1700] * 30))
    assert data_service.compute_summary()["trend"].startswith("상승")


def test_trend_down(db):
    db.seed_prices(daily("2025-01-01", [1700] * 30 + [1600] * 30))
    assert data_service.compute_summary()["trend"].startswith("하락")


def test_trend_flat_within_threshold(db):
    # 0.1% 차이는 "유지"
    db.seed_prices(daily("2025-01-01", [1700] * 30 + [1701.7] * 30))
    assert data_service.compute_summary()["trend"].startswith("유지")


def test_trend_with_few_rows_does_not_crash(db):
    db.seed_prices(daily("2025-01-01", [1600]))
    assert "판단 불가" in data_service.compute_summary()["trend"]


def test_corrupted_documents_are_skipped(db):
    """피드백 1번 재현: 값이 null인 문서가 있어도 요약 전체가 죽지 않아야 한다."""
    db.seed_prices(daily("2025-01-01", [1600, 1700]))
    db.collections["data"].update({
        "bad1": {"date": None, "value": None, "memo": ""},
        "bad2": {"date": "2025-1-5", "value": 1620.0, "memo": ""},   # 형식이 틀린 날짜
        "bad3": {"date": "2025-01-03", "value": "abc", "memo": ""},  # 숫자가 아닌 가격
        "bad4": {"date": "2025-01-04", "value": float("nan"), "memo": ""},
    })
    s = data_service.compute_summary()
    assert s["count"] == 2
    assert len(data_service.monthly_statistics()) == 1


def test_monthly_statistics_and_change_pct(db):
    db.seed_prices([("2025-01-10", 1600), ("2025-01-20", 1700), ("2025-02-10", 1650)])
    jan, feb = data_service.monthly_statistics()
    assert (jan["month"], jan["avg"], jan["min"], jan["max"], jan["days"]) == ("2025-01", 1650.0, 1600, 1700, 2)
    assert jan["change_pct"] is None
    assert (feb["month"], feb["avg"], feb["change_pct"]) == ("2025-02", 1650.0, 0.0)


def test_cache_is_used_until_invalidated(db):
    db.seed_prices([("2025-01-01", 1600)])
    assert data_service.compute_summary()["count"] == 1
    db.seed_prices([("2025-01-02", 1700)])              # DB에 직접 추가 (캐시를 거치지 않음)
    assert data_service.compute_summary()["count"] == 1  # 캐시 때문에 아직 1건
    data_service.invalidate_cache()
    assert data_service.compute_summary()["count"] == 2
