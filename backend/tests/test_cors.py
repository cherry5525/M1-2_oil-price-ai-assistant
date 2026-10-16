"""CORS 설정(main.py) 테스트. 실제 앱(main.app)에 브라우저의 사전 요청(preflight)을 보내 확인한다."""
import pytest
from fastapi.testclient import TestClient

import config
from main import app

client = TestClient(app)
EVIL = "https://evil.example"


def allowed_origin():
    """설정된 허용 출처 중 하나 ('*'는 제외)"""
    return next((o for o in config.ALLOWED_ORIGINS if o != "*"), "http://localhost:5500")


def preflight(origin, method="DELETE", headers="content-type"):
    return client.options("/api/data/abc", headers={
        "Origin": origin, "Access-Control-Request-Method": method, "Access-Control-Request-Headers": headers})


def test_allowed_origin_passes_preflight():
    r = preflight(allowed_origin())
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == allowed_origin()


def test_credentials_are_never_allowed():
    """쿠키/로그인 정보를 쓰지 않는 서비스이므로 자격 증명 허용 헤더가 어떤 응답에도 나오면 안 된다."""
    assert "access-control-allow-credentials" not in preflight(allowed_origin()).headers
    assert "access-control-allow-credentials" not in client.get("/", headers={"Origin": allowed_origin()}).headers


@pytest.mark.skipif("*" in config.ALLOWED_ORIGINS, reason="ALLOWED_ORIGINS에 *가 설정된 환경")
def test_other_sites_are_rejected():
    r = preflight(EVIL)
    assert r.status_code == 400
    assert "access-control-allow-origin" not in r.headers


def test_only_methods_used_by_the_frontend_are_allowed():
    assert preflight(allowed_origin(), "DELETE").status_code == 200
    assert preflight(allowed_origin(), "PATCH").status_code == 400


def test_only_content_type_header_is_allowed():
    assert preflight(allowed_origin(), headers="content-type").status_code == 200
    assert preflight(allowed_origin(), headers="x-custom-header").status_code == 400


def test_root_still_works():
    assert client.get("/").status_code == 200
