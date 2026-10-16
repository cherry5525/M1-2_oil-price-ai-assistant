from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import data, chat, conversations
from config import ALLOWED_ORIGINS

app = FastAPI(title="김해시 주유 타이밍 AI 비서 API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    # 이 서비스는 쿠키나 로그인 정보를 쓰지 않으므로 자격 증명 전달을 허용하지 않는다.
    # (허용하면, ALLOWED_ORIGINS가 "*"일 때 아무 사이트나 자격 증명과 함께 요청할 수 있는 구성이 된다)
    allow_credentials=False,
    # 프론트엔드가 실제로 쓰는 메서드/헤더만 허용한다.
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type"],
)

app.include_router(data.router)
app.include_router(chat.router)
app.include_router(conversations.router)


@app.get("/")
def root():
    return {"message": "오피넷 기반 AI 주유 비서 API가 정상적으로 실행 중입니다."}
