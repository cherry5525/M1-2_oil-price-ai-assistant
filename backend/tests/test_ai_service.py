"""AI 호출 설정(토큰 상한, 길이 제한 처리) 테스트. 진짜 AI는 호출하지 않는다."""
import types

import pytest

from services import ai_service


def fake_client(sequence, calls):
    def create(**kwargs):
        calls.append(kwargs)
        content, finish_reason = sequence.pop(0)
        message = types.SimpleNamespace(content=content, tool_calls=None)
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=message, finish_reason=finish_reason)])

    return types.SimpleNamespace(chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=create)))


@pytest.fixture(autouse=True)
def empty_db(db):
    return db


def test_token_limit_is_sent(monkeypatch):
    calls = []
    monkeypatch.setattr(ai_service, "client", fake_client([("정상 답변", "stop")], calls))
    reply, tools = ai_service.run_chat("질문", [])
    assert reply == "정상 답변" and tools == []
    assert calls[0]["max_completion_tokens"] == ai_service.OPENAI_MAX_COMPLETION_TOKENS > 0


def test_token_limit_can_be_disabled(monkeypatch):
    calls = []
    monkeypatch.setattr(ai_service, "OPENAI_MAX_COMPLETION_TOKENS", 0)
    monkeypatch.setattr(ai_service, "client", fake_client([("ok", "stop")], calls))
    ai_service.run_chat("질문", [])
    assert "max_completion_tokens" not in calls[0]


def test_empty_reply_when_length_limit_hit(monkeypatch):
    monkeypatch.setattr(ai_service, "client", fake_client([("", "length")], []))
    assert "길이 제한" in ai_service.run_chat("질문", [])[0]


def test_partial_reply_gets_notice_when_length_limit_hit(monkeypatch):
    monkeypatch.setattr(ai_service, "client", fake_client([("앞부분만", "length")], []))
    reply = ai_service.run_chat("질문", [])[0]
    assert reply.startswith("앞부분만") and "끊겼어요" in reply


def test_only_last_10_history_messages_are_sent(monkeypatch):
    calls = []
    monkeypatch.setattr(ai_service, "client", fake_client([("ok", "stop")], calls))
    history = [{"role": "user", "content": f"m{i}", "tools_used": ["x"]} for i in range(25)]
    ai_service.run_chat("질문", history)
    sent = calls[0]["messages"]
    assert len(sent) == 1 + 10 + 1  # 시스템 프롬프트 + 최근 10개 + 새 질문
    assert all(set(m) == {"role", "content"} for m in sent)  # tools_used 같은 추가 필드는 AI에 보내지 않음


def test_system_prompt_contains_data_summary(db, monkeypatch):
    db.seed_prices([("2025-01-01", 1600.0), ("2025-01-02", 1700.0)])
    prompt = ai_service._system_prompt()
    assert "[사용자 데이터 요약]" in prompt and "2025-01-01 ~ 2025-01-02" in prompt and "총 레코드: 2개" in prompt
