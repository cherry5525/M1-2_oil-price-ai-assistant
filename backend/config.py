import os
from dotenv import load_dotenv

# 프로젝트 루트의 .env 파일을 읽음
load_dotenv(dotenv_path="../.env")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://copa.codyssey.kr/v1")   # ← 추가
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
FIREBASE_SERVICE_ACCOUNT_PATH = os.getenv("FIREBASE_SERVICE_ACCOUNT_PATH", "serviceAccountKey.json")
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "*").split(",")