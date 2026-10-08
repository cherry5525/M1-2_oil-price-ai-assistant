"""LLM 서버 연결 확인용 스크립트.

사용법
  1) python test_llm.py              -> 사용 가능한 모델 목록 출력
  2) python test_llm.py 모델이름      -> 해당 모델로 일반 대화 + 도구 호출 지원 여부 테스트
"""
import sys

from openai import OpenAI

from config import OPENAI_API_KEY, OPENAI_BASE_URL

if not OPENAI_API_KEY:
    sys.exit("OPENAI_API_KEY가 비어 있습니다. .env 파일을 확인하세요.")
if not OPENAI_API_KEY.isascii():
    sys.exit("OPENAI_API_KEY에 한글 등 영문 외 글자가 섞여 있습니다. .env에 실제 키를 붙여 넣었는지 확인하세요.")

client = OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL)
print("접속 주소:", OPENAI_BASE_URL)

# ---- 모델 이름을 아직 안 줬다면: 목록만 출력 ----
if len(sys.argv) < 2:
    print("\n=== 사용 가능한 모델 ===")
    try:
        for m in client.models.list():
            print(" -", m.id)
    except Exception as e:
        print("모델 목록 조회 실패:", repr(e))
        print("(목록 기능이 없는 서비스일 수 있습니다. 서비스 안내 문서에서 모델 이름을 확인하세요.)")
    sys.exit()

model = sys.argv[1]

# ---- 1) 일반 대화 테스트 ----
print(f"\n=== 1) 일반 대화 테스트 (model={model}) ===")
try:
    r = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": "안녕! 한 문장으로 인사해줘."}],
    )
    print("응답:", r.choices[0].message.content)
except Exception as e:
    sys.exit(f"실패: {e!r}")

# ---- 2) 도구 호출(function calling) 지원 테스트 ----
print("\n=== 2) 도구 호출 지원 테스트 ===")
tools = [{
    "type": "function",
    "function": {
        "name": "get_secret_number",
        "description": "비밀 숫자를 알려주는 도구",
        "parameters": {"type": "object", "properties": {}},
    },
}]
try:
    r = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": "get_secret_number 도구를 호출해서 비밀 숫자를 알아내줘."}],
        tools=tools,
    )
    calls = r.choices[0].message.tool_calls
    if calls:
        print("도구 호출 지원: 예 ->", calls[0].function.name)
    else:
        print("도구 호출 지원: 아니오 (모델이 도구를 호출하지 않고 글로만 답했습니다)")
except Exception as e:
    print("도구 호출 지원: 아니오 또는 오류 ->", repr(e))
