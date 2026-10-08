import pandas as pd
from firebase_client import db

df = pd.read_csv("gimhae_gasoline_final.csv")
df["memo"] = df["memo"].fillna("")  # NaN 방지

count = 0
for _, row in df.iterrows():
    db.collection("data").add({
        "date": row["date"],
        "value": float(row["value"]),
        "memo": row["memo"],
    })
    count += 1
    if count % 100 == 0:
        print(f"{count}개 저장 완료...")

print(f"전체 완료! 총 {count}개 데이터가 Firestore에 저장되었습니다.")