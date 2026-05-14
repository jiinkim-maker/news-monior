#    message = "[Web발신] [IN_EN] From Kapil Sharma to Khatra Khatra Khatra:... https://bit.ly/3PWFD9M"
#  message = "[Web발신] [TW] 三星擴展One UI... https://bit.ly/3OgmSxs"

# 터미널이 너무 지저분해져서, 테스트 할때는 문자열 기준 앞 500자만 출력만.

from app.parser import extract_short_url, normalize_bitlink
from app.bitly_client import expand_bitlink
from app.scraper import fetch_article_html, parse_article_content
from app.checker import find_forbidden_words


def print_findings(findings: list[dict], section_title: str):
    print(f"\n=== {section_title} ===")
    if not findings:
        print("금지어 없음")
        return

    for item in findings:
        print(f"\n- 금지어: {item['word']}")
        print(f"  위치: {', '.join(item['locations'])}")
        print(f"  제목 등장 횟수: {item['title_count']}")
        print(f"  본문 등장 횟수: {item['body_count']}")
        print(f"  태그 등장 횟수: {item['tag_count']}")
        print(f"  카테고리 등장 횟수: {item['category_count']}")
        print(f"  캡션 등장 횟수: {item['caption_count']}")
        print(f"  총 등장 횟수: {item['total_count']}")

        if item.get("title_sentences"):
            print("  [제목 검출 문장]")
            for sentence in item["title_sentences"][:3]:
                print(f"   - {sentence}")

        if item.get("body_sentences"):
            print("  [본문 검출 문장]")
            for sentence in item["body_sentences"][:5]:
                print(f"   - {sentence}")

        if item.get("matched_tags"):
            print("  [태그 검출]")
            for tag in item["matched_tags"]:
                print(f"   - {tag}")

        if item.get("matched_categories"):
            print("  [카테고리 검출]")
            for category in item["matched_categories"]:
                print(f"   - {category}")

        if item.get("matched_captions"):
            print("  [캡션 검출]")
            for caption in item["matched_captions"]:
                print(f"   - {caption}")


def run():
    message = "[Web발신] [IN_EN] From Kapil Sharma to Khatra Khatra Khatra:... https://bit.ly/3PWFD9M"

    short_url = extract_short_url(message)
    if not short_url:
        print("문자에서 URL을 찾지 못했습니다.")
        return

    bitlink = normalize_bitlink(short_url)

    print("=== 1. URL 처리 ===")
    print("문자에서 추출한 URL:", short_url)
    print("Bitly에 보낼 값:", bitlink)

    try:
        long_url = expand_bitlink(bitlink)
    except Exception as e:
        print("Bitly 원문 URL 확장 중 오류가 발생했습니다.")
        print("오류 내용:", e)
        return

    print("원문 URL:", long_url)

    try:
        html = fetch_article_html(long_url)
    except Exception as e:
        print("기사 HTML 요청 중 오류가 발생했습니다.")
        print("오류 내용:", e)
        return

    article = parse_article_content(html)

    title = article.get("title", "").strip()
    body = article.get("body", "").strip()
    tags = article.get("tags", [])
    categories = article.get("categories", [])
    captions = article.get("captions", [])

    print("\n=== 2. 기사 추출 결과 ===")
    print("제목:", title if title else "[제목 없음]")
    print("본문 글자 수:", len(body))
    print("태그:", tags if tags else "[태그 없음]")
    print("카테고리:", categories if categories else "[카테고리 없음]")
    print("캡션:", captions if captions else "[캡션 없음]")

    findings = find_forbidden_words(title, body, tags, categories, captions)
    print_findings(findings, "3. 금지어 탐지 결과")


if __name__ == "__main__":
    run()