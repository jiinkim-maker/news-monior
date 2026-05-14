
## For me
## 배너, KV 스크리닝 기능에서 지정되는 뉴스룸별 세대, 국가 코드를 이 페이지 하나에 딕셔너리로 만들어서 꺼내쓸 수 있도록 함.
## 다른 구동 코드는 '엔진.py' 파일에서 수정하면 됨.


BASE_URL = "https://news.samsung.com"

TARGETS_RAW = [
    {"region": "North America", "country": "Canada (English)", "code": "CA", "url_code": "ca", "generation": "gen2"},
    {"region": "North America", "country": "Canada (French)", "code": "CA_FR", "url_code": "ca_fr", "generation": "gen2"},

    {"region": "Europe", "country": "Germany", "code": "DE", "url_code": "de", "generation": "gen2"},
    {"region": "Europe", "country": "U.K.", "code": "UK", "url_code": "uk", "generation": "gen2"},
    {"region": "Europe", "country": "France", "code": "FR", "url_code": "fr", "generation": "gen2"},
    {"region": "Europe", "country": "Italy", "code": "IT", "url_code": "it", "generation": "gen2"},
    {"region": "Europe", "country": "Spain", "code": "ES", "url_code": "es", "generation": "gen2"},
    {"region": "Europe", "country": "Netherlands", "code": "NL", "url_code": "nl", "generation": "gen2"},
    {"region": "Europe", "country": "Belgium (Dutch)", "code": "be", "url_code": "be", "generation": "gen2"},
    {"region": "Europe", "country": "Belgium (French)", "code": "be_fr", "url_code": "be_fr", "generation": "gen2"},
    {"region": "Europe", "country": "Sweden", "code": "SE", "url_code": "se", "generation": "gen2"},
    {"region": "Europe", "country": "Norway", "code": "NO", "url_code": "no", "generation": "gen2"},
    {"region": "Europe", "country": "Poland", "code": "PL", "url_code": "pl", "generation": "gen3"},
    {"region": "Europe", "country": "Romania", "code": "RO", "url_code": "ro", "generation": "gen2"},
    {"region": "Europe", "country": "Switzerland (German)", "code": "ch", "url_code": "ch", "generation": "gen2"},
    {"region": "Europe", "country": "Switzerland (French)", "code": "ch_fr", "url_code": "ch_fr", "generation": "gen2"},
    {"region": "Europe", "country": "Austria", "code": "AT", "url_code": "at", "generation": "gen2"},
    {"region": "Europe", "country": "Czech Republic", "code": "CZ", "url_code": "cz", "generation": "gen2"},
    {"region": "Europe", "country": "Ukraine", "code": "UA", "url_code": "ua", "generation": "gen3"},

    {"region": "South Asia & Oceania", "country": "Japan", "code": "JP", "url_code": "jp", "generation": "gen2"},
    {"region": "South Asia & Oceania", "country": "Singapore", "code": "SG", "url_code": "sg", "generation": "gen2"},
    {"region": "South Asia & Oceania", "country": "Australia", "code": "AU", "url_code": "au", "generation": "gen2"},
    {"region": "South Asia & Oceania", "country": "Philippines", "code": "PH", "url_code": "ph", "generation": "gen2"},
    {"region": "South Asia & Oceania", "country": "Malaysia", "code": "MY", "url_code": "my", "generation": "gen2"},
    {"region": "South Asia & Oceania", "country": "Indonesia", "code": "ID", "url_code": "id", "generation": "gen2"},
    {"region": "South Asia & Oceania", "country": "Thailand", "code": "TH", "url_code": "th", "generation": "gen3"},
    {"region": "South Asia & Oceania", "country": "Vietnam", "code": "VN", "url_code": "vn", "generation": "gen2"},
    {"region": "South Asia & Oceania", "country": "Taiwan", "code": "TW", "url_code": "tw", "generation": "gen2"},

    {"region": "South West Asia", "country": "India (English)", "code": "IN_EN", "url_code": "in", "generation": "gen2"},
    {"region": "South West Asia", "country": "India (Hindi)", "code": "IN_HI", "url_code": "bharat", "generation": "gen2"},

    {"region": "CIS", "country": "Kazakhstan (Kazakh)", "code": "KZ_KK", "url_code": "kz_kz", "generation": "gen2"},
    {"region": "CIS", "country": "Kazakhstan (Russian)", "code": "KZ_RU", "url_code": "kz", "generation": "gen2"},
    {"region": "CIS", "country": "Uzbekistan", "code": "UZ", "url_code": "uz", "generation": "gen2"},
    {"region": "CIS", "country": "Russia", "code": "RU", "url_code": "ru", "generation": "gen2"},

    {"region": "MENA", "country": "Middle East", "code": "ME", "url_code": "mena", "generation": "gen2"},
    {"region": "MENA", "country": "Turkiye", "code": "TR", "url_code": "tr", "generation": "gen2"},

    {"region": "Africa", "country": "South Africa", "code": "ZA", "url_code": "za", "generation": "gen2"},

    {"region": "South America", "country": "Brazil", "code": "BR", "url_code": "br", "generation": "gen2"},
    {"region": "South America", "country": "Mexico", "code": "MX", "url_code": "mx", "generation": "gen2"},
    {"region": "South America", "country": "LatinoAmerica", "code": "LATAM", "url_code": "latin", "generation": "gen2"},
    {"region": "South America", "country": "Colombia", "code": "CO", "url_code": "co", "generation": "gen2"},
    {"region": "South America", "country": "Chile", "code": "CL", "url_code": "cl", "generation": "gen2"},
    {"region": "South America", "country": "Peru", "code": "PE", "url_code": "pe", "generation": "gen2"},
    {"region": "South America", "country": "Argentina", "code": "AR", "url_code": "ar", "generation": "gen2"},
]


def build_page_url(url_code: str) -> str:
    return f"{BASE_URL}/{url_code}/"


def build_monitor_targets() -> list[dict]:
    items = []
    for item in TARGETS_RAW:
        items.append({
            "region": item["region"],
            "country": item["country"],
            "code": item["code"],
            "url_code": item["url_code"],
            "generation": item["generation"],
            "page_url": build_page_url(item["url_code"]),
        })
    return items