import os
from io import BytesIO
from urllib.parse import urlparse, urljoin

import requests
from bs4 import BeautifulSoup
from PIL import Image

from app.bitly_client import expand_bitlink
from app.scraper import fetch_article_html, parse_article_content


def is_svg_url(url: str) -> bool:
    if not url:
        return False
    lowered = url.lower()
    path = urlparse(lowered).path
    return path.endswith(".svg")


def is_youtube_url(url: str) -> bool:
    if not url:
        return False
    lowered = url.lower()
    return (
        "youtube.com/watch" in lowered
        or "youtube.com/shorts/" in lowered
        or "youtube.com/embed/" in lowered
        or "youtu.be/" in lowered
    )


def guess_media_type(url: str) -> str | None:
    if not url:
        return None

    lowered = (url or "").lower()
    path = urlparse(lowered).path

    if path.endswith(".svg"):
        return None
    if path.endswith(".gif"):
        return "gif"
    if path.endswith(".mp4"):
        return "mp4"
    if is_youtube_url(url):
        return "embedded_video"
    return "image"


def filename_from_url(url: str) -> str:
    path = urlparse(url).path
    name = os.path.basename(path)
    return name or "-"


def format_size(size_bytes: int | None) -> str:
    if size_bytes is None:
        return "-"
    if size_bytes >= 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.2f} MB"
    if size_bytes >= 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes} B"


def get_content_length(url: str) -> int | None:
    try:
        res = requests.head(url, timeout=15, allow_redirects=True)
        content_length = res.headers.get("Content-Length")
        if content_length and content_length.isdigit():
            return int(content_length)
    except Exception:
        return None
    return None


def get_media_dimensions(url: str, media_type: str):
    if media_type in {"mp4", "embedded_video"}:
        return None, None

    try:
        res = requests.get(url, timeout=20)
        res.raise_for_status()
        img = Image.open(BytesIO(res.content))
        return img.width, img.height
    except Exception:
        return None, None


def extract_media_urls_from_html(html: str, page_url: str):
    soup = BeautifulSoup(html, "html.parser")
    media_items = []

    # img tags
    for img in soup.find_all("img"):
        src = (
            img.get("src")
            or img.get("data-src")
            or img.get("data-lazy-src")
            or img.get("data-original")
        )
        if src:
            full_url = urljoin(page_url, src)
            if not is_svg_url(full_url):
                media_items.append(full_url)

    # direct video/source tags
    for video in soup.find_all("video"):
        src = video.get("src")
        if src:
            full_url = urljoin(page_url, src)
            if not is_svg_url(full_url):
                media_items.append(full_url)

        for source in video.find_all("source"):
            source_src = source.get("src")
            if source_src:
                full_url = urljoin(page_url, source_src)
                if not is_svg_url(full_url):
                    media_items.append(full_url)

    # iframe embeds
    for iframe in soup.find_all("iframe"):
        src = iframe.get("src")
        if src:
            full_url = urljoin(page_url, src)
            if is_youtube_url(full_url):
                media_items.append(full_url)

    # YouTube shorts/watch/embed links inside anchors
    for a in soup.find_all("a"):
        href = a.get("href")
        if href:
            full_url = urljoin(page_url, href)
            if is_youtube_url(full_url):
                media_items.append(full_url)

    deduped = []
    seen = set()
    for item in media_items:
        if item in seen:
            continue
        seen.add(item)
        deduped.append(item)

    return deduped


def analyze_media_shortlink_batch(input_text: str):
    short_links = [line.strip() for line in input_text.splitlines() if line.strip()]
    results = []
    error_count = 0

    for short_url in short_links:
        bitlink = short_url.replace("https://", "").replace("http://", "").rstrip("/")

        try:
            long_url = expand_bitlink(bitlink)
            html = fetch_article_html(long_url)
            article = parse_article_content(html)
            article_title = article.get("title") or ""

            media_urls = extract_media_urls_from_html(html, long_url)

            if not media_urls:
                results.append({
                    "short_url": short_url,
                    "long_url": long_url,
                    "article_title": article_title,
                    "media_url": None,
                    "media_type": None,
                    "filename": "-",
                    "width": None,
                    "height": None,
                    "size_bytes": None,
                    "size_display": "-",
                    "preview_url": None,
                    "error": "No media found",
                })
                continue

            for media_url in media_urls:
                media_type = guess_media_type(media_url)

                if media_type is None:
                    continue

                if media_type == "embedded_video":
                    results.append({
                        "short_url": short_url,
                        "long_url": long_url,
                        "article_title": article_title,
                        "media_url": media_url,
                        "media_type": media_type,
                        "filename": filename_from_url(media_url),
                        "width": None,
                        "height": None,
                        "size_bytes": None,
                        "size_display": "-",
                        "preview_url": media_url,
                        "error": None,
                    })
                    continue

                size_bytes = get_content_length(media_url)
                width, height = get_media_dimensions(media_url, media_type)

                results.append({
                    "short_url": short_url,
                    "long_url": long_url,
                    "article_title": article_title,
                    "media_url": media_url,
                    "media_type": media_type,
                    "filename": filename_from_url(media_url),
                    "width": width,
                    "height": height,
                    "size_bytes": size_bytes,
                    "size_display": format_size(size_bytes),
                    "preview_url": media_url,
                    "error": None,
                })

        except Exception as e:
            error_count += 1
            results.append({
                "short_url": short_url,
                "long_url": None,
                "article_title": "",
                "media_url": None,
                "media_type": None,
                "filename": "-",
                "width": None,
                "height": None,
                "size_bytes": None,
                "size_display": "-",
                "preview_url": None,
                "error": str(e),
            })

    summary = {
        "total_links": len(short_links),
        "total_media_count": len(results),
        "error_count": error_count,
    }

    return summary, results