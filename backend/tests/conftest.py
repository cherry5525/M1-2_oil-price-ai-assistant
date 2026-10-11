import sys
import types

import pytest

# ---------------------------------------------------------------------------
# 진짜 Firebase에 연결되지 않도록, 앱 코드가 import되기 전에 firebase_client를 가짜로 바꿔 둔다.
# ---------------------------------------------------------------------------
from tests.fakes import FakeDB

_fake_module = types.ModuleType("firebase_client")
_fake_module.db = FakeDB()
sys.modules["firebase_client"] = _fake_module

try:  # Firestore 라이브러리가 없는 환경에서도 테스트가 돌도록
    import google.cloud.firestore_v1  # noqa: F401
except ImportError:
    for _name in ("google", "google.cloud", "google.cloud.firestore_v1"):
        sys.modules.setdefault(_name, types.ModuleType(_name))

    class _Query:
        ASCENDING = "ASCENDING"
        DESCENDING = "DESCENDING"

    sys.modules["google.cloud.firestore_v1"].Query = _Query


@pytest.fixture
def db(monkeypatch):
    """테스트마다 새 가짜 DB를 만들어 앱 코드에 끼워 넣는다."""
    import routers.data as data_router
    import services.conversation_service as conversation_service
    import services.data_service as data_service

    fake = FakeDB()
    for module in (data_router, data_service, conversation_service):
        monkeypatch.setattr(module, "db", fake)
    data_service.invalidate_cache()
    yield fake
    data_service.invalidate_cache()


@pytest.fixture
def client(db):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from routers import chat, conversations, data

    app = FastAPI()
    for router_module in (data, chat, conversations):
        app.include_router(router_module.router)
    return TestClient(app)
