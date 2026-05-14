import re
from app.db import get_active_forbidden_words, get_active_required_words


def split_sentences(text: str) -> list[str]:
    if not text or not text.strip():
        return []

    normalized = re.sub(r"\s+", " ", text).strip()

    sentences = re.split(
        r'(?<=[.!?])\s+|(?<=다\.)\s+|(?<=요\.)\s+|[\n\r]+|(?<=•)\s+|(?<=·)\s+|(?<=►)\s+|(?<=▶)\s+|(?<=▲)\s+',
        normalized
    )

    return [s.strip() for s in sentences if s.strip()]


def count_occurrences(text: str, phrase: str) -> int:
    if not text or not phrase:
        return 0
    return text.lower().count(phrase.lower())


def extract_body_occurrence_sentences(body: str, phrase: str) -> list[str]:
    """
    body_count는 전체 등장 횟수 기준으로 유지하되,
    문장 출력은 중복 없이 한 번만 반환한다.
    즉 한 문장에 phrase가 여러 번 있어도 문장은 1개만 반환.
    """
    if not body or not phrase:
        return []

    sentences = split_sentences(body)
    phrase_lower = phrase.lower()

    results = []
    for sentence in sentences:
        if phrase_lower in sentence.lower():
            results.append(sentence)

    return results


def find_forbidden_words(
    title: str,
    body: str,
    tags: list[str],
    categories: list[str],
    captions: list[str],
) -> list[dict]:
    forbidden_words = get_active_forbidden_words()
    results = []

    title_lower = (title or "").lower()
    body_lower = (body or "").lower()

    for word in forbidden_words:
        word_lower = word.lower()

        title_count = title_lower.count(word_lower)
        body_count = body_lower.count(word_lower)

        matched_tags = [tag for tag in (tags or []) if word_lower in tag.lower()]
        matched_categories = [c for c in (categories or []) if word_lower in c.lower()]
        matched_captions = [c for c in (captions or []) if word_lower in c.lower()]

        tag_count = len(matched_tags)
        category_count = len(matched_categories)
        caption_count = len(matched_captions)

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

        if locations:
            results.append({
                "word": word,
                "locations": locations,
                "title_count": title_count,
                "body_count": body_count,
                "tag_count": tag_count,
                "category_count": category_count,
                "caption_count": caption_count,
                "total_count": title_count + body_count + tag_count + category_count + caption_count,
                "body_occurrence_sentences": extract_body_occurrence_sentences(body or "", word),
            })

    return results


def find_missing_required_words(
    title: str,
    body: str,
    tags: list[str],
    categories: list[str],
    captions: list[str],
) -> list[dict]:
    required_words = get_active_required_words()
    results = []

    combined_parts = [
        title or "",
        body or "",
        " ".join(tags or []),
        " ".join(categories or []),
        " ".join(captions or []),
    ]
    combined_text = " ".join(combined_parts).lower()

    for word in required_words:
        word_lower = word.lower()
        found = word_lower in combined_text

        if not found:
            results.append({
                "word": word,
                "reason": "missing",
            })

    return results