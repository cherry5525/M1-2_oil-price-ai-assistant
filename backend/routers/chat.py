import math

from fastapi import APIRouter, HTTPException
from openai import OpenAIError

from schemas import ChatRequest, ChatResponse
from services import ai_service, conversation_service
from services.rate_limiter import chat_limiter

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
def chat(body: ChatRequest):
    """AI 비서에게 질문하기.

    흐름: (이어가는 대화면 기록 불러오기) -> 요청 횟수 확인 -> 데이터 요약을 시스템 프롬프트에 주입 -> GPT 호출
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
        # Firestore 문서는 1MiB가 한계라서, 한도에 가까우면 AI를 호출하기 전에 거절한다 (비용 낭비 방지)
        if conversation_service.messages_size_bytes(history) > conversation_service.MAX_CONVERSATION_BYTES:
            raise HTTPException(
                status_code=409,
                detail="이 대화는 저장 용량 한도에 가까워 더 이어갈 수 없어요. 새 대화를 시작해 주세요.",
            )

    # 2) 요청 횟수 제한 (AI를 실제로 호출하는 요청만 센다. 위에서 거절된 요청은 세지 않음)
    allowed, retry_after, reason = chat_limiter.acquire()
    if not allowed:
        if reason == "day":
            detail = f"하루 질문 한도를 모두 사용했어요. 약 {math.ceil(retry_after / 3600)}시간 뒤에 다시 시도해 주세요."
        else:
            detail = f"질문이 너무 빨리 들어오고 있어요. {retry_after}초 뒤에 다시 시도해 주세요."
        raise HTTPException(status_code=429, detail=detail, headers={"Retry-After": str(retry_after)})

    # 3) AI 호출 (요약 주입은 ai_service 안에서 처리)
    try:
        trace: list = []  # AI가 호출한 도구와 인자가 여기에 쌓인다
        reply, tools_used = ai_service.run_chat(body.message, history, trace=trace)
    except OpenAIError as e:
        raise HTTPException(status_code=502, detail=f"AI 호출 중 오류가 발생했습니다: {e}")

    # 4) 대화 자동 저장
    assistant_message = {"role": "assistant", "content": reply}
    if tools_used:  # 대화를 다시 열어도 "추가 조회" 표시가 보이도록 함께 저장
        assistant_message["tools_used"] = list(dict.fromkeys(tools_used))  # 중복 제거, 순서 유지
    new_messages = [{"role": "user", "content": body.message}, assistant_message]

    conversation_id = body.conversation_id
    if conversation_id and conversation_service.append_messages(conversation_id, new_messages) is None:
        conversation_id = None  # AI가 답하는 사이에 대화가 삭제된 경우: 새 대화로 저장해서 답변을 잃지 않는다
    if not conversation_id:
        conversation_id = conversation_service.create_conversation(new_messages)["id"]

    return ChatResponse(reply=reply, conversation_id=conversation_id, tools_used=tools_used, tool_calls=trace)
