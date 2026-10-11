"""Firestore 'data' 컬렉션에서 같은 날짜가 2번 이상 있는 문서를 찾는 검사 스크립트.
읽기만 하고 아무것도 수정/삭제하지 않습니다.

사용법 (backend 폴더에서): python -m scripts.check_duplicates
"""
from collections import defaultdict
from datetime import date, timedelta

from firebase_client import db  # 변수 이름이 db가 아니면 data.py와 똑같이 맞춰주세요

by_date = defaultdict(list)
for doc in db.collection("data").stream():
    d = doc.to_dict()
    by_date[d.get("date")].append((doc.id, d.get("value"), d.get("memo")))

total = sum(len(v) for v in by_date.values())
print(f"전체 문서 수: {total}")
print(f"서로 다른 날짜 수: {len(by_date)}")

# 1) 같은 날짜가 여러 번 있는 경우
print("\n=== 중복된 날짜 ===")
found = False
for day, items in sorted(by_date.items()):
    if len(items) > 1:
        found = True
        print(f"[{day}] {len(items)}건")
        for doc_id, value, memo in items:
            print(f"   id={doc_id}  value={value}  memo={memo!r}")
if not found:
    print("(없음)")

# 2) 빠진 날짜가 있는 경우
days = sorted(k for k in by_date if k)
start = date.fromisoformat(days[0])
end = date.fromisoformat(days[-1])
missing = []
cur = start
while cur <= end:
    if cur.isoformat() not in by_date:
        missing.append(cur.isoformat())
    cur += timedelta(days=1)

print("\n=== 빠진 날짜 ===")
print(missing if missing else "(없음)")
