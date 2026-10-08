from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


def _check_date(v: str) -> str:
    """YYYY-MM-DD 형식인지 검증"""
    try:
        datetime.strptime(v, "%Y-%m-%d")
    except ValueError:
        raise ValueError("date는 YYYY-MM-DD 형식이어야 합니다 (예: 2024-01-15)")
    return v


# ---------------------------------------------------------------
# 데이터 CRUD
# ---------------------------------------------------------------
class DataCreate(BaseModel):
    """POST /api/data 요청 본문"""
    date: str = Field(..., description="날짜 (YYYY-MM-DD)", examples=["2024-01-15"])
    value: float = Field(..., gt=0, description="휘발유 가격 (원/L)", examples=[1650.5])
    memo: Optional[str] = Field(default="", description="메모", examples=["설 연휴 전"])

    @field_validator("date")
    @classmethod
    def validate_date(cls, v: str) -> str:
        return _check_date(v)


class DataUpdate(BaseModel):
    """PUT /api/data/{id} 요청 본문 (보낸 필드만 수정)"""
    date: Optional[str] = Field(default=None, description="날짜 (YYYY-MM-DD)")
    value: Optional[float] = Field(default=None, gt=0, description="휘발유 가격 (원/L)")
    memo: Optional[str] = Field(default=None, description="메모")

    @field_validator("date")
    @classmethod
    def validate_date(cls, v: Optional[str]) -> Optional[str]:
        return _check_date(v) if v is not None else v


class DataResponse(BaseModel):
    """데이터 1건 응답"""
    id: str
    date: str
    value: float
    memo: Optional[str] = ""


# ---------------------------------------------------------------
# 데이터 요약 (GET /api/data/summary)
# ---------------------------------------------------------------
class SummaryMetrics(BaseModel):
    average: float
    max: float
    max_date: str
    min: float
    min_date: str
    latest: float
    latest_date: str
    std_dev: float = Field(description="표준편차 (가격이 얼마나 들쭉날쭉한지)")
    recent_30d_avg: Optional[float] = Field(default=None, description="최근 30일 평균")


class DataSummary(BaseModel):
    period: Optional[str] = None
    count: int
    metrics: Optional[SummaryMetrics] = None
    trend: str


# ---------------------------------------------------------------
# AI 채팅 (POST /api/chat)
# ---------------------------------------------------------------
class ChatMessage(BaseModel):
    """대화 메시지 1개"""
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=1000, description="사용자 질문",
                         examples=["2025년 평균 휘발유 가격이 얼마야?"])
    conversation_id: Optional[str] = Field(
        default=None,
        description="이어갈 대화 id. 새 대화로 시작하려면 이 줄을 아예 지우세요.",
    )


class ChatResponse(BaseModel):
    reply: str
    conversation_id: str = Field(description="자동 저장된 대화 id (다음 질문에 넣으면 대화가 이어집니다)")
    tools_used: List[str] = Field(default_factory=list, description="AI가 추가 조회에 사용한 도구")


# ---------------------------------------------------------------
# 대화 기록 (/api/conversations)
# ---------------------------------------------------------------
class ConversationCreate(BaseModel):
    title: Optional[str] = Field(default=None, max_length=100, description="생략하면 첫 질문으로 자동 생성")
    messages: List[ChatMessage] = Field(..., min_length=1)


class ConversationSummary(BaseModel):
    """목록용 (메시지 본문 없음)"""
    id: str
    title: str
    created_at: str
    updated_at: str
    message_count: int


class ConversationDetail(BaseModel):
    """상세용 (전체 메시지 포함)"""
    id: str
    title: str
    created_at: str
    updated_at: str
    messages: List[ChatMessage]
