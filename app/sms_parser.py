import re
from app.parser import extract_short_url, normalize_bitlink

TIMESTAMP_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}")
REGION_PATTERN = re.compile(r"\[([A-Z]{2})\]")

def split_sms_blocks(raw_text: str) -> list[str]:
    blocks = re.split(r"\n\s*\n", raw_text.strip())
    return [block.strip() for block in blocks if block.strip()]

def parse_sms_block(block: str) -> dict | None:
    lines = [line.strip() for line in block.splitlines() if line.strip()]
    if len(lines) < 2:
        return None

    timestamp_line = lines[0]
    message_line = " ".join(lines[1:])

    if not TIMESTAMP_PATTERN.search(timestamp_line):
        return None

    timestamp = timestamp_line[:19]

    region_match = REGION_PATTERN.search(message_line)
    region = region_match.group(1) if region_match else "UNKNOWN"

    short_url = extract_short_url(message_line)
    if not short_url:
        return None

    bitlink = normalize_bitlink(short_url)

    return {
        "received_at": timestamp,
        "region": region,
        "raw_block": block,
        "message": message_line,
        "short_url": short_url,
        "bitlink": bitlink,
    }

def parse_sms_dump(raw_text: str) -> list[dict]:
    blocks = split_sms_blocks(raw_text)
    results = []

    for block in blocks:
        parsed = parse_sms_block(block)
        if parsed:
            results.append(parsed)

    return results

def deduplicate_messages(messages: list[dict]) -> tuple[list[dict], int]:
    seen = set()
    unique = []
    duplicate_count = 0

    for msg in messages:
        key = msg["bitlink"]
        if key in seen:
            duplicate_count += 1
            continue
        seen.add(key)
        unique.append(msg)

    return unique, duplicate_count