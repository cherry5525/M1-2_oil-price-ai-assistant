from typing import List

from fastapi import APIRouter, HTTPException, Query, status

from schemas import ConversationCreate, ConversationDetail, ConversationSummary
from services import conversation_service

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


@router.post("", response_model=ConversationDetail, status_code=status.HTTP_201_CREATED)
def create_conversation(body: ConversationCreate):
    """대화 저장 (제목을 안 보내면 첫 질문으로 자동 생성)"""
    messages = [m.model_dump(exclude_defaults=True) for m in body.messages]  # 빈 tools_used는 저장하지 않음
    return conversation_service.create_conversation(messages, body.title)


@router.get("", response_model=List[ConversationSummary])
def list_conversations(limit: int = Query(50, ge=1, le=200, description="최대 반환 건수")):
    """대화 목록 (최근 갱신순). 메시지 본문은 포함하지 않고 message_count만 포함합니다."""
    return conversation_service.list_conversations(limit)


@router.get("/{conversation_id}", response_model=ConversationDetail)
def get_conversation(conversation_id: str):
    """특정 대화의 전체 메시지 조회 (대화 불러오기용)"""
    conv = conversation_service.get_conversation(conversation_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="해당 id의 대화를 찾을 수 없습니다.")
    return conv


@router.delete("/{conversation_id}")
def delete_conversation(conversation_id: str):
    """대화 삭제"""
    if not conversation_service.delete_conversation(conversation_id):
        raise HTTPException(status_code=404, detail="해당 id의 대화를 찾을 수 없습니다.")
    return {"message": "삭제되었습니다.", "id": conversation_id}
