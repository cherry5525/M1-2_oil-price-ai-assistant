"""입력 검증(Pydantic) 테스트. 잘못된 값이 DB에 들어가기 전에 막히는지 확인한다."""
import datetime as dt

import pytest
from pydantic import ValidationError

from schemas import DataCreate, DataUpdate

KST = dt.timezone(dt.timedelta(hours=9))


def today():
    return dt.datetime.now(KST).date()


# ---- 수정(PUT): null로 필수 값을 지우는 요청 ----
@pytest.mark.parametrize("body", [{"value": None}, {"date": None}, {"value": None, "date": None}])
def test_update_rejects_null_for_date_and_value(body):
    with pytest.raises(ValidationError):
        DataUpdate(**body)


def test_update_allows_omitting_fields_and_null_memo():
    assert DataUpdate(value=1700).model_dump(exclude_unset=True) == {"value": 1700.0}
    assert DataUpdate(memo=None).model_dump(exclude_unset=True) == {"memo": None}


# ---- 날짜 ----
@pytest.mark.parametrize("bad", [
    "2024-1-5", "2024-01-5", "2024-1-05",   # 0을 채우지 않은 표기 (문자열 정렬이 깨짐)
    "0001-01-01", "1999-12-31",             # 범위 밖
    "2024-02-30",                           # 없는 날짜
    "20240105", "2024-01-05\n", "２０２４-01-05", "",  # 형식 오류
])
def test_date_rejects_bad_values(bad):
    with pytest.raises(ValidationError):
        DataCreate(date=bad, value=1700)


def test_date_rejects_future():
    tomorrow = (today() + dt.timedelta(days=1)).isoformat()
    with pytest.raises(ValidationError):
        DataCreate(date=tomorrow, value=1700)


@pytest.mark.parametrize("good", ["2024-01-05", "2000-01-01"])
def test_date_accepts_valid_values(good):
    assert DataCreate(date=good, value=1700).date == good


def test_date_accepts_today():
    assert DataCreate(date=today().isoformat(), value=1700).date == today().isoformat()


# ---- 가격 / 메모 ----
@pytest.mark.parametrize("bad", [0, -1, 10001, float("nan"), float("inf")])
def test_value_rejects_bad_numbers(bad):
    with pytest.raises(ValidationError):
        DataCreate(date="2024-01-05", value=bad)


def test_memo_length_limit():
    DataCreate(date="2024-01-05", value=1700, memo="가" * 100)
    with pytest.raises(ValidationError):
        DataCreate(date="2024-01-05", value=1700, memo="가" * 101)
