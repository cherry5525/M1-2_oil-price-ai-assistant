"""가격 데이터 읽기(캐시) + 요약/월별 통계 계산 + 내보내기용 레코드.

Firestore는 읽은 문서 수만큼 무료 한도(하루 5만 건)가 줄어듭니다. 그래서
  - 전체 데이터(1,368건)를 서버 메모리에 한 번 읽어 두고, 조회(요약/통계/목록/내보내기/AI 도구)는 모두 여기서 처리합니다.
  - 데이터를 추가·수정·삭제하면 Firestore에 쓰는 동시에 메모리 캐시도 '그 한 건만' 바로 고칩니다. (전체를 다시 읽지 않음)
  - Firestore를 직접 고친 경우(콘솔, 적재 스크립트)를 반영하기 위해 6시간마다 한 번 전체를 다시 읽습니다.
"""
import logging
import math
import re
import time
from collections import defaultdict
from threading import Lock
from typing import Dict, List, Optional, Tuple

from firebase_client import db  # 변수 이름이 db가 아니면 다른 파일과 똑같이 맞춰주세요

COLLECTION = "data"
CACHE_TTL_SECONDS = 6 * 60 * 60

logger = logging.getLogger(__name__)
_DATE_PATTERN = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")

_lock = Lock()
_cache = {"records": None, "rows": None, "loaded_at": 0.0}

Row = Tuple[str, float]  # (날짜, 가격)


def _make_record(doc_id: str, d: dict) -> Optional[dict]:
    """Firestore 문서(dict)를 캐시용 레코드로 바꾼다. 손상된 문서면 None"""
    date_str, raw = d.get("date"), d.get("value")
    valid = (
        isinstance(date_str, str) and _DATE_PATTERN.fullmatch(date_str)
        and isinstance(raw, (int, float)) and not isinstance(raw, bool)
        and math.isfinite(raw)
    )
    if not valid:
        # 손상된 문서 1개 때문에 요약/채팅/그래프 전체가 멈추지 않도록 건너뛴다
        logger.warning("손상된 데이터 문서를 건너뜁니다: id=%s date=%r value=%r", doc_id, date_str, raw)
        return None
    return {"id": doc_id, "date": date_str, "value": float(raw), "memo": d.get("memo") or ""}


def _store(records: List[dict]) -> None:
    """레코드를 날짜순으로 정렬해 캐시에 저장한다. (호출하는 쪽이 _lock을 잡고 있어야 함)
    기존 리스트를 고치지 않고 새 리스트로 바꿔 끼우므로, 읽는 중인 다른 요청에는 영향이 없다."""
    records = sorted(records, key=lambda r: (r["date"], r["id"]))
    _cache["records"] = records
    _cache["rows"] = [(r["date"], r["value"]) for r in records]


def invalidate_cache() -> None:
    """캐시를 비운다: 다음 조회 때 Firestore에서 전체를 새로 읽는다."""
    with _lock:
        _cache["records"] = None
        _cache["rows"] = None


def _load_all() -> Tuple[List[dict], List[Row]]:
    """(레코드 목록, (날짜, 가격) 목록)을 반환. 캐시가 신선하면 Firestore를 읽지 않는다."""
    with _lock:
        fresh = _cache["rows"] is not None and (time.time() - _cache["loaded_at"]) < CACHE_TTL_SECONDS
        if fresh:
            return _cache["records"], _cache["rows"]

        records = []
        for doc in db.collection(COLLECTION).order_by("date").stream():
            record = _make_record(doc.id, doc.to_dict())
            if record:
                records.append(record)
        _store(records)
        _cache["loaded_at"] = time.time()
        return _cache["records"], _cache["rows"]


def cache_upsert_doc(doc_id: str, data: dict) -> None:
    """추가/수정된 문서 1건을 캐시에 반영한다. (캐시가 아직 없으면 아무것도 하지 않음: 첫 조회 때 읽어 옴)
    문서가 손상된 상태이면 캐시에서 제외한다."""
    with _lock:
        if _cache["records"] is None:
            return
        others = [r for r in _cache["records"] if r["id"] != doc_id]
        record = _make_record(doc_id, data)
        _store(others + ([record] if record else []))


def cache_remove(doc_id: str) -> None:
    """삭제된 문서 1건을 캐시에서 뺀다."""
    with _lock:
        if _cache["records"] is None:
            return
        _store([r for r in _cache["records"] if r["id"] != doc_id])


