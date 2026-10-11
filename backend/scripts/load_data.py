"""CSV(date, value, memo)를 Firestore의 'data' 컬렉션에 적재합니다.

- 이미 같은 날짜의 데이터가 있으면 건너뜁니다. (여러 번 실행해도 중복 저장되지 않음)
- 형식이 잘못된 행은 건너뛰고, 마지막에 몇 번째 줄이 왜 제외됐는지 알려 줍니다.

사용법 (backend 폴더에서):
    python -m scripts.load_data                  # 기본 파일(backend/data/gimhae_gasoline_final.csv) 사용
    python -m scripts.load_data 다른파일.csv      # 다른 CSV 사용
"""
import csv
import math
import re
import sys
from datetime import datetime
from pathlib import Path

from firebase_client import db  # 변수 이름이 db가 아니면 다른 파일과 똑같이 맞춰주세요

DEFAULT_CSV = Path(__file__).resolve().parent.parent / "data" / "gimhae_gasoline_final.csv"
COLLECTION = "data"
BATCH_SIZE = 400  # Firestore는 한 번에 최대 500건까지 쓸 수 있음
DATE_PATTERN = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")


def parse_row(row: dict) -> dict:
    """CSV 한 줄을 검증해서 저장할 형태로 바꾼다. 잘못되면 ValueError"""
    date_str = (row.get("date") or "").strip()
    if not DATE_PATTERN.fullmatch(date_str):
        raise ValueError(f"날짜 형식이 YYYY-MM-DD가 아닙니다: {date_str!r}")
    try:
        datetime.strptime(date_str, "%Y-%m-%d")  # 2024-02-30 같은 없는 날짜를 걸러낸다
    except ValueError:
        raise ValueError(f"존재하지 않는 날짜입니다: {date_str!r}")

    try:
        value = float((row.get("value") or "").strip())
    except ValueError:
        raise ValueError(f"가격이 숫자가 아닙니다: {row.get('value')!r}")
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"가격은 0보다 큰 유한한 숫자여야 합니다: {value}")

    return {"date": date_str, "value": value, "memo": (row.get("memo") or "").strip()}


def main() -> None:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_CSV
    if not path.exists():
        sys.exit(f"CSV 파일을 찾을 수 없습니다: {path}")

    # 이미 저장된 날짜 목록 (중복 저장 방지)
    seen = {doc.to_dict().get("date") for doc in db.collection(COLLECTION).stream()}
    print(f"Firestore에 이미 있는 데이터: {len(seen)}개")

    added, skipped_existing = 0, 0
    problems = []  # (줄 번호, 이유)
    batch, pending = db.batch(), 0

    # utf-8-sig: 엑셀에서 저장한 CSV 맨 앞의 BOM이 있어도 안전하게 읽는다
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        missing_columns = {"date", "value"} - set(reader.fieldnames or [])
        if missing_columns:
            sys.exit(f"CSV에 필요한 열이 없습니다: {sorted(missing_columns)} (필요: date, value, memo)")

        for line_no, row in enumerate(reader, start=2):  # 1번째 줄은 머리글
            try:
                item = parse_row(row)
            except ValueError as e:
                problems.append((line_no, str(e)))
                continue

            if item["date"] in seen:
                skipped_existing += 1
                continue

            batch.set(db.collection(COLLECTION).document(), item)
            seen.add(item["date"])  # CSV 안에서 같은 날짜가 두 번 나와도 한 번만 저장
            added += 1
            pending += 1

            if pending >= BATCH_SIZE:
                batch.commit()
                batch, pending = db.batch(), 0
                print(f"{added}개 저장 완료...")

    if pending:
        batch.commit()

    print("\n===== 결과 =====")
    print(f"새로 저장: {added}개")
    print(f"이미 있어서 건너뜀: {skipped_existing}개")
    print(f"형식 오류로 제외: {len(problems)}개")
    for line_no, reason in problems[:20]:
        print(f"  - {line_no}번째 줄: {reason}")
    if len(problems) > 20:
        print(f"  ... 외 {len(problems) - 20}개")


if __name__ == "__main__":
    main()
