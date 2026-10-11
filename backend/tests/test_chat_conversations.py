"""채팅 자동 저장 / 대화 기록 API 테스트. (진짜 AI는 호출하지 않고 가짜 응답을 쓴다.)"""
import pytest

from services import ai_service


@pytest.fixture
def fake_ai(monkeypatch):
    calls = []

    def fake_run_chat(message, history):
        calls.append({"message": message, "history": history})
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
