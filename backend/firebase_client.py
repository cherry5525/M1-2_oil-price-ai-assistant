import firebase_admin
from firebase_admin import credentials, firestore
from config import FIREBASE_SERVICE_ACCOUNT_PATH

# serviceAccountKey.json은 backend 폴더 안에 있음
cred = credentials.Certificate(FIREBASE_SERVICE_ACCOUNT_PATH.replace("backend/", ""))
firebase_admin.initialize_app(cred)

db = firestore.client()