import json
from collections import defaultdict
import logging
from datetime import date, datetime, timedelta, timezone
from typing import List, Optional

from openai import OpenAI

from config import (
    OPENAI_API_KEY,
    OPENAI_BASE_URL,
    OPENAI_MAX_COMPLETION_TOKENS,
    OPENAI_MODEL,
    OPENAI_TIMEOUT_SECONDS,
    OPENAI_TOKEN_PARAM,
)
from services.data_service import compute_summary, get_rows

MODEL = OPENAI_MODEL

# uvicorn 로그에 함께 찍히도록 uvicorn의 로거를 사용한다 (Render의 Logs 탭, 로컬 터미널에서 확인 가능)
logger = logging.getLogger("uvicorn.error")
_KST = timezone(timedelta(hours=9))


def _today_kst() -> date:
    """오늘 날짜(한국 시간). 서버(Render)는 UTC라서 date.today()를 쓰면 한국 시간 새벽에 하루 전 날짜가 된다."""
    return datetime.now(_KST).date()
MAX_TOOL_ROUNDS = 5  # AI가 도구를 부르는 최대 횟수 (무한 반복 방지)

# 키가 없어도 서버는 켜지도록, 키가 없으면 None으로 둡니다.
# timeout: 응답이 오지 않을 때 무한정 기다리지 않게 함 / max_retries: 실패 시 재시도 1회만
client = (
    OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL, timeout=OPENAI_TIMEOUT_SECONDS, max_retries=1)
    if OPENAI_API_KEY
    else None
)


# ---------------------------------------------------------------
# 1) 추가 조회 도구 (요약만으로 부족할 때 AI가 호출) - 보너스 기능
# ---------------------------------------------------------------
def get_price_stats(start_date: Optional[str] = None, end_date: Optional[str] = None):
    """기간 통계: 건수, 평균, 최저/최고(날짜 포함), 시작값/끝값, 변동폭"""
    rows = get_rows(start_date, end_date)
    if not rows:
        return {"count": 0, "message": "해당 기간에 데이터가 없습니다."}

    values = [r[1] for r in rows]
    low = min(rows, key=lambda r: r[1])
    high = max(rows, key=lambda r: r[1])
    first, last = rows[0], rows[-1]
    change = last[1] - first[1]

    return {
        "count": len(rows),
        "period": {"start": first[0], "end": last[0]},
        "avg": round(sum(values) / len(values), 2),
        "min": {"value": low[1], "date": low[0]},
        "max": {"value": high[1], "date": high[0]},
        "first": {"value": first[1], "date": first[0]},
        "last": {"value": last[1], "date": last[0]},
        "change": round(change, 2),
        "change_pct": round(change / first[1] * 100, 2),
    }


def get_prices(start_date: Optional[str] = None, end_date: Optional[str] = None, limit: int = 31):
    """일별 가격 목록 (최대 60건). 짧은 기간이나 특정 날짜 조회용"""
    limit = max(1, min(int(limit), 60))
    rows = get_rows(start_date, end_date)
    shown = rows[:limit]
    return {
        "total_in_period": len(rows),
        "returned": len(shown),
        "truncated": len(rows) > len(shown),
        "prices": [{"date": d, "value": v} for d, v in shown],
    }


def get_monthly_averages(start_date: Optional[str] = None, end_date: Optional[str] = None):
    """월별 평균 가격. 긴 기간의 추세 파악용"""
    rows = get_rows(start_date, end_date)
    if not rows:
        return {"months": [], "message": "해당 기간에 데이터가 없습니다."}

    by_month = defaultdict(list)
    for d, v in rows:
        by_month[d[:7]].append(v)  # "2025-03-15" -> "2025-03"

    months = [
        {"month": m, "avg": round(sum(vs) / len(vs), 2), "days": len(vs)}
        for m, vs in sorted(by_month.items())
    ]
    return {"months": months}


TOOL_FUNCTIONS = {
    "get_price_stats": get_price_stats,
    "get_prices": get_prices,
    "get_monthly_averages": get_monthly_averages,
}

_DATE_PARAMS = {
    "start_date": {"type": "string", "description": "시작일 YYYY-MM-DD (생략하면 처음부터)"},
    "end_date": {"type": "string", "description": "종료일 YYYY-MM-DD (생략하면 끝까지)"},
}

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_price_stats",
            "description": "특정 기간의 평균, 최저가, 최고가(날짜 포함), 시작/끝 가격, 변동폭을 계산한다.",
            "parameters": {"type": "object", "properties": _DATE_PARAMS},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_prices",
            "description": "기간의 일별 가격 목록을 반환한다(최대 60건). 특정 날짜의 가격이나 짧은 기간의 일별 흐름을 볼 때 사용.",
            "parameters": {
                "type": "object",
                "properties": {
                    **_DATE_PARAMS,
                    "limit": {"type": "integer", "description": "최대 반환 건수 (1~60, 기본 31)"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_monthly_averages",
            "description": "기간의 월별 평균 가격을 반환한다. 몇 달~몇 년에 걸친 추세·계절성 질문에 사용.",
            "parameters": {"type": "object", "properties": _DATE_PARAMS},
        },
    },
]


# ---------------------------------------------------------------
# 2) 시스템 프롬프트: 데이터 요약을 주입 (컨텍스트 주입)
# ---------------------------------------------------------------
def _summary_text(s: dict) -> str:
    if s["count"] == 0:
        return "- 저장된 데이터가 없습니다."
    m = s["metrics"]
    return (
        f"- 데이터 기간: {s['period']}\n"
        f"- 총 레코드: {s['count']}개 (하루 1건, 단위: 원/L)\n"
        f"- 주요 지표: 평균 {m['average']:,.1f}원, "
        f"최고 {m['max']:,.1f}원({m['max_date']}), 최저 {m['min']:,.1f}원({m['min_date']}), "
        f"가장 최근 {m['latest']:,.1f}원({m['latest_date']}), 표준편차 {m['std_dev']:,.1f}\n"
        f"- 최근 트렌드: {s['trend']}"
    )


def _freshness_text(s: dict, today: date) -> str:
    """데이터가 어디까지 있는지, 오늘과 얼마나 떨어져 있는지 알려 주는 문장"""
    if s["count"] == 0:
        return ""
    last = date.fromisoformat(s["metrics"]["latest_date"])
    gap = (today - last).days
    if gap > 0:
        return f"데이터의 마지막 날짜는 {last.isoformat()}이며(오늘보다 {gap}일 전), 그 이후의 데이터는 없습니다.\n"
    if gap == 0:
        return f"데이터의 마지막 날짜는 {last.isoformat()}(오늘)입니다.\n"
    return ""


def _system_prompt() -> str:
    summary = compute_summary()
    today = _today_kst()
    return f"""당신은 경상남도 김해시의 휘발유 가격 데이터를 분석해 주는 AI 비서입니다.
오늘 날짜: {today.isoformat()} (한국 시간 기준)
{_freshness_text(summary, today)}
[사용자 데이터 요약]
{_summary_text(summary)}

규칙:
1. 위 요약을 기본 근거로 맞춤형 답변을 하세요. 요약에 없는 세부 값(특정 날짜의 가격, 특정 기간의 평균, 월별 추이 등)은 제공된 도구로 조회한 뒤 답하세요. 기억이나 추측으로 숫자를 말하지 마세요.
2. '올해', '지난달', '최근'처럼 상대적인 기간은 오늘 날짜 기준으로 계산해 YYYY-MM-DD로 바꿔서 도구에 전달하세요.
3. 보유 데이터 기간 밖의 질문이면 보유 기간을 안내하고, 해당 기간은 답할 수 없다고 말하세요.
4. 한국어로 간결하고 친절하게 답하세요. 가격은 '1,700.5원/L'처럼 천 단위 쉼표와 단위를 붙이세요.
5. 휘발유 가격과 무관한 질문에는 정중하게 답변 가능한 범위를 안내하세요.
6. 가격 전망이나 주유 시점을 단정하지 말고, 과거 데이터에 근거한 참고 의견임을 밝히세요.
7. 데이터의 마지막 날짜 이후에 해당하는 기간(예: '오늘', '이번 주', '이번 달')을 물으면, 그 기간의 데이터는 아직 없다고 먼저 알리고, 가장 최근 데이터로 대신 답하면서 기준 날짜를 밝히세요.
8. 마크다운 문법(**, #, 표 등)은 쓰지 말고 일반 문장과 줄바꿈으로만 답하세요."""


# ---------------------------------------------------------------
# 3) 채팅 실행: 질문 -> (필요시 도구 호출 반복) -> 최종 답변
# ---------------------------------------------------------------
def run_chat(message: str, history: List[dict], trace: Optional[List[dict]] = None) -> tuple[str, List[str]]:
    """trace 리스트를 넘기면 도구 호출 내역({name, arguments})이 거기에 쌓인다."""
    messages = [{"role": "system", "content": _system_prompt()}]
    for m in history[-10:]:  # 최근 대화 10개까지만 사용 (비용 절약)
        messages.append({"role": m["role"], "content": m["content"]})
    messages.append({"role": "user", "content": message})

    tools_used: List[str] = []

    for _ in range(MAX_TOOL_ROUNDS):
        # 출력 토큰 상한은 항상 적용한다. gpt-5 계열은 추론 토큰도 포함되므로 넉넉하게 잡는다.
        # (서버가 max_completion_tokens를 지원하지 않을 때는 OPENAI_TOKEN_PARAM=max_tokens 로 이름만 바꾼다)
        limits = {OPENAI_TOKEN_PARAM: OPENAI_MAX_COMPLETION_TOKENS}
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=TOOLS,
            **limits,
        )
        choice = response.choices[0]
        reply = choice.message

        usage = getattr(response, "usage", None)  # 실제 토큰 사용량을 기록해 두면 상한(OPENAI_MAX_COMPLETION_TOKENS)을 근거 있게 조정할 수 있다
        if usage is not None:
            reasoning = getattr(getattr(usage, "completion_tokens_details", None), "reasoning_tokens", None)
            logger.info("토큰 사용: prompt=%s completion=%s (추론=%s)", usage.prompt_tokens, usage.completion_tokens, reasoning)

        # 도구 호출 없이 바로 답을 줬다면 끝
        if not reply.tool_calls:
            text = reply.content or ""
            if choice.finish_reason == "length":  # 토큰 상한에 걸려 답이 끊긴 경우
                if text:
                    text += "\n\n(답변이 길어 중간에 끊겼어요. 질문을 더 구체적으로 해 주세요.)"
                else:
                    text = "답변을 끝까지 만들지 못했어요(길이 제한). 질문을 더 구체적으로 해 주세요."
            return text, tools_used

        # AI가 요청한 도구를 실행하고 결과를 돌려준다
        messages.append(reply)
        for call in reply.tool_calls:
            name = call.function.name
            args = {}
            try:
                args = json.loads(call.function.arguments or "{}")
                result = TOOL_FUNCTIONS[name](**args)
            except Exception as e:  # 도구 실행 실패도 AI에게 알려준다
                result = {"error": str(e)}
            tools_used.append(name)
            if trace is not None:
                trace.append({"name": name, "arguments": args if isinstance(args, dict) else {}})
            logger.info("도구 호출: %s(%s)", name, args)
            messages.append({
                "role": "tool",
                "tool_call_id": call.id,
                "content": json.dumps(result, ensure_ascii=False),
            })

    return "죄송합니다. 데이터를 조회하는 데 시간이 너무 오래 걸려 답변을 완성하지 못했어요. 질문을 조금 더 구체적으로 해 주세요.", tools_used
