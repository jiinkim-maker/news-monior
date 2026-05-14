## 문자에서 비틀리 숏링크 찾기
## 비틀리 API 숏링크 포맷으로 바꾸기

import re

URL_PATTERN = re.compile(r'https?://[^\s]+|bit\.ly/[^\s]+')

def extract_short_url(message: str) -> str | None:
    match = URL_PATTERN.search(message)
    if not match:
        return None
    return match.group(0).strip()

def normalize_bitlink(short_url: str) -> str:
    url = short_url.strip()
    url = re.sub(r"^https?://", "", url)
    url = url.rstrip("/")
    return url