"""읽기 비용(Firestore 무료 한도) 방어 테스트: 조회는 캐시에서, 쓰기는 한 건만 반영하는지 확인한다."""
import datetime as dt

from services import data_service


def seed(db, n=200):
    first = dt.date(2025, 1, 1)
    db.seed_prices([((first + dt.timedelta(days=i)).isoformat(), 1600.0 + i) for i in range(n)])


def warm_up(client, db):
    client.get("/api/data/summary")  # 캐시를 채운다 (n건을 읽음)
    db.counter["reads"] = 0          # 이 시점부터 Firestore 읽기를 다시 센다


def test_listing_is_served_from_cache(client, db):
    """limit=2000으로 반복 호출해도 Firestore를 읽지 않아야 한다. (예전에는 호출마다 최대 2,000건을 읽었다)"""
    seed(db)
    warm_up(client, db)
    for _ in range(5):
        r = client.get("/api/data?limit=2000")
        assert r.status_code == 200 and len(r.json()) == 200
    assert db.counter["reads"] == 0


def test_summary_statistics_and_export_do_not_read_firestore(client, db):
    seed(db)
    warm_up(client, db)
    for url in ["/api/data/summary", "/api/data/statistics", "/api/data/export?format=csv", "/api/data/export?format=json"]:
        assert client.get(url).status_code == 200
    assert db.counter["reads"] == 0


def test_writes_update_the_cache_without_rereading_everything(client, db):
    seed(db, 200)
    warm_up(client, db)

    new = client.post("/api/data", json={"date": "2025-12-01", "value": 1700}).json()
    assert client.get("/api/data/summary").json()["count"] == 201
    client.put(f"/api/data/{new['id']}", json={"value": 1750})
    assert client.get("/api/data/summary").json()["metrics"]["latest"] == 1750.0
    client.delete(f"/api/data/{new['id']}")
    assert client.get("/api/data/summary").json()["count"] == 200

    assert db.counter["reads"] < 20  # 전체를 다시 읽었다면 200건 이상이어야 한다


def test_changing_a_date_reorders_the_cached_list(client, db):
    db.seed_prices([("2025-01-01", 1600.0), ("2025-01-02", 1610.0), ("2025-01-03", 1620.0)])
    client.get("/api/data/summary")
    first_id = next(iter(db.collections["data"]))
    client.put(f"/api/data/{first_id}", json={"date": "2025-02-01"})
    assert [d["date"] for d in client.get("/api/data").json()] == ["2025-01-02", "2025-01-03", "2025-02-01"]


def test_a_corrupted_document_can_be_repaired_with_put(client, db):
    db.seed_prices([("2025-01-01", 1600.0)])
    db.collections["data"]["bad"] = {"date": None, "value": None, "memo": ""}
    assert client.get("/api/data/summary").json()["count"] == 1  # 손상 문서는 제외

    r = client.put("/api/data/bad", json={"date": "2025-01-02", "value": 1700})
    assert r.status_code == 200
    assert client.get("/api/data/summary").json()["count"] == 2  # 고치면 다시 포함


def test_cache_is_reloaded_after_ttl_to_pick_up_changes_made_outside_the_api(client, db, monkeypatch):
    seed(db, 50)
    warm_up(client, db)
    db.seed_prices([("2026-01-01", 1900.0)])  # 콘솔/스크립트로 직접 추가한 데이터
    assert client.get("/api/data/summary").json()["count"] == 50  # 아직 캐시

    real_time = data_service.time.time()
    monkeypatch.setattr(data_service.time, "time", lambda: real_time + data_service.CACHE_TTL_SECONDS + 1)
    assert client.get("/api/data/summary").json()["count"] == 51  # TTL이 지나 다시 읽음
    assert db.counter["reads"] == 51


def test_ttl_is_long_enough_to_protect_the_free_quota():
    """하루 5만 건 한도에서 전체 재조회를 몇 번까지 견디는지 (1,368건 기준)"""
    reloads_per_day = 24 * 60 * 60 / data_service.CACHE_TTL_SECONDS
    assert reloads_per_day * 1368 < 50_000 / 4  # 한도의 1/4 이하만 사용
