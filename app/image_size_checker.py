import os
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from PIL import Image
from io import BytesIO

from app.bitly_client import expand_bitlink


EXCLUDED_EXTENSIONS = {".svg"}


def _get_html(url: str) -> str:
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(url, headers=headers, timeout=20)
    response.raise_for_status()
    return response.text


def _is_excluded_image(url: str) -> bool:
    parsed = urlparse(url)
    path = parsed.path.lower()
    _, ext = os.path.splitext(path)
    return ext in EXCLUDED_EXTENSIONS


def _extract_image_urls(article_url: str, html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    image_urls = []

    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src") or img.get("data-lazy-src")
        if not src:
            continue

        full_url = urljoin(article_url, src)

        if _is_excluded_image(full_url):
            continue

        if full_url not in image_urls:
            image_urls.append(full_url)

    return image_urls


def _get_image_size(image_url: str) -> dict:
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(image_url, headers=headers, timeout=30)
    response.raise_for_status()

    image = Image.open(BytesIO(response.content))
    width, height = image.size

    parsed = urlparse(image_url)
    filename = os.path.basename(parsed.path)

    return {
        "image_url": image_url,
        "filename": filename,
        "width": width,
        "height": height,
        "format": image.format,
    }


def analyze_shortlinks(raw_text: str) -> list[dict]:
    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    results = []

    for line in lines:
        short_url = line
        bitlink = short_url.replace("https://", "").replace("http://", "").rstrip("/")

        article_result = {
            "input_short_url": short_url,
            "bitlink": bitlink,
            "long_url": None,
            "title": None,
            "image_count": 0,
            "images": [],
            "error": None,
        }

        try:
            long_url = expand_bitlink(bitlink)
            article_result["long_url"] = long_url

            html = _get_html(long_url)
            soup = BeautifulSoup(html, "html.parser")

            h1 = soup.find("h1")
            article_result["title"] = h1.get_text(" ", strip=True) if h1 else ""

            image_urls = _extract_image_urls(long_url, html)

            image_items = []
            for image_url in image_urls:
                try:
                    image_items.append(_get_image_size(image_url))
                except Exception as e:
                    image_items.append({
                        "image_url": image_url,
                        "filename": os.path.basename(urlparse(image_url).path),
                        "width": None,
                        "height": None,
                        "format": None,
                        "error": str(e),
                    })

            article_result["images"] = image_items
            article_result["image_count"] = len(image_items)

        except Exception as e:
            article_result["error"] = str(e)

        results.append(article_result)

    return results