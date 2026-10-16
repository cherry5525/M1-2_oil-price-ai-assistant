import os
from pathlib import Path

from dotenv import load_dotenv

# 프로젝트 맨 위 폴더의 .env를 읽는다. (이 파일 위치 기준으로 계산하므로 실행하는 폴더와 상관없이 같은 파일을 찾는다.)
# 배포 서버(Render)에는 .env가 없고 환경 변수가 직접 설정되어 있으므로, 파일이 없어도 오류 없이 넘어간다.
load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env")


def _positive_int_env(name: str, default: int) -> int:
    """양의 정수 환경 변수. 비어 있거나 숫자가 아니거나 0 이하이면 기본값을 쓴다.
    (비용/남용 방지용 한도를 0이나 음수로 '해제'하지 못하게 하기 위함)"""
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        return default
    return value if value > 0 else default


def _positive_float_env(name: str, default: float) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except ValueError:
        return default
    return value if value > 0 else default


# ---- AI (OpenAI 호환 API) ----
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://copa.codyssey.kr/v1")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5-mini")  # README, .env.example과 같은 기본값
OPENAI_MAX_COMPLETION_TOKENS = _positive_int_env("OPENAI_MAX_COMPLETION_TOKENS", 4000)  # 0 이하는 허용하지 않음
OPENAI_TIMEOUT_SECONDS = _positive_float_env("OPENAI_TIMEOUT_SECONDS", 60)

# 출력 토큰 상한을 전달할 때 쓸 파라미터 이름. 서버가 max_completion_tokens를 지원하지 않으면 max_tokens로 바꾼다.
# (상한을 없애는 것이 아니라 이름만 바꾸는 옵션)
_token_param = os.getenv("OPENAI_TOKEN_PARAM", "max_completion_tokens").strip()
OPENAI_TOKEN_PARAM = _token_param if _token_param in ("max_completion_tokens", "max_tokens") else "max_completion_tokens"

# ---- 채팅 요청 제한 (서버 전체 합산, OpenAI 비용 방어) ----
CHAT_RATE_LIMIT_PER_MINUTE = _positive_int_env("CHAT_RATE_LIMIT_PER_MINUTE", 20)
CHAT_DAILY_LIMIT = _positive_int_env("CHAT_DAILY_LIMIT", 300)

# ---- Firebase ----
FIREBASE_SERVICE_ACCOUNT_PATH = os.getenv("FIREBASE_SERVICE_ACCOUNT_PATH", "serviceAccountKey.json")
FIREBASE_SERVICE_ACCOUNT_JSON = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")

# ---- CORS ----
# 환경 변수를 깜빡해도 모든 사이트가 허용되지 않도록, 기본값은 로컬 개발 주소만 허용한다.
# 배포(Render)에서는 반드시 프론트엔드 주소로 설정한다. (끝의 "/"는 자동으로 제거해서 흔한 입력 실수를 막는다)
_DEFAULT_ORIGINS = "http://localhost:5500,http://127.0.0.1:5500"
ALLOWED_ORIGINS = [o.strip().rstrip("/") for o in os.getenv("ALLOWED_ORIGINS", _DEFAULT_ORIGINS).split(",") if o.strip()]
