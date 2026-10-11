"""환경 변수 해석 테스트. 비용/남용 방지 한도를 0이나 잘못된 값으로 해제할 수 없는지 확인한다."""
import importlib

import pytest

import config


@pytest.mark.parametrize("raw, expected", [
    ("4000", 4000), ("1", 1),
    ("0", 4000), ("-5", 4000), ("abc", 4000), ("", 4000), ("3.5", 4000),  # 잘못된 값 -> 기본값
])
def test_positive_int_env(monkeypatch, raw, expected):
    monkeypatch.setenv("TEST_LIMIT", raw)
    assert config._positive_int_env("TEST_LIMIT", 4000) == expected


def test_positive_int_env_uses_default_when_missing(monkeypatch):
    monkeypatch.delenv("TEST_LIMIT", raising=False)
    assert config._positive_int_env("TEST_LIMIT", 4000) == 4000


def test_positive_float_env(monkeypatch):
    monkeypatch.setenv("TEST_TIMEOUT", "0")
    assert config._positive_float_env("TEST_TIMEOUT", 60) == 60
    monkeypatch.setenv("TEST_TIMEOUT", "12.5")
    assert config._positive_float_env("TEST_TIMEOUT", 60) == 12.5


@pytest.mark.parametrize("name, default", [
    ("OPENAI_MAX_COMPLETION_TOKENS", 4000),
    ("CHAT_RATE_LIMIT_PER_MINUTE", 20),
    ("CHAT_DAILY_LIMIT", 300),
])
def test_cost_limits_cannot_be_disabled_with_zero(monkeypatch, name, default):
    monkeypatch.setenv(name, "0")
    try:
        importlib.reload(config)
        assert getattr(config, name) == default
    finally:
        monkeypatch.undo()
        importlib.reload(config)


def test_token_param_only_accepts_known_names(monkeypatch):
    try:
        monkeypatch.setenv("OPENAI_TOKEN_PARAM", "max_tokens")
        importlib.reload(config)
        assert config.OPENAI_TOKEN_PARAM == "max_tokens"

        monkeypatch.setenv("OPENAI_TOKEN_PARAM", "no_limit")
        importlib.reload(config)
        assert config.OPENAI_TOKEN_PARAM == "max_completion_tokens"
    finally:
        monkeypatch.undo()
        importlib.reload(config)


def test_default_model_matches_env_example(monkeypatch):
    """코드의 기본 모델이 .env.example(README와 같은 값)과 어긋나지 않는지 확인한다."""
    from pathlib import Path

    example = Path(__file__).resolve().parents[2] / ".env.example"
    if not example.exists():
        pytest.skip(".env.example이 없는 위치에서 실행됨")
    documented = next(line.split("=", 1)[1].strip() for line in example.read_text(encoding="utf-8").splitlines()
                      if line.startswith("OPENAI_MODEL="))

    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.setattr("dotenv.load_dotenv", lambda *args, **kwargs: False)  # 내 .env의 값이 섞이지 않게
    try:
        importlib.reload(config)
        assert config.OPENAI_MODEL == documented
    finally:
        monkeypatch.undo()
        importlib.reload(config)
