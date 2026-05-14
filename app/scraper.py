import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime


def fetch_article_html(long_url: str) -> str:
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(long_url, headers=headers, timeout=20)
    response.raise_for_status()
    return response.text


def _clean_list_text(elements) -> list[str]:
    return [el.get_text(" ", strip=True) for el in elements if el.get_text(" ", strip=True)]


def _extract_meta_texts(soup: BeautifulSoup) -> list[str]:
    texts = []
    for el in soup.select(".meta"):
        text = el.get_text(" ", strip=True)
        if text:
            texts.append(text)
    return texts


def _parse_date_candidates(text: str) -> tuple[str | None, str | None]:
    if not text:
        return None, None

    patterns = [
        r"\b(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})\b",
        r"\b(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{4})\b",
    ]

    for pattern in patterns:
        match = re.search(pattern, text)
        if not match:
            continue

        raw = match.group(0)
        parts = match.groups()

        try:
            if len(parts[0]) == 4:
                year = int(parts[0])
                month = int(parts[1])
                day = int(parts[2])
                normalized = datetime(year, month, day).strftime("%Y-%m-%d")
                return raw, normalized
            else:
                first = int(parts[0])
                second = int(parts[1])
                year = int(parts[2])

                if first > 12:
                    day = first
                    month = second
                elif second > 12:
                    month = first
                    day = second
                else:
                    day = first
                    month = second

                normalized = datetime(year, month, day).strftime("%Y-%m-%d")
                return raw, normalized

        except ValueError:
            continue

    return None, None


def _extract_published_date(soup: BeautifulSoup) -> tuple[str | None, str | None]:
    meta_texts = _extract_meta_texts(soup)

    for text in meta_texts:
        raw, normalized = _parse_date_candidates(text)
        if raw and normalized:
            return raw, normalized

    full_text = soup.get_text(" ", strip=True)
    return _parse_date_candidates(full_text)


def _remove_elements_by_selectors(soup_fragment, selectors: list[str]):
    for selector in selectors:
        for el in soup_fragment.select(selector):
            el.decompose()


def _remove_exact_title_from_body(body_text: str, title: str) -> str:
    if not body_text or not title:
        return body_text

    normalized_body = re.sub(r"\s+", " ", body_text).strip()
    normalized_title = re.sub(r"\s+", " ", title).strip()

    if normalized_body.startswith(normalized_title):
        normalized_body = normalized_body[len(normalized_title):].strip(" -–—:|")
        normalized_body = normalized_body.strip()

    return normalized_body


def _extract_body_text(content, title: str = "") -> str:
    if not content:
        return ""

    body_clone = BeautifulSoup(str(content), "html.parser")

    selectors_to_remove = [
        "script",
        "style",
        "h1",
        "h2.title",
        "h3.title",
        ".title",
        ".article_title",
        ".entry-title",
        ".post-title",
        ".headline",
        ".meta",
        ".date",
        ".byline",
        ".author",
        "p.wp-caption-text",
        "figcaption",
        ".caption",
        ".image-caption",
        ".share",
        ".share_area",
        ".sns_area",
        ".single_share",
        ".article-share",
        ".at-share-btn-elements",
        ".icon_box",
        ".btn_share",
        ".hash",
        ".tag",
        ".tags",
        ".category",
        ".categories",
        "nav",
        "aside",
    ]

    _remove_elements_by_selectors(body_clone, selectors_to_remove)

    body_text = body_clone.get_text(" ", strip=True)
    body_text = re.sub(r"\s+", " ", body_text).strip()
    body_text = _remove_exact_title_from_body(body_text, title)

    return body_text


def parse_article_content(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")

    h1 = soup.find("h1")
    title = h1.get_text(" ", strip=True) if h1 else ""

    content = soup.select_one("div.content_view")
    if not content:
        content = soup.select_one("div.single_container")

    body = _extract_body_text(content, title=title)

    tags = []
    tag_container = soup.select_one("p.hash")
    if tag_container:
        tag_links = tag_container.select('a[rel="tag"]')
        tags = _clean_list_text(tag_links)

    categories = []
    current_category = soup.select("span.now")
    if current_category:
        categories = _clean_list_text(current_category)

    caption_elements = soup.select("p.wp-caption-text, figcaption, .caption, .image-caption")
    captions = _clean_list_text(caption_elements)

    published_at_raw, published_at_normalized = _extract_published_date(soup)

    return {
        "title": title,
        "body": body,
        "tags": tags,
        "categories": categories,
        "captions": captions,
        "published_at_raw": published_at_raw,
        "published_at_normalized": published_at_normalized,
    }