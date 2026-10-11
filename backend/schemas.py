import datetime as dt
import re
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

_DATE_PATTERN = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_MIN_DATE = dt.date(2000, 1, 1)
_KST = dt.timezone(dt.timedelta(hours=9))  # 한국 시간 (Windows에서도 추가 설치 없이 동작)
MAX_PRICE = 10000


def _check_date(v: str) -> str:
    """YYYY-MM-DD(월/일 두 자리) + 실제로 존재하는 날짜 + 2000-01-01 ~ 오늘(한국 시간) 범위"""
    if not _DATE_PATTERN.fullmatch(v):
        raise ValueError("date는 YYYY-MM-DD 형식이어야 합니다 (예: 2024-01-05, 월/일은 두 자리)")
    try:
        parsed = dt.datetime.strptime(v, "%Y-%m-%d").date()
    except ValueError:
        raise ValueError("존재하지 않는 날짜입니다.")
    today = dt.datetime.now(_KST).date()
    if not (_MIN_DATE <= parsed <= today):
        raise ValueError(f"date는 {_MIN_DATE.isoformat()} ~ 오늘({today.isoformat()}) 범위여야 합니다.")
    return v


# ---------------------------------------------------------------
# 데이터 CRUD
# ---------------------------------------------------------------
class DataCreate(BaseModel):
    """POST /api/data 요청 본문"""
    date: str = Field(..., description="날짜 (YYYY-MM-DD)", examples=["2024-01-15"])
    value: float = Field(..., gt=0, le=MAX_PRICE, allow_inf_nan=False,
                         description="휘발유 가격 (원/L)", examples=[1650.5])
    memo: str = Field(default="", max_length=100, description="메모", examples=["설 연휴 전"])

    @field_validator("date")
    @classmethod
    def validate_date(cls, v: str) -> str:
        return _check_date(v)


class DataUpdate(BaseModel):
    """PUT /api/data/{id} 요청 본문 (보낸 필드만 수정)

    date, value는 null을 보낼 수 없습니다. 바꾸지 않으려면 필드를 아예 빼세요.
    """
    date: Optional[str] = Field(default=None, description="날짜 (YYYY-MM-DD)")
    value: Optional[float] = Field(default=None, gt=0, le=MAX_PRICE, allow_inf_nan=False,
                                   description="휘발유 가격 (원/L)")
    memo: Optional[str] = Field(default=None, max_length=100, description="메모 (null이면 빈 메모로 저장)")

    @field_validator("date")
    @classmethod
    def validate_date(cls, v: Optional[str]) -> Optional[str]:
        return _check_date(v) if v is not None else v

    @model_validator(mode="after")
    def reject_null_required_fields(self):
        for name in ("date", "value"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name}은(는) null로 보낼 수 없습니다. 바꾸지 않으려면 필드를 빼세요.")
        return self


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


class MonthlyStat(BaseModel):
    month: str = Field(description="YYYY-MM")
    avg: float
    min: float
    max: float
    days: int = Field(description="해당 월의 데이터 일수")
    change_pct: Optional[float] = Field(default=None, description="전월 평균 대비 변동률(%)")


class DataStatistics(BaseModel):
    """GET /api/data/statistics 응답 (그래프용)"""
    monthly: List[MonthlyStat]


# ---------------------------------------------------------------
# AI 채팅 (POST /api/chat)
# ---------------------------------------------------------------
class ChatMessage(BaseModel):
    """대화 메시지 1개"""
    role: Literal["user", "assistant"]
    content: str
    tools_used: List[str] = Field(
        default_factory=list,
        description="(assistant 메시지) 이 답변을 만들 때 AI가 추가 조회에 사용한 도구",
    )


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
