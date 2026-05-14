import re
from typing import List, Dict, Tuple

from app.bitly_client import expand_bitlink
from app.scraper import fetch_article_html, parse_article_content


def normalize_whitespace(text: str) -> str:
    return " ".join((text or "").split()).strip()


def split_sentences(text: str) -> List[str]:
    if not text or not text.strip():
        return []

    normalized = normalize_whitespace(text)

    sentences = re.split(
        r'(?<=[.!?])\s+|(?<=다\.)\s+|(?<=요\.)\s+|[\n\r]+',
        normalized
    )

    return [s.strip() for s in sentences if s.strip()]


def build_pattern(keyword: str, match_rule: str):
    escaped = re.escape(keyword)

    if match_rule == "case_insensitive":
        return re.compile(escaped, re.IGNORECASE)

    if match_rule == "exact":
        return re.compile(escaped)

    if match_rule == "all_upper":
        return re.compile(re.escape(keyword.upper()))

    if match_rule == "all_lower":
        return re.compile(re.escape(keyword.lower()))

    if match_rule == "initial_cap":
        transformed = keyword[:1].upper() + keyword[1:].lower() if keyword else keyword
        return re.compile(re.escape(transformed))

    return re.compile(escaped, re.IGNORECASE)


def count_matches(text: str, keyword: str, match_rule: str) -> int:
    if not text or not keyword:
        return 0
    pattern = build_pattern(keyword, match_rule)
    return len(pattern.findall(text))


def filter_matching_items(items: List[str], keyword: str, match_rule: str) -> List[str]:
    if not items:
        return []
    pattern = build_pattern(keyword, match_rule)
    return [item for item in items if pattern.search(item or "")]


def extract_matching_body_sentences(body: str, keyword: str, match_rule: str) -> List[str]:
    sentences = split_sentences(body)
    pattern = build_pattern(keyword, match_rule)

    results = []
    for sentence in sentences:
        if pattern.search(sentence):
            results.append(sentence)

    return results


def find_forbidden_with_rules(
    title: str,
    body: str,
    tags: List[str],
    categories: List[str],
    captions: List[str],
    forbidden_rules: List[Dict],
) -> List[Dict]:
    findings = []

    for rule in forbidden_rules:
        keyword = rule["keyword"]
        match_rule = rule["match_rule"]

        title_count = count_matches(title, keyword, match_rule)
        body_count = count_matches(body, keyword, match_rule)

        matched_tags = filter_matching_items(tags, keyword, match_rule)
        matched_categories = filter_matching_items(categories, keyword, match_rule)
        matched_captions = filter_matching_items(captions, keyword, match_rule)

        tag_count = len(matched_tags)
        category_count = len(matched_categories)
        caption_count = len(matched_captions)

        total_count = title_count + body_count + tag_count + category_count + caption_count

        if total_count == 0:
            continue

        locations = []
        if title_count > 0:
            locations.append("title")
        if body_count > 0:
            locations.append("body")
        if tag_count > 0:
            locations.append("tags")
        if category_count > 0:
            locations.append("categories")
        if caption_count > 0:
            locations.append("captions")

        findings.append({
            "rule_id": rule["id"],
            "word": keyword,
            "match_rule": match_rule,
            "locations": locations,
            "title_count": title_count,
            "body_count": body_count,
            "tag_count": tag_count,
            "category_count": category_count,
            "caption_count": caption_count,
            "total_count": total_count,
            "body_occurrence_sentences": extract_matching_body_sentences(body, keyword, match_rule),
        })

    return findings


def find_missing_required_with_rules(
    title: str,
    body: str,
    tags: List[str],
    categories: List[str],
    captions: List[str],
    required_rules: List[Dict],
) -> List[Dict]:
    missing = []

    combined_parts = [
        title or "",
        body or "",
        " ".join(tags or []),
        " ".join(categories or []),
        " ".join(captions or []),
    ]
    combined_text = " ".join(combined_parts)

    for rule in required_rules:
        keyword = rule["keyword"]
        match_rule = rule["match_rule"]

        found_count = count_matches(combined_text, keyword, match_rule)

        if found_count == 0:
            missing.append({
                "rule_id": rule["id"],
                "word": keyword,
                "match_rule": match_rule,
                "reason": "missing",
            })

    return missing


def analyze_shortlink_batch(
    input_text: str,
    forbidden_rules: List[Dict],
    required_rules: List[Dict],
) -> Tuple[Dict, List[Dict]]:
    short_links = [line.strip() for line in input_text.splitlines() if line.strip()]

    results = []
    flagged_articles = 0
    missing_required_articles = 0
    error_articles = 0

    for short_url in short_links:
        bitlink = short_url.replace("https://", "").replace("http://", "").rstrip("/")

        item = {
            "short_url": short_url,
            "long_url": None,
            "title": None,
            "published_at_raw": None,
            "published_at_normalized": None,
            "body_text": "",
            "tags": [],
            "categories": [],
            "captions": [],
            "forbidden_findings": [],
            "required_missing": [],
            "forbidden_found_count": 0,
            "required_missing_count": 0,
            "status": "clean",
            "error": None,
        }

        try:
            long_url = expand_bitlink(bitlink)
            item["long_url"] = long_url

            html = fetch_article_html(long_url)
            article = parse_article_content(html)

            title = article.get("title", "") or ""
            body = article.get("body", "") or ""
            tags = article.get("tags", []) or []
            categories = article.get("categories", []) or []
            captions = article.get("captions", []) or []

            forbidden_findings = find_forbidden_with_rules(
                title=title,
                body=body,
                tags=tags,
                categories=categories,
                captions=captions,
                forbidden_rules=forbidden_rules,
            )

            required_missing = find_missing_required_with_rules(
                title=title,
                body=body,
                tags=tags,
                categories=categories,
                captions=captions,
                required_rules=required_rules,
            )

            forbidden_found_count = sum(f["total_count"] for f in forbidden_findings)
            required_missing_count = len(required_missing)

            status = "clean"
            if forbidden_found_count > 0 or required_missing_count > 0:
                status = "flagged"

            item["title"] = title
            item["published_at_raw"] = article.get("published_at_raw")
            item["published_at_normalized"] = article.get("published_at_normalized")
            item["body_text"] = body
            item["tags"] = tags
            item["categories"] = categories
            item["captions"] = captions
            item["forbidden_findings"] = forbidden_findings
            item["required_missing"] = required_missing
            item["forbidden_found_count"] = forbidden_found_count
            item["required_missing_count"] = required_missing_count
            item["status"] = status

            if status == "flagged":
                flagged_articles += 1
            if required_missing_count > 0:
                missing_required_articles += 1

        except Exception as e:
            item["status"] = "error"
            item["error"] = str(e)
            error_articles += 1

        results.append(item)

    summary = {
        "input_count": len(short_links),
        "total_links": len(short_links),
        "total_articles": len(results),
        "flagged_articles": flagged_articles,
        "missing_required_articles": missing_required_articles,
        "error_articles": error_articles,
    }

    return summary, results