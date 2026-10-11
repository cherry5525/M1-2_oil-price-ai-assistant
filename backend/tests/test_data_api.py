"""데이터 API(/api/data/...) 테스트."""
import csv
import io


def seed_three(db):
    db.seed_prices([("2025-01-01", 1600.0, "설 연휴"), ("2025-01-02", 1610.0), ("2025-02-01", 1650.0)])


def first_id(db):
    return next(iter(db.collections["data"]))


# ---- 피드백 1번: PUT null ----
def test_put_null_is_rejected_and_data_is_untouched(client, db):
    seed_three(db)
    doc_id = first_id(db)
    before = dict(db.collections["data"][doc_id])
    r = client.put(f"/api/data/{doc_id}", json={"value": None, "date": None})
    assert r.status_code == 422
    assert db.collections["data"][doc_id] == before  # 아무것도 바뀌지 않음
    assert client.get("/api/data/summary").status_code == 200  # 서비스가 살아 있음


def test_put_updates_only_sent_fields(client, db):
    seed_three(db)
    doc_id = first_id(db)
    r = client.put(f"/api/data/{doc_id}", json={"value": 1700})
    assert r.status_code == 200 and r.json()["value"] == 1700.0 and r.json()["date"] == "2025-01-01"


def test_put_null_memo_becomes_empty_string(client, db):
    seed_three(db)
    r = client.put(f"/api/data/{first_id(db)}", json={"memo": None})
    assert r.status_code == 200 and r.json()["memo"] == ""


def test_put_error_cases(client, db):
    seed_three(db)
    doc_id = first_id(db)
    assert client.put(f"/api/data/{doc_id}", json={}).status_code == 400
    assert client.put(f"/api/data/{doc_id}", json={"date": "2025-1-1"}).status_code == 422
    assert client.put("/api/data/없는id", json={"value": 1700}).status_code == 404
    assert client.put(f"/api/data/{doc_id}", json={"date": "2025-01-02"}).status_code == 409  # 다른 문서와 날짜 중복


# ---- 피드백 2번: 날짜 검증이 API까지 이어지는지 ----
def test_post_validation_and_duplicates(client, db):
    seed_three(db)
    assert client.post("/api/data", json={"date": "2025-1-5", "value": 1700}).status_code == 422
    assert client.post("/api/data", json={"date": "2030-01-01", "value": 1700}).status_code == 422
    assert client.post("/api/data", json={"date": "2025-01-01", "value": 1700}).status_code == 409
    assert client.post("/api/data", json={"date": "2025-03-01", "value": 0}).status_code == 422
    r = client.post("/api/data", json={"date": "2025-03-01", "value": 1700, "memo": "ok"})
    assert r.status_code == 201 and r.json()["date"] == "2025-03-01"


# ---- 피드백 5번: 추가/삭제 직후 요약이 바로 갱신되는지 ----
def test_summary_updates_immediately_after_post_and_delete(client, db):
    seed_three(db)
    assert client.get("/api/data/summary").json()["count"] == 3
    new = client.post("/api/data", json={"date": "2025-03-01", "value": 1700}).json()
    summary = client.get("/api/data/summary").json()
    assert summary["count"] == 4 and summary["period"].endswith("2025-03-01")
    client.delete(f"/api/data/{new['id']}")
    assert client.get("/api/data/summary").json()["count"] == 3


def test_summary_updates_after_put(client, db):
    seed_three(db)
    client.get("/api/data/summary")  # 캐시를 채워 둔다
    client.put(f"/api/data/{first_id(db)}", json={"value": 1900})
    assert client.get("/api/data/summary").json()["metrics"]["max"] == 1900.0


def test_list_survives_corrupted_documents(client, db):
    seed_three(db)
    db.collections["data"]["bad"] = {"date": None, "value": None, "memo": None}
    assert client.get("/api/data").status_code == 200


def test_list_filters_order_and_pagination(client, db):
    seed_three(db)
    dates = [d["date"] for d in client.get("/api/data?order=desc").json()]
    assert dates == ["2025-02-01", "2025-01-02", "2025-01-01"]
    assert len(client.get("/api/data?limit=2&offset=1").json()) == 2
    assert len(client.get("/api/data?start_date=2025-02-01").json()) == 1


# ---- 통계 / 내보내기 (보너스) ----
def test_statistics_endpoint(client, db):
    seed_three(db)
    monthly = client.get("/api/data/statistics").json()["monthly"]
    assert [m["month"] for m in monthly] == ["2025-01", "2025-02"]


def test_export_csv_has_bom_and_korean_memo(client, db):
    seed_three(db)
    r = client.get("/api/data/export?format=csv")
    assert r.status_code == 200
    assert "attachment" in r.headers["content-disposition"]
    assert r.content[:3] == b"\xef\xbb\xbf"  # 엑셀에서 한글이 깨지지 않게 하는 BOM
    rows = list(csv.DictReader(io.StringIO(r.content.decode("utf-8-sig"))))
    assert len(rows) == 3 and rows[0]["memo"] == "설 연휴"


def test_export_json_and_filters(client, db):
    seed_three(db)
    assert len(client.get("/api/data/export?format=json").json()) == 3
    assert len(client.get("/api/data/export?format=json&start_date=2025-02-01").json()) == 1
    assert client.get("/api/data/export?format=xml").status_code == 422
