"""가격 데이터 읽기(캐시) + 요약 통계 계산.

Firestore는 읽은 문서 수만큼 무료 한도(하루 5만 건)가 줄어듭니다.
그래서 전체 데이터를 5분 동안 메모리에 보관하고, 데이터가 바뀌면(추가/수정/삭제) 즉시 비웁니다.
"""
import time
from threading import Lock
from typing import List, Optional, Tuple

from firebase_client import db  # 변수 이름이 db가 아니면 다른 파일과 똑같이 맞춰주세요

COLLECTION = "data"
CACHE_TTL_SECONDS = 300

_lock = Lock()
_cache = {"rows": None, "loaded_at": 0.0}

Row = Tuple[str, float]  # (날짜, 가격)


def invalidate_cache() -> None:
    """데이터가 바뀌었을 때 호출: 다음 조회 때 Firestore에서 새로 읽는다."""
    with _lock:
        _cache["rows"] = None


def _load_all() -> List[Row]:
    with _lock:
        fresh = _cache["rows"] is not None and (time.time() - _cache["loaded_at"]) < CACHE_TTL_SECONDS
        if fresh:
            return _cache["rows"]

        rows: List[Row] = []
        for doc in db.collection(COLLECTION).order_by("date").stream():
            d = doc.to_dict()
            if "date" in d and "value" in d:
                rows.append((d["date"], float(d["value"])))

        _cache["rows"] = rows
        _cache["loaded_at"] = time.time()
        return rows


def get_rows(start_date: Optional[str] = None, end_date: Optional[str] = None) -> List[Row]:
    """기간 내 (날짜, 가격) 목록을 날짜순으로 반환"""
    rows = _load_all()
    if start_date:
        rows = [r for r in rows if r[0] >= start_date]
    if end_date:
        rows = [r for r in rows if r[0] <= end_date]
    return rows


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
