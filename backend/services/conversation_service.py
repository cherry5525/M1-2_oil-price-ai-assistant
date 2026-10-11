"""대화 기록(conversations 컬렉션) 저장/조회/삭제.

문서 구조:
  {
    "title": "2025년 평균 가격이...",
    "messages": [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}],
    "created_at": "2026-10-08T01:23:45+00:00",
    "updated_at": "2026-10-08T01:25:10+00:00"
  }
"""
import json
from datetime import datetime, timezone
from typing import List, Optional

from google.cloud.firestore_v1 import Query as FSQuery
from google.cloud.firestore_v1 import transactional

from firebase_client import db  # 변수 이름이 db가 아니면 다른 파일과 똑같이 맞춰주세요

COLLECTION = "conversations"

# Firestore 문서 하나는 최대 1MiB(1,048,576바이트). 한 번의 질문/답변이 약 20KB를 넘지 않으므로 여유를 두고 900KB로 제한한다.
MAX_CONVERSATION_BYTES = 900_000


def messages_size_bytes(messages: List[dict]) -> int:
    """메시지 목록이 차지하는 대략적인 저장 크기(바이트)"""
    return len(json.dumps(messages, ensure_ascii=False).encode("utf-8"))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_title(messages: List[dict]) -> str:
    """첫 번째 사용자 메시지의 앞 30자를 제목으로 사용"""
    for m in messages:
        if m["role"] == "user":
            text = m["content"].strip().replace("\n", " ")
            return text[:30] + ("…" if len(text) > 30 else "")
    return "새 대화"


def create_conversation(messages: List[dict], title: Optional[str] = None) -> dict:
    now = _now()
    data = {
        "title": title or _make_title(messages),
        "messages": messages,
        "created_at": now,
        "updated_at": now,
    }
    _, ref = db.collection(COLLECTION).add(data)
    return {"id": ref.id, **data}


def get_conversation(conversation_id: str) -> Optional[dict]:
    doc = db.collection(COLLECTION).document(conversation_id).get()
    if not doc.exists:
        return None
    return {"id": doc.id, **doc.to_dict()}


def list_conversations(limit: int = 50) -> List[dict]:
    """최근에 갱신된 순서. 목록에는 메시지 본문 대신 개수만 포함한다."""
    query = db.collection(COLLECTION).order_by("updated_at", direction=FSQuery.DESCENDING).limit(limit)
    result = []
    for doc in query.stream():
        d = doc.to_dict()
        result.append({
            "id": doc.id,
            "title": d.get("title", ""),
            "created_at": d.get("created_at", ""),
            "updated_at": d.get("updated_at", ""),
            "message_count": len(d.get("messages", [])),
        })
    return result


def _append_logic(transaction, ref, new_messages: List[dict]) -> Optional[dict]:
    """읽고 -> 합치고 -> 쓰기. 트랜잭션 안에서 실행되므로, 읽은 뒤 다른 요청이 같은 대화를 바꾸면
    Firestore가 이 함수를 처음부터 다시 실행해 준다. (한쪽이 다른 쪽을 덮어쓰는 일이 없음)"""
    snapshot = ref.get(transaction=transaction)
    if not snapshot.exists:
        return None

    data = snapshot.to_dict()
    messages = data.get("messages", []) + new_messages
    updated_at = _now()
    transaction.update(ref, {"messages": messages, "updated_at": updated_at})
    return {"id": ref.id, **data, "messages": messages, "updated_at": updated_at}


# ArrayUnion은 내용이 같은 메시지(같은 질문 두 번)를 하나로 합쳐 버리므로 쓰지 않고, 대신 트랜잭션을 사용한다.
_append_in_transaction = transactional(_append_logic)


def append_messages(conversation_id: str, new_messages: List[dict]) -> Optional[dict]:
    """기존 대화 끝에 메시지를 이어 붙인다. 대화가 없으면 None"""
    ref = db.collection(COLLECTION).document(conversation_id)
    return _append_in_transaction(db.transaction(), ref, new_messages)


def delete_conversation(conversation_id: str) -> bool:
    ref = db.collection(COLLECTION).document(conversation_id)
    if not ref.get().exists:
        return False
    ref.delete()
    return True
