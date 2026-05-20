import json
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from urllib.parse import urljoin

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup

from app.scraper import parse_article_content


# ------------------------------------------------------------------ #
# 스레드 로컬 Session
# ThreadPoolExecutor 워커마다 독립적인 Session을 가져
# TCP/TLS 연결을 재사용하면서도 스레드 안전성을 유지한다.
# ------------------------------------------------------------------ #
_thread_local = threading.local()

MAX_WORKERS = 8  # 동시 요청 수. 너무 높으면 대상 서버가 429/403으로 응답할 수 있음.


def _get_session() -> requests.Session:
    if not hasattr(_thread_local, "session"):
        s = requests.Session()
        adapter = HTTPAdapter(
            max_retries=Retry(
                total=2,
                backoff_factor=1,
                status_forcelist=[429, 500, 502, 503, 504],
                allowed_methods=["GET"],
            ),
            pool_connections=4,
            pool_maxsize=MAX_WORKERS,
        )
        s.mount("https://", adapter)
        s.mount("http://", adapter)
        s.headers.update({"User-Agent": "Mozilla/5.0"})
        _thread_local.session = s
    return _thread_local.session


# ------------------------------------------------------------------ #
# 유틸
# ------------------------------------------------------------------ #

def normalize_text(value: str) -> str:
    return " ".join((value or "").split()).strip()


def fetch_html(url: str) -> str:
    """뉴스룸 메인 페이지 HTML을 가져온다."""
    session = _get_session()
    response = session.get(url, timeout=20)
    response.raise_for_status()
    return response.text


def check_landing_status(url: str):
    """상태코드만 확인하던 기존 함수.
    현재 엔진 내부에서는 fetch_landing_info로 대체되었으나
    호환성을 위해 남겨둔다."""
    if not url:
        return None, False, "EMPTY"

    session = _get_session()
    try:
        response = session.head(url, timeout=15, allow_redirects=True)
        status_code = response.status_code

        if status_code >= 400 or status_code == 405:
            response = session.get(url, timeout=15, allow_redirects=True)
            status_code = response.status_code

        return status_code, 200 <= status_code < 400, None
    except Exception as e:
        return None, False, str(e)


def _extract_meta_published_date(soup: BeautifulSoup) -> tuple:
    """<meta property="article:published_time"> 태그에서 발행일 추출.
    삼성 뉴스룸 기사 페이지의 가장 신뢰할 수 있는 날짜 소스.
    예: content="2026-05-13T09:00:00+09:00" → ("2026-05-13", "2026-05-13")"""
    meta = soup.find("meta", attrs={"property": "article:published_time"})
    if not meta:
        return None, None
    content = (meta.get("content") or "").strip()
    if len(content) < 10:
        return None, None
    date_part = content[:10]  # "2026-05-13T09:00:00+09:00" → "2026-05-13"
    try:
        normalized = datetime.strptime(date_part, "%Y-%m-%d").strftime("%Y-%m-%d")
        return date_part, normalized
    except ValueError:
        return None, None


def _detect_article_page(soup: BeautifulSoup) -> bool:
    """기사 페이지 여부 판단. True=기사, False=홈페이지/섹션/미디어라이브러리 등.
    og:type=article, article:published_time, 또는 기사 본문 컨테이너 존재 여부로 판단."""
    og_type = soup.find("meta", attrs={"property": "og:type"})
    if og_type and "article" in (og_type.get("content") or "").lower():
        return True
    if soup.find("meta", attrs={"property": "article:published_time"}):
        return True
    if soup.select_one("div.content_view, div.single_container"):
        return True
    return False


def fetch_landing_info(url: str):
    """랜딩 URL을 GET 한 번으로 방문해
    (status_code, landing_ok, landing_error, published_at_raw, published_at_normalized) 반환.

    날짜 추출 순서:
    1. <meta property="article:published_time"> — 삼성 뉴스룸 기사의 가장 신뢰할 수 있는 소스
    2. parse_article_content 텍스트 기반 fallback
    3. 날짜 없고 비기사 페이지 → published_at_normalized = "home-page" 센티넬 값

    published_at_normalized 값 의미:
    - "YYYY-MM-DD" : 기사 발행일
    - "home-page"  : 기사가 아닌 홈페이지/섹션 페이지 (날짜 없음)
    - None         : 구 스냅샷이거나 날짜 파싱 실패 (표시 시 제목만 노출)
    """
    if not url:
        return None, False, "EMPTY", None, None

    session = _get_session()
    try:
        response = session.get(url, timeout=20, allow_redirects=True)
        status_code = response.status_code
        landing_ok = 200 <= status_code < 400

        published_at_raw = None
        published_at_normalized = None

        if landing_ok:
            soup = BeautifulSoup(response.text, "html.parser")

            # 1차: article:published_time meta 태그 (삼성 뉴스룸 기사 표준)
            published_at_raw, published_at_normalized = _extract_meta_published_date(soup)

            # 2차: scraper의 텍스트 기반 파싱 fallback
            if not published_at_normalized:
                try:
                    article = parse_article_content(response.text)
                    published_at_raw = article.get("published_at_raw")
                    published_at_normalized = article.get("published_at_normalized")
                except Exception:
                    pass

            # 날짜를 끝내 찾지 못한 경우: 기사 페이지가 아니면 "home-page" 마킹
            if not published_at_normalized:
                if not _detect_article_page(soup):
                    published_at_normalized = "home-page"

        return status_code, landing_ok, None, published_at_raw, published_at_normalized

    except Exception as e:
        return None, False, str(e), None, None


def extract_background_image(style_value: str) -> str | None:
    if not style_value:
        return None
    match = re.search(
        r'background-image\s*:\s*url\((["\']?)(.*?)\1\)',
        style_value,
        re.IGNORECASE,
    )
    return match.group(2).strip() if match else None


# ------------------------------------------------------------------ #
# 병렬 fetch 코어
# ------------------------------------------------------------------ #

def _fill_landing_info_parallel(stubs: list[dict]) -> None:
    """슬롯 스텁 리스트의 landing_url을 ThreadPoolExecutor로 병렬 GET.

    동작:
    - 중복 URL은 딱 한 번만 요청 (dedupe 후 호출하면 더 줄어든다)
    - 결과를 스텁 dict에 in-place로 채운다 (반환값 없음)
    - landing_url이 None인 슬롯은 즉시 기본값으로 채운다
    """
    unique_urls = [u for u in {s.get("landing_url") for s in stubs} if u]

    results_map: dict[str, tuple] = {}
    if unique_urls:
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            future_to_url = {
                executor.submit(fetch_landing_info, url): url
                for url in unique_urls
            }
            for future in as_completed(future_to_url):
                url = future_to_url[future]
                try:
                    results_map[url] = future.result()
                except Exception as e:
                    results_map[url] = (None, False, str(e), None, None)

    for stub in stubs:
        url = stub.get("landing_url")
        if url and url in results_map:
            sc, ok, err, pub_raw, pub_norm = results_map[url]
        else:
            sc, ok, err, pub_raw, pub_norm = None, False, "URL 없음", None, None

        stub.update({
            "landing_status_code": sc,
            "landing_ok": ok,
            "landing_error": err,
            "published_at_raw": pub_raw,
            "published_at_normalized": pub_norm,
        })


def dedupe_by_content(items: list[dict]) -> list[dict]:
    seen = set()
    deduped = []
    for item in items:
        key = "||".join([
            normalize_text(item.get("landing_url", "")),
            normalize_text(item.get("image_url", "")),
            normalize_text(item.get("title", "")),
        ])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    for idx, item in enumerate(deduped, start=1):
        item["slot"] = idx
    return deduped


# ------------------------------------------------------------------ #
# gen2 스텁 추출 (HTML 파싱만, 네트워크 없음)
# ------------------------------------------------------------------ #

def _extract_kv_gen2_stubs(soup: BeautifulSoup, page_url: str) -> list[dict]:
    stubs = []
    for li in soup.select("#kv_area .kv_main ul > li"):
        a = li.find("a")
        if not a:
            continue
        landing_url = urljoin(page_url, a.get("href")) if a.get("href") else None
        title_el = li.select_one(".title")
        title = title_el.get_text(" ", strip=True) if title_el else ""
        bg_holder = li.select_one(".thumb > div")
        image_url = None
        if bg_holder:
            bg_url = extract_background_image(bg_holder.get("style", ""))
            image_url = urljoin(page_url, bg_url) if bg_url else None
        stubs.append({
            "slot": len(stubs) + 1,
            "landing_url": landing_url,
            "image_url": image_url,
            "title": title,
        })
    return stubs


def _extract_banner_gen2_stubs(soup: BeautifulSoup, page_url: str) -> list[dict]:
    stubs = []
    for li in soup.select("#side .banner_area li"):
        a = li.select_one("a.banner") or li.find("a")
        if not a:
            continue
        landing_url = urljoin(page_url, a.get("href")) if a.get("href") else None
        title = a.get("title", "").strip()
        thumb_wrap = li.select_one(".thumb_wrap")
        image_url = None
        if thumb_wrap:
            bg_url = extract_background_image(thumb_wrap.get("style", ""))
            image_url = urljoin(page_url, bg_url) if bg_url else None
        stubs.append({
            "slot": len(stubs) + 1,
            "landing_url": landing_url,
            "image_url": image_url,
            "title": title,
        })
    return stubs


# ------------------------------------------------------------------ #
# gen3 스텁 추출 (HTML 파싱만, 네트워크 없음)
# ------------------------------------------------------------------ #

def _extract_main_visual_links_stubs(main_visual_item, page_url: str) -> list[dict]:
    stubs = []

    main_anchor = main_visual_item.select_one("a.visual-main")
    if main_anchor:
        title_el = main_anchor.select_one(".title")
        title = title_el.get_text(" ", strip=True) if title_el else ""
        img = main_anchor.select_one("img.desktop") or main_anchor.select_one("img")
        image_url = urljoin(page_url, img.get("src")) if img and img.get("src") else None
        landing_url = urljoin(page_url, main_anchor.get("href")) if main_anchor.get("href") else None
        stubs.append({
            "slot": 0,
            "landing_url": landing_url,
            "image_url": image_url,
            "title": title,
        })

    for anchor in main_visual_item.select(".case02-sub a.item.visual-image"):
        title_el = anchor.select_one(".title")
        title = title_el.get_text(" ", strip=True) if title_el else ""
        img = anchor.select_one("img")
        image_url = urljoin(page_url, img.get("src")) if img and img.get("src") else None
        landing_url = urljoin(page_url, anchor.get("href")) if anchor.get("href") else None
        stubs.append({
            "slot": 0,
            "landing_url": landing_url,
            "image_url": image_url,
            "title": title,
        })

    return stubs


def _extract_kv_gen3_stubs(soup: BeautifulSoup, page_url: str) -> list[dict]:
    stubs = []
    for visual_item in soup.select(".main-visual-item"):
        if "slick-cloned" in visual_item.get("class", []):
            continue
        stubs.extend(_extract_main_visual_links_stubs(visual_item, page_url))
    return stubs


def _extract_banner_gen3_stubs(soup: BeautifulSoup, page_url: str) -> list[dict]:
    stubs = []
    for item in soup.select(".carousel_slide_item"):
        if "slick-cloned" in item.get("class", []):
            continue
        a = item.find("a")
        if not a:
            continue
        landing_url = urljoin(page_url, a.get("href")) if a.get("href") else None
        title_el = a.select_one(".title")
        title = title_el.get_text(" ", strip=True) if title_el else ""
        img = a.select_one("img")
        image_url = urljoin(page_url, img.get("src")) if img and img.get("src") else None
        stubs.append({
            "slot": len(stubs) + 1,
            "landing_url": landing_url,
            "image_url": image_url,
            "title": title,
        })
    return stubs


# ------------------------------------------------------------------ #
# 메인 추출 진입점
# 흐름: HTML 파싱 → 중복제거 → 병렬 fetch → 결과 채우기
# ------------------------------------------------------------------ #

def extract_by_generation(html: str, page_url: str, generation: str):
    soup = BeautifulSoup(html, "html.parser")
    title_tag = soup.find("title")
    page_title = title_tag.get_text(" ", strip=True) if title_tag else ""

    if generation == "gen2":
        kv_stubs = dedupe_by_content(_extract_kv_gen2_stubs(soup, page_url))
        banner_stubs = dedupe_by_content(_extract_banner_gen2_stubs(soup, page_url))
    elif generation == "gen3":
        kv_stubs = dedupe_by_content(_extract_kv_gen3_stubs(soup, page_url))
        banner_stubs = dedupe_by_content(_extract_banner_gen3_stubs(soup, page_url))
    else:
        raise ValueError(f"지원하지 않는 generation: {generation}")

    # KV + 배너를 합쳐서 한 번에 병렬 fetch
    # 같은 URL은 1회만 요청하고, in-place 업데이트라 kv_stubs/banner_stubs에 자동 반영
    _fill_landing_info_parallel(kv_stubs + banner_stubs)

    return page_title, kv_stubs, banner_stubs


# ------------------------------------------------------------------ #
# 변경 비교 (기존 로직 그대로)
# ------------------------------------------------------------------ #

def compare_slot_items(previous_items: list[dict], current_items: list[dict]) -> dict:
    prev_map = {item["slot"]: item for item in previous_items}
    curr_map = {item["slot"]: item for item in current_items}

    max_slot = max(list(prev_map.keys()) + list(curr_map.keys()) + [0])

    slot_results = []
    changed_count = 0
    error_count = 0

    for slot in range(1, max_slot + 1):
        prev_item = prev_map.get(slot)
        curr_item = curr_map.get(slot)

        image_changed = False
        landing_changed = False
        title_changed = False
        landing_error = False

        if prev_item and curr_item:
            image_changed = normalize_text(prev_item.get("image_url")) != normalize_text(curr_item.get("image_url"))
            landing_changed = normalize_text(prev_item.get("landing_url")) != normalize_text(curr_item.get("landing_url"))
            title_changed = normalize_text(prev_item.get("title")) != normalize_text(curr_item.get("title"))
            landing_error = not bool(curr_item.get("landing_ok"))
        elif curr_item and not prev_item:
            image_changed = True
            landing_changed = True
            title_changed = True
            landing_error = not bool(curr_item.get("landing_ok"))
        elif prev_item and not curr_item:
            image_changed = True
            landing_changed = True
            title_changed = True
            landing_error = False

        has_change = image_changed or landing_changed or title_changed or landing_error
        if has_change:
            changed_count += 1
        if landing_error:
            error_count += 1

        slot_results.append({
            "slot": slot,
            "image_changed": image_changed,
            "landing_changed": landing_changed,
            "title_changed": title_changed,
            "landing_error": landing_error,
            "previous": prev_item,
            "current": curr_item,
        })

    return {
        "slot_results": slot_results,
        "changed_count": changed_count,
        "error_count": error_count,
        "current_count": len(current_items),
        "previous_count": len(previous_items),
        "changed": changed_count > 0,
    }


# ------------------------------------------------------------------ #
# 단일 타겟 분석 (기존 시그니처/반환 그대로)
# ------------------------------------------------------------------ #

def analyze_banner_monitor_target(target: dict):
    html = fetch_html(target["page_url"])
    page_title, kv_items, banner_items = extract_by_generation(
        html=html,
        page_url=target["page_url"],
        generation=target["generation"],
    )

    return {
        "region": target["region"],
        "country": target["country"],
        "code": target["code"],
        "url_code": target["url_code"],
        "page_url": target["page_url"],
        "generation": target["generation"],
        "page_title": page_title,
        "kv_items": kv_items,
        "banner_items": banner_items,
        "kv_count": len(kv_items),
        "banner_count": len(banner_items),
    }