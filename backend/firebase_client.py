import json

import firebase_admin
from firebase_admin import credentials, firestore

from config import FIREBASE_SERVICE_ACCOUNT_JSON, FIREBASE_SERVICE_ACCOUNT_PATH


def _build_credentials():
    """서비스 계정 키를 읽는다.

    1) 환경 변수 FIREBASE_SERVICE_ACCOUNT_JSON(키 파일의 내용 전체)이 있으면 그것을 사용 -> 배포(Render)용
    2) 없으면 키 파일 경로를 사용 -> 내 컴퓨터(로컬 개발)용
    """
    if FIREBASE_SERVICE_ACCOUNT_JSON:
        try:
            info = json.loads(FIREBASE_SERVICE_ACCOUNT_JSON)
        except json.JSONDecodeError as e:
            raise RuntimeError(
                "FIREBASE_SERVICE_ACCOUNT_JSON 값이 올바른 JSON이 아닙니다. "
                "키 파일의 내용 전체를 그대로 붙여 넣었는지 확인하세요."
            ) from e
        return credentials.Certificate(info)

    # serviceAccountKey.json은 backend 폴더 안에 있음
    return credentials.Certificate(FIREBASE_SERVICE_ACCOUNT_PATH.replace("backend/", ""))


# 한 번만 초기화 (--reload로 코드가 다시 읽혀도 중복 초기화 방지)
if not firebase_admin._apps:
    firebase_admin.initialize_app(_build_credentials())

db = firestore.client()
