from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import data, chat, conversations
from config import ALLOWED_ORIGINS

app = FastAPI(title="김해시 주유 타이밍 AI 비서 API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(data.router)
app.include_router(chat.router)
app.include_router(conversations.router) 

@app.get("/")
def root():
    return {"message": "오피넷 기반 AI 주유 비서 API가 정상적으로 실행 중입니다."}