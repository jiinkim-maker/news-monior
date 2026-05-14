import time
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from app.config import BITLY_ACCESS_TOKEN

session = requests.Session()

retry_strategy = Retry(
    total=3,
    connect=3,
    read=3,
    backoff_factor=2,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["GET"],
)

adapter = HTTPAdapter(max_retries=retry_strategy)
session.mount("https://", adapter)
session.mount("http://", adapter)


def get_bitlink_info(bitlink: str) -> dict:
    if not BITLY_ACCESS_TOKEN:
        raise ValueError("BITLY_ACCESS_TOKEN이 설정되지 않았습니다.")

    url = f"https://api-ssl.bitly.com/v4/bitlinks/{bitlink}"
    headers = {
        "Authorization": f"Bearer {BITLY_ACCESS_TOKEN}",
        "Content-Type": "application/json",
        "User-Agent": "news-monitor/1.0",
    }

    last_error = None

    for attempt in range(3):
        try:
            response = session.get(url, headers=headers, timeout=(10, 40))
            if not response.ok:
                print("Bitly status_code:", response.status_code)
                print("Bitly response_text:", response.text)

            response.raise_for_status()
            return response.json()

        except requests.exceptions.RequestException as e:
            last_error = e
            print(f"[Bitly Error] attempt={attempt + 1} bitlink={bitlink} error={e}")
            time.sleep(3 * (attempt + 1))

    raise last_error


def expand_bitlink(bitlink: str) -> str:
    data = get_bitlink_info(bitlink)
    long_url = data.get("long_url", "").strip()

    if not long_url:
        raise ValueError("Bitly 응답에서 long_url을 찾지 못했습니다.")

    return long_url