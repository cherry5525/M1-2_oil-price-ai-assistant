"""채팅 자동 저장 / 대화 기록 API 테스트. (진짜 AI는 호출하지 않고 가짜 응답을 쓴다.)"""
import pytest

from services import ai_service


@pytest.fixture
def fake_ai(monkeypatch):
    calls = []

    def fake_run_chat(message, history, trace=None):
        calls.append({"message": message, "history": history})
        if trace is not None:
            trace.append({"name": "get_price_stats", "arguments": {"start_date": "2025-03-01", "end_date": "2025-03-31"}})
        return f"답변: {message}", ["get_price_stats", "get_price_stats", "get_prices"]

    monkeypatch.setattr(ai_service, "client", object())  # API 키가 없어도 통과하도록
    monkeypatch.setattr(ai_service, "run_chat", fake_run_chat)
    return calls


def test_chat_saves_conversation_with_tools_used(client, db, fake_ai):
    r = client.post("/api/chat", json={"message": "평균은?"})
    assert r.status_code == 200
    conv_id = r.json()["conversation_id"]

    saved = db.collections["conversations"][conv_id]["messages"]
    assert saved[0] == {"role": "user", "content": "평균은?"}          # 사용자 메시지에는 tools_used가 없음
    assert saved[1]["tools_used"] == ["get_price_stats", "get_prices"]  # 중복 제거, 순서 유지

    detail = client.get(f"/api/conversations/{conv_id}").json()          # 다시 열었을 때도 보여야 함
    assert detail["messages"][1]["tools_used"] == ["get_price_stats", "get_prices"]
    assert detail["messages"][0]["tools_used"] == []


def test_chat_continues_existing_conversation(client, db, fake_ai):
    conv_id = client.post("/api/chat", json={"message": "첫 질문"}).json()["conversation_id"]
    r = client.post("/api/chat", json={"message": "두번째 질문", "conversation_id": conv_id})
    assert r.json()["conversation_id"] == conv_id
    assert len(db.collections["conversations"][conv_id]["messages"]) == 4
    assert [m["content"] for m in fake_ai[1]["history"]] == ["첫 질문", "답변: 첫 질문"]  # AI에는 이전 대화가 전달됨
    assert client.get("/api/conversations").json()[0]["message_count"] == 4


def test_chat_with_same_question_twice_keeps_both(client, db, fake_ai):
    conv_id = client.post("/api/chat", json={"message": "안녕"}).json()["conversation_id"]
    client.post("/api/chat", json={"message": "안녕", "conversation_id": conv_id})
    assert len(db.collections["conversations"][conv_id]["messages"]) == 4  # 같은 질문도 중복 제거되지 않음


def test_chat_errors(client, db, fake_ai, monkeypatch):
    assert client.post("/api/chat", json={"message": "x", "conversation_id": "없는id"}).status_code == 404
    assert client.post("/api/chat", json={"message": ""}).status_code == 422
    assert client.post("/api/chat", json={"message": "가" * 1001}).status_code == 422
    monkeypatch.setattr(ai_service, "client", None)
    assert client.post("/api/chat", json={"message": "x"}).status_code == 500


def test_conversation_crud(client, db):
    r = client.post("/api/conversations", json={"messages": [
        {"role": "user", "content": "저장 테스트"}, {"role": "assistant", "content": "저장됩니다"}]})
    assert r.status_code == 201
    conv_id = r.json()["id"]
    assert r.json()["title"] == "저장 테스트"
    assert "tools_used" not in db.collections["conversations"][conv_id]["messages"][0]

    assert client.get("/api/conversations").json()[0]["message_count"] == 2
    assert client.get(f"/api/conversations/{conv_id}").status_code == 200
    assert client.delete(f"/api/conversations/{conv_id}").status_code == 200
    assert client.get(f"/api/conversations/{conv_id}").status_code == 404
    assert client.delete(f"/api/conversations/{conv_id}").status_code == 404
    assert client.post("/api/conversations", json={"messages": []}).status_code == 422


# ---------------------------------------------------------------------------
# 요청 제한 / 동시성 / 용량 제한
# ---------------------------------------------------------------------------
def test_chat_rate_limit_returns_429_with_retry_after(client, db, fake_ai, monkeypatch):
    import routers.chat as chat_router
    from services.rate_limiter import RateLimiter

    monkeypatch.setattr(chat_router, "chat_limiter", RateLimiter(per_minute=2, per_day=100))
    assert client.post("/api/chat", json={"message": "1"}).status_code == 200
    assert client.post("/api/chat", json={"message": "2"}).status_code == 200

    r = client.post("/api/chat", json={"message": "3"})
    assert r.status_code == 429
    assert "초 뒤에 다시" in r.json()["detail"]
    assert int(r.headers["retry-after"]) >= 1
    assert len(fake_ai) == 2  # 거절된 요청은 AI를 호출하지 않음 (비용이 들지 않음)


def test_daily_limit_message(client, db, fake_ai, monkeypatch):
    import routers.chat as chat_router
    from services.rate_limiter import RateLimiter

    monkeypatch.setattr(chat_router, "chat_limiter", RateLimiter(per_minute=100, per_day=1))
    client.post("/api/chat", json={"message": "1"})
    r = client.post("/api/chat", json={"message": "2"})
    assert r.status_code == 429 and "하루 질문 한도" in r.json()["detail"]


def test_rejected_requests_do_not_use_up_the_limit(client, db, fake_ai, monkeypatch):
    import routers.chat as chat_router
    from services.rate_limiter import RateLimiter

    monkeypatch.setattr(chat_router, "chat_limiter", RateLimiter(per_minute=1, per_day=100))
    assert client.post("/api/chat", json={"message": "x", "conversation_id": "없는id"}).status_code == 404
    assert client.post("/api/chat", json={"message": ""}).status_code == 422
    assert client.post("/api/chat", json={"message": "정상 질문"}).status_code == 200  # 한도를 소모하지 않았으므로 성공


def test_oversized_conversation_is_rejected_before_calling_ai(client, db, fake_ai):
    from services import conversation_service

    db.collections["conversations"]["big"] = {
        "title": "큰 대화", "created_at": "", "updated_at": "",
        "messages": [{"role": "user", "content": "가" * 400_000}, {"role": "assistant", "content": "나" * 400_000}],
    }
    assert conversation_service.messages_size_bytes(db.collections["conversations"]["big"]["messages"]) > conversation_service.MAX_CONVERSATION_BYTES

    r = client.post("/api/chat", json={"message": "계속", "conversation_id": "big"})
    assert r.status_code == 409 and "새 대화" in r.json()["detail"]
    assert fake_ai == []  # AI를 호출하지 않았다


def test_append_goes_through_a_transaction(client, db, fake_ai):
    conv_id = client.post("/api/chat", json={"message": "첫 질문"}).json()["conversation_id"]
    assert db.transaction_updates == 0  # 새 대화 생성은 트랜잭션이 필요 없음
    client.post("/api/chat", json={"message": "두번째", "conversation_id": conv_id})
    assert db.transaction_updates == 1  # 이어 붙이기는 트랜잭션 경로로 저장됨


def test_append_to_missing_conversation_returns_none(db):
    from services import conversation_service

    assert conversation_service.append_messages("없는id", [{"role": "user", "content": "x"}]) is None


def test_reply_is_not_lost_if_conversation_is_deleted_while_ai_is_answering(client, db, monkeypatch):
    """AI가 답하는 동안 같은 대화가 삭제되어도 답변이 사라지지 않고 새 대화로 저장된다."""
    monkeypatch.setattr(ai_service, "client", object())
    conv_id = None

    def run_chat_and_delete(message, history, trace=None):
        db.collections["conversations"].pop(conv_id)  # 답변을 만드는 도중 삭제
        return "답변", []

    monkeypatch.setattr(ai_service, "run_chat", run_chat_and_delete)
    db.collections["conversations"]["c1"] = {"title": "t", "created_at": "", "updated_at": "",
                                             "messages": [{"role": "user", "content": "a"}]}
    conv_id = "c1"

    r = client.post("/api/chat", json={"message": "질문", "conversation_id": "c1"})
    assert r.status_code == 200
    new_id = r.json()["conversation_id"]
    assert new_id != "c1" and db.collections["conversations"][new_id]["messages"][1]["content"] == "답변"


# ---------------------------------------------------------------------------
# 도구 호출 내역 / 대화 저장 입력 상한
# ---------------------------------------------------------------------------
def test_chat_response_includes_tool_call_arguments(client, db, fake_ai):
    r = client.post("/api/chat", json={"message": "2025년 3월 평균은?"}).json()
    assert r["tool_calls"] == [{"name": "get_price_stats", "arguments": {"start_date": "2025-03-01", "end_date": "2025-03-31"}}]


def _message(**overrides):
    return {"role": "user", "content": "안녕", **overrides}


def test_conversation_save_limits_input_size(client, db):
    assert client.post("/api/conversations", json={"messages": [_message(content="가" * 20000)]}).status_code == 201
    assert client.post("/api/conversations", json={"messages": [_message(content="가" * 20001)]}).status_code == 422
    assert client.post("/api/conversations", json={"messages": [_message()] * 100}).status_code == 201
    assert client.post("/api/conversations", json={"messages": [_message()] * 101}).status_code == 422
    assert client.post("/api/conversations", json={"messages": [_message(tools_used=["a"] * 11)]}).status_code == 422
    assert client.post("/api/conversations", json={"messages": [_message(tools_used=["가" * 51])]}).status_code == 422
    assert client.post("/api/conversations", json={"title": "가" * 101, "messages": [_message()]}).status_code == 422
