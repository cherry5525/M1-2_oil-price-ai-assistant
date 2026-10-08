from fastapi import APIRouter, HTTPException
from openai import OpenAIError

from schemas import ChatRequest, ChatResponse
from services import ai_service, conversation_service

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
def chat(body: ChatRequest):
    """AI 비서에게 질문하기.

    흐름: (이어가는 대화면 기록 불러오기) -> 데이터 요약을 시스템 프롬프트에 주입 -> GPT 호출
          -> 질문/답변을 conversations에 자동 저장
    """
    if ai_service.client is None:
        raise HTTPException(
            status_code=500,
            detail="OPENAI_API_KEY를 읽지 못했습니다. .env 파일과 실행 위치(backend 폴더)를 확인하세요.",
        )

    # 1) 이어가는 대화라면 이전 기록을 불러온다
    history = []
    if body.conversation_id:
        conv = conversation_service.get_conversation(body.conversation_id)
        if conv is None:
            raise HTTPException(status_code=404, detail="해당 id의 대화를 찾을 수 없습니다.")
        history = conv["messages"]

    # 2) AI 호출 (요약 주입은 ai_service 안에서 처리)
    try:
        reply, tools_used = ai_service.run_chat(body.message, history)
    except OpenAIError as e:
        raise HTTPException(status_code=502, detail=f"AI 호출 중 오류가 발생했습니다: {e}")

    # 3) 대화 자동 저장
    new_messages = [
        {"role": "user", "content": body.message},
        {"role": "assistant", "content": reply},
    ]
    if body.conversation_id:
        conversation_service.append_messages(body.conversation_id, new_messages)
        conversation_id = body.conversation_id
    else:
        conversation_id = conversation_service.create_conversation(new_messages)["id"]

    return ChatResponse(reply=reply, conversation_id=conversation_id, tools_used=tools_used)
