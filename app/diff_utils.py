import re


def split_sentences(text: str) -> list[str]:
    if not text or not text.strip():
        return []
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    return [s.strip() for s in sentences if s.strip()]


def make_body_diff(current_text: str, previous_text: str) -> dict:
    current_sentences = split_sentences(current_text or "")
    previous_sentences = split_sentences(previous_text or "")

    current_set = set(current_sentences)
    previous_set = set(previous_sentences)

    added = [s for s in current_sentences if s not in previous_set]
    removed = [s for s in previous_sentences if s not in current_set]

    return {
        "changed": len(added) > 0 or len(removed) > 0,
        "added_sentences": added,
        "removed_sentences": removed,
        "current_sentence_count": len(current_sentences),
        "previous_sentence_count": len(previous_sentences),
    }