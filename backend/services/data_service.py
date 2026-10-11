"""가격 데이터 읽기(캐시) + 요약/월별 통계 계산 + 내보내기용 레코드.

Firestore는 읽은 문서 수만큼 무료 한도(하루 5만 건)가 줄어듭니다.
그래서 전체 데이터를 5분 동안 메모리에 보관하고, 데이터가 바뀌면(추가/수정/삭제) 즉시 비웁니다.
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
CACHE_TTL_SECONDS = 300

logger = logging.getLogger(__name__)
_DATE_PATTERN = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")

_lock = Lock()
_cache = {"records": None, "rows": None, "loaded_at": 0.0}

Row = Tuple[str, float]  # (날짜, 가격)


def invalidate_cache() -> None:
    """데이터가 바뀌었을 때 호출: 다음 조회 때 Firestore에서 새로 읽는다."""
    with _lock:
        _cache["records"] = None
        _cache["rows"] = None


def _load_all() -> Tuple[List[dict], List[Row]]:
    """(레코드 목록, (날짜, 가격) 목록)을 반환. 캐시가 신선하면 Firestore를 읽지 않는다."""
    with _lock:
        fresh = _cache["rows"] is not None and (time.time() - _cache["loaded_at"]) < CACHE_TTL_SECONDS
        if fresh:
            return _cache["records"], _cache["rows"]

        records: List[dict] = []
        for doc in db.collection(COLLECTION).order_by("date").stream():
            d = doc.to_dict()
            date_str, raw = d.get("date"), d.get("value")
            valid = (
                isinstance(date_str, str) and _DATE_PATTERN.fullmatch(date_str)
                and isinstance(raw, (int, float)) and not isinstance(raw, bool)
                and math.isfinite(raw)
            )
            if not valid:
                # 손상된 문서 1개 때문에 요약/채팅/그래프 전체가 멈추지 않도록 건너뛴다
                logger.warning("손상된 데이터 문서를 건너뜁니다: id=%s date=%r value=%r", doc.id, date_str, raw)
                continue
            records.append({"date": date_str, "value": float(raw), "memo": d.get("memo") or ""})
        rows = [(r["date"], r["value"]) for r in records]

        _cache["records"] = records
        _cache["rows"] = rows
        _cache["loaded_at"] = time.time()
        return records, rows


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
    return [dict(r) for r in records if _in_range(r["date"], start_date, end_date)]


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