def _in_range(date_str: str, start_date: Optional[str], end_date: Optional[str]) -> bool:
    if start_date and date_str < start_date:
        return False
    if end_date and date_str > end_date:
        return False
    return True


def get_rows(start_date: Optional[str] = None, end_date: Optional[str] = None) -> List[Row]:
    """기간 내 (날짜, 가격) 목록을 날짜순으로 반환"""
    _, rows = _load_all()
    return [r for r in rows if _in_range(r[0], start_date, end_date)]


def get_records(start_date: Optional[str] = None, end_date: Optional[str] = None) -> List[dict]:
    """기간 내 {date, value, memo} 목록을 날짜순으로 반환 (내보내기용)"""
    records, _ = _load_all()
    return [{"date": r["date"], "value": r["value"], "memo": r["memo"]}
            for r in records if _in_range(r["date"], start_date, end_date)]


def list_records(start_date: Optional[str] = None, end_date: Optional[str] = None,
                 order: str = "asc", limit: int = 100, offset: int = 0) -> List[dict]:
    """기간 내 {id, date, value, memo} 목록 (정렬, 페이지 이동 지원). Firestore를 읽지 않고 캐시에서 만든다."""
    records, _ = _load_all()
    items = [r for r in records if _in_range(r["date"], start_date, end_date)]
    if order == "desc":
        items = items[::-1]
    return [dict(r) for r in items[offset:offset + limit]]


def _mean(values: List[float]) -> float:
    return sum(values) / len(values)


def _trend(values: List[float]) -> Tuple[str, Optional[float]]:
    """최근 30일 평균 vs 직전 30일 평균으로 추세 판단. (문구, 최근30일평균) 반환"""
    n = len(values)
    if n >= 60:
        recent, prev = values[-30:], values[-60:-30]
        recent_avg, prev_avg = _mean(recent), _mean(prev)
        pct = (recent_avg - prev_avg) / prev_avg * 100
        label = "상승" if pct >= 0.5 else "하락" if pct <= -0.5 else "유지"
        return f"{label} (최근 30일 평균 {recent_avg:,.1f}원/L, 직전 30일 대비 {pct:+.1f}%)", round(recent_avg, 2)
    if n >= 2:
        pct = (values[-1] - values[0]) / values[0] * 100
        label = "상승" if pct >= 0.5 else "하락" if pct <= -0.5 else "유지"
        return f"{label} (기간 처음 대비 {pct:+.1f}%, 데이터가 적어 단순 비교)", None
    return "판단 불가 (데이터 부족)", None


def compute_summary(start_date: Optional[str] = None, end_date: Optional[str] = None) -> dict:
    """요약 정보: 기간, 개수, 주요 지표, 최근 추세"""
    rows = get_rows(start_date, end_date)
    if not rows:
        return {"period": None, "count": 0, "metrics": None, "trend": "데이터 없음"}

    values = [v for _, v in rows]
    n = len(values)
    avg = _mean(values)
    std = (sum((v - avg) ** 2 for v in values) / n) ** 0.5
    low = min(rows, key=lambda r: r[1])
    high = max(rows, key=lambda r: r[1])
    last = rows[-1]
    trend_text, recent_avg = _trend(values)

    return {
        "period": f"{rows[0][0]} ~ {rows[-1][0]}",
        "count": n,
        "metrics": {
            "average": round(avg, 2),
            "max": high[1],
            "max_date": high[0],
            "min": low[1],
            "min_date": low[0],
            "latest": last[1],
            "latest_date": last[0],
            "std_dev": round(std, 2),
            "recent_30d_avg": recent_avg,
        },
        "trend": trend_text,
    }


def monthly_statistics(start_date: Optional[str] = None, end_date: Optional[str] = None) -> List[Dict]:
    """월별 평균/최저/최고/일수와 전월 대비 변동률(%) (그래프용)"""
    by_month = defaultdict(list)
    for d, v in get_rows(start_date, end_date):
        by_month[d[:7]].append(v)  # "2025-03-15" -> "2025-03"

    result = []
    prev_avg = None
    for month in sorted(by_month):
        values = by_month[month]
        avg = _mean(values)
        change = None if prev_avg is None else round((avg - prev_avg) / prev_avg * 100, 2)
        result.append({
            "month": month,
            "avg": round(avg, 2),
            "min": min(values),
            "max": max(values),
            "days": len(values),
            "change_pct": change,
        })
        prev_avg = avg
    return result
