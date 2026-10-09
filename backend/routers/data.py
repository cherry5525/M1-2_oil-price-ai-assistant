import csv
import io
import json
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, Response, status
from google.cloud.firestore_v1 import Query as FSQuery

from firebase_client import db  # firebase_client.py에서 만든 Firestore 클라이언트
from schemas import DataCreate, DataResponse, DataStatistics, DataSummary, DataUpdate
from services.data_service import compute_summary, get_records, invalidate_cache, monthly_statistics

router = APIRouter(prefix="/api/data", tags=["data"])

COLLECTION = "data"


def _to_response(doc) -> DataResponse:
    d = doc.to_dict()
    return DataResponse(
        id=doc.id,
        date=d.get("date", ""),
        value=float(d.get("value", 0)),
        memo=d.get("memo") or "",
    )


# ⚠️ /summary는 반드시 /{data_id} 보다 먼저 정의해야 합니다.
#    (아니면 "summary"가 id로 해석됨)
@router.get("/summary", response_model=DataSummary)
def get_summary(
    start_date: Optional[str] = Query(None, description="시작일 (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="종료일 (YYYY-MM-DD)"),
):
    """데이터 요약: 기간, 개수, 주요 지표, 최근 추세 (AI 시스템 프롬프트에 주입되는 정보)"""
    return compute_summary(start_date, end_date)


@router.get("/statistics", response_model=DataStatistics)
def get_statistics(
    start_date: Optional[str] = Query(None, description="시작일 (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="종료일 (YYYY-MM-DD)"),
):
    """월별 통계(평균/최저/최고/전월 대비 변동률). 프론트엔드 그래프에서 사용합니다."""
    return {"monthly": monthly_statistics(start_date, end_date)}


@router.get("/export")
def export_data(
    file_format: str = Query("csv", alias="format", pattern="^(csv|json)$", description="csv 또는 json"),
    start_date: Optional[str] = Query(None, description="시작일 (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="종료일 (YYYY-MM-DD)"),
):
    """데이터 내보내기 (파일 다운로드). 컬럼: date, value, memo"""
    records = get_records(start_date, end_date)

    if file_format == "json":
        content = json.dumps(records, ensure_ascii=False, indent=2)
        media_type = "application/json"
        filename = "gimhae_gasoline.json"
    else:
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=["date", "value", "memo"])
        writer.writeheader()
        writer.writerows(records)
        content = "\ufeff" + buffer.getvalue()  # 맨 앞의 BOM: 엑셀에서 한글이 깨지지 않게 함
        media_type = "text/csv; charset=utf-8"
        filename = "gimhae_gasoline.csv"

    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("", response_model=DataResponse, status_code=status.HTTP_201_CREATED)
def create_data(body: DataCreate):
    """데이터 추가 (같은 날짜가 이미 있으면 409)"""
    exists = db.collection(COLLECTION).where("date", "==", body.date).limit(1).get()
    if exists:
        raise HTTPException(status_code=409, detail=f"{body.date} 날짜의 데이터가 이미 존재합니다.")

    _, ref = db.collection(COLLECTION).add(body.model_dump())
    invalidate_cache()
    return _to_response(ref.get())


@router.get("", response_model=List[DataResponse])
def list_data(
    start_date: Optional[str] = Query(None, description="시작일 (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="종료일 (YYYY-MM-DD)"),
    order: str = Query("asc", pattern="^(asc|desc)$", description="날짜 정렬 방향"),
    limit: int = Query(100, ge=1, le=2000, description="최대 반환 건수"),
    offset: int = Query(0, ge=0, description="건너뛸 건수"),
):
    """데이터 목록 조회 (기간 필터, 정렬, 페이지네이션)"""
    query = db.collection(COLLECTION)
    if start_date:
        query = query.where("date", ">=", start_date)
    if end_date:
        query = query.where("date", "<=", end_date)

    direction = FSQuery.DESCENDING if order == "desc" else FSQuery.ASCENDING
    query = query.order_by("date", direction=direction).offset(offset).limit(limit)

    return [_to_response(doc) for doc in query.stream()]


@router.put("/{data_id}", response_model=DataResponse)
def update_data(data_id: str, body: DataUpdate):
    """데이터 수정 (보낸 필드만 변경)"""
    ref = db.collection(COLLECTION).document(data_id)
    if not ref.get().exists:
        raise HTTPException(status_code=404, detail="해당 id의 데이터를 찾을 수 없습니다.")

    updates = body.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail="수정할 필드를 하나 이상 보내주세요.")

    # 날짜를 바꾸는 경우 다른 문서와 중복되는지 확인
    if "date" in updates:
        dup = db.collection(COLLECTION).where("date", "==", updates["date"]).get()
        if any(d.id != data_id for d in dup):
            raise HTTPException(status_code=409, detail=f"{updates['date']} 날짜의 데이터가 이미 존재합니다.")

    ref.update(updates)
    invalidate_cache()
    return _to_response(ref.get())


@router.delete("/{data_id}")
def delete_data(data_id: str):
    """데이터 삭제"""
    ref = db.collection(COLLECTION).document(data_id)
    if not ref.get().exists:
        raise HTTPException(status_code=404, detail="해당 id의 데이터를 찾을 수 없습니다.")
    ref.delete()
    invalidate_cache()
    return {"message": "삭제되었습니다.", "id": data_id}
