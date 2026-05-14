from collections import Counter
from app.sms_parser import parse_sms_dump, deduplicate_messages
from app.bitly_client import expand_bitlink
from app.scraper import fetch_article_html, parse_article_content
from app.checker import find_forbidden_words, find_missing_required_words
from app.db import init_db, save_article_check


def analyze_dump(raw_text: str) -> dict:
    init_db()

    parsed_messages = parse_sms_dump(raw_text)
    unique_messages, duplicate_count = deduplicate_messages(parsed_messages)

    results = []
    region_counter = Counter()
    flagged_region_counter = Counter()

    for msg in unique_messages:
        region = msg["region"]
        region_counter[region] += 1

        item = {
            "received_at": msg["received_at"],
            "region": region,
            "short_url": msg["short_url"],
            "bitlink": msg["bitlink"],
            "long_url": None,
            "title": None,
            "published_at_raw": None,
            "published_at_normalized": None,
            "body_text": "",
            "body_length": 0,
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
            try:
                long_url = expand_bitlink(msg["bitlink"])
            except Exception:
                long_url = msg["short_url"]

            item["long_url"] = long_url

            html = fetch_article_html(long_url)
            article = parse_article_content(html)

            title = article.get("title", "").strip()
            body = article.get("body", "").strip()
            tags = article.get("tags", [])
            categories = article.get("categories", [])
            captions = article.get("captions", [])
            published_at_raw = article.get("published_at_raw")
            published_at_normalized = article.get("published_at_normalized")

            forbidden_findings = find_forbidden_words(title, body, tags, categories, captions)
            required_missing = find_missing_required_words(title, body, tags, categories, captions)

            item["title"] = title
            item["published_at_raw"] = published_at_raw
            item["published_at_normalized"] = published_at_normalized
            item["body_text"] = body
            item["body_length"] = len(body)
            item["tags"] = tags
            item["categories"] = categories
            item["captions"] = captions
            item["forbidden_findings"] = forbidden_findings
            item["required_missing"] = required_missing
            item["forbidden_found_count"] = len(forbidden_findings)
            item["required_missing_count"] = len(required_missing)

            if forbidden_findings or required_missing:
                item["status"] = "flagged"
                flagged_region_counter[region] += 1
            else:
                item["status"] = "clean"

        except Exception as e:
            item["error"] = str(e)
            item["status"] = "error"

        save_article_check(item)
        results.append(item)

    summary = {
        "total_sms": len(parsed_messages),
        "unique_articles": len(unique_messages),
        "duplicate_sms": duplicate_count,
        "flagged_articles": sum(1 for r in results if r["status"] == "flagged"),
        "clean_articles": sum(1 for r in results if r["status"] == "clean"),
        "error_articles": sum(1 for r in results if r["status"] == "error"),
        "region_counts": dict(region_counter),
        "flagged_region_counts": dict(flagged_region_counter),
    }

    return {
        "summary": summary,
        "results": results,
    }