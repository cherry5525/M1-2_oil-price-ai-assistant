import os
from pathlib import Path

from dotenv import load_dotenv

# 프로젝트 맨 위 폴더의 .env를 읽는다. (이 파일 위치 기준으로 계산하므로 실행하는 폴더와 상관없이 같은 파일을 찾는다.)
# 배포 서버(Render)에는 .env가 없고 환경 변수가 직접 설정되어 있으므로, 파일이 없어도 오류 없이 넘어간다.
load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env")

# ---- AI (OpenAI 호환 API) ----
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://copa.codyssey.kr/v1")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5-mini")  # README, .env.example과 같은 기본값
OPENAI_MAX_COMPLETION_TOKENS = int(os.getenv("OPENAI_MAX_COMPLETION_TOKENS", "4000"))
OPENAI_TIMEOUT_SECONDS = float(os.getenv("OPENAI_TIMEOUT_SECONDS", "60"))

# ---- Firebase ----
FIREBASE_SERVICE_ACCOUNT_PATH = os.getenv("FIREBASE_SERVICE_ACCOUNT_PATH", "serviceAccountKey.json")
FIREBASE_SERVICE_ACCOUNT_JSON = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")

# ---- CORS ----
ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "*").split(",") if o.strip()]
