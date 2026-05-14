import json
import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


def normalize_text(value: str) -> str:
    return " ".join((value or "").split()).strip()


def fetch_html(url: str) -> str:
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(url, headers=headers, timeout=20)
    response.raise_for_status()
    return response.text


def check_landing_status(url: str):
    if not url:
        return None, False, "EMPTY"

    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        response = requests.head(url, headers=headers, timeout=15, allow_redirects=True)
        status_code = response.status_code

        if status_code >= 400 or status_code == 405:
            response = requests.get(url, headers=headers, timeout=15, allow_redirects=True)
            status_code = response.status_code

        return status_code, 200 <= status_code < 400, None
    except Exception as e:
        return None, False, str(e)


def extract_background_image(style_value: str) -> str | None:
    if not style_value:
        return None

    match = re.search(r'background-image\s*:\s*url\((["\']?)(.*?)\1\)', style_value, re.IGNORECASE)
    if match:
        return match.group(2).strip()

    return None


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


# ---------------- gen2 ----------------

def extract_kv_gen2(soup: BeautifulSoup, page_url: str) -> list[dict]:
    items = []

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

        status_code, landing_ok, landing_error = check_landing_status(landing_url)

        items.append({
            "slot": len(items) + 1,
            "landing_url": landing_url,
            "image_url": image_url,
            "title": title,
            "landing_status_code": status_code,
            "landing_ok": landing_ok,
            "landing_error": landing_error,
        })

    return dedupe_by_content(items)


def extract_banner_gen2(soup: BeautifulSoup, page_url: str) -> list[dict]:
    items = []

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

        status_code, landing_ok, landing_error = check_landing_status(landing_url)

        items.append({
            "slot": len(items) + 1,
            "landing_url": landing_url,
            "image_url": image_url,
            "title": title,
            "landing_status_code": status_code,
            "landing_ok": landing_ok,
            "landing_error": landing_error,
        })

    return dedupe_by_content(items)


# ---------------- gen3 ----------------

def extract_main_visual_links(main_visual_item, page_url: str) -> list[dict]:
    sub_items = []

    main_anchor = main_visual_item.select_one("a.visual-main")
    if main_anchor:
        title_el = main_anchor.select_one(".title")
        title = title_el.get_text(" ", strip=True) if title_el else ""

        img = main_anchor.select_one("img.desktop") or main_anchor.select_one("img")
        image_url = urljoin(page_url, img.get("src")) if img and img.get("src") else None
        landing_url = urljoin(page_url, main_anchor.get("href")) if main_anchor.get("href") else None

        status_code, landing_ok, landing_error = check_landing_status(landing_url)

        sub_items.append({
            "slot": 0,
            "landing_url": landing_url,
            "image_url": image_url,
            "title": title,
            "landing_status_code": status_code,
            "landing_ok": landing_ok,
            "landing_error": landing_error,
        })

    for anchor in main_visual_item.select(".case02-sub a.item.visual-image"):
        title_el = anchor.select_one(".title")
        title = title_el.get_text(" ", strip=True) if title_el else ""

        img = anchor.select_one("img")
        image_url = urljoin(page_url, img.get("src")) if img and img.get("src") else None
        landing_url = urljoin(page_url, anchor.get("href")) if anchor.get("href") else None

        status_code, landing_ok, landing_error = check_landing_status(landing_url)

        sub_items.append({
            "slot": 0,
            "landing_url": landing_url,
            "image_url": image_url,
            "title": title,
            "landing_status_code": status_code,
            "landing_ok": landing_ok,
            "landing_error": landing_error,
        })

    return sub_items


def extract_kv_gen3(soup: BeautifulSoup, page_url: str) -> list[dict]:
    items = []

    for visual_item in soup.select(".main-visual-item"):
        classes = visual_item.get("class", [])
        if "slick-cloned" in classes:
            continue
        items.extend(extract_main_visual_links(visual_item, page_url))

    return dedupe_by_content(items)


def extract_banner_gen3(soup: BeautifulSoup, page_url: str) -> list[dict]:
    items = []

    for item in soup.select(".carousel_slide_item"):
        classes = item.get("class", [])
        if "slick-cloned" in classes:
            continue

        a = item.find("a")
        if not a:
            continue

        landing_url = urljoin(page_url, a.get("href")) if a.get("href") else None
        title_el = a.select_one(".title")
        title = title_el.get_text(" ", strip=True) if title_el else ""

        img = a.select_one("img")
        image_url = urljoin(page_url, img.get("src")) if img and img.get("src") else None

        status_code, landing_ok, landing_error = check_landing_status(landing_url)

        items.append({
            "slot": len(items) + 1,
            "landing_url": landing_url,
            "image_url": image_url,
            "title": title,
            "landing_status_code": status_code,
            "landing_ok": landing_ok,
            "landing_error": landing_error,
        })

    return dedupe_by_content(items)


def extract_by_generation(html: str, page_url: str, generation: str):
    soup = BeautifulSoup(html, "html.parser")
    title_tag = soup.find("title")
    page_title = title_tag.get_text(" ", strip=True) if title_tag else ""

    if generation == "gen2":
        kv_items = extract_kv_gen2(soup, page_url)
        banner_items = extract_banner_gen2(soup, page_url)
    elif generation == "gen3":
        kv_items = extract_kv_gen3(soup, page_url)
        banner_items = extract_banner_gen3(soup, page_url)
    else:
        raise ValueError(f"지원하지 않는 generation: {generation}")

    return page_title, kv_items, banner_items


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