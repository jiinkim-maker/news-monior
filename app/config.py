## 토큰 꺼내쓰는 함수 따로 빼두고 기능화해서 쓰려고 함.

from dotenv import load_dotenv
import os

load_dotenv()

BITLY_ACCESS_TOKEN = os.getenv("BITLY_ACCESS_TOKEN", "").strip()

_forbidden_raw = os.getenv("FORBIDDEN_WORDS", "")
FORBIDDEN_WORDS = [w.strip() for w in _forbidden_raw.split(",") if w.strip()]

if not FORBIDDEN_WORDS:
    FORBIDDEN_WORDS = [
        "iphone",
        "ipad",
    ]