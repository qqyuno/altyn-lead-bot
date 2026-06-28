#!/usr/bin/env python3
import argparse
import csv
import html
import re
import sys
import time
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path


BING_SEARCH_URL = "https://www.bing.com/search"
BESTCHANGE_URL = "https://www.bestchange.ru/tether-trc20-to-sberbank.html"
DUCKDUCKGO_HTML_URL = "https://html.duckduckgo.com/html/"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

HEADERS = [
    "Название проекта",
    "Сфера",
    "Telegram",
    "Email",
    "Оценка 1-10 для покупки франшизы",
]

CONTACT_PATHS = ("", "/contacts", "/contact", "/about", "/support", "/help")
SKIP_DOMAINS = {
    "bestchange.ru",
    "exchangesumo.com",
    "google.com",
    "kurs.expert",
    "minfin.com.ua",
    "monitoring-obmennikov.ru",
    "yandex.ru",
    "telegram.org",
    "t.me",
    "vk.com",
    "youtube.com",
    "wikipedia.org",
    "xvideos.com",
    "xvideos.es",
    "xvideos.la",
    "mobile-xvideos.com",
    "coinmarketcap.com",
    "coingecko.com",
    "crypto.com",
    "binance.com",
    "bybit.com",
    "okx.com",
    "kucoin.com",
    "bseindia.com",
    "pinkbike.com",
    "zhihu.com",
}

BLOCKED_DOMAIN_SUFFIXES = (".ua", ".ge")

NON_TARGET_MARKERS = (
    "агрегатор обменников",
    "каталог обменников",
    "мониторинг обменников",
    "рейтинг обменников",
    "сравнение обменников",
    "compare exchange rates",
    "exchange monitoring",
    "exchanger monitor",
    "list of exchangers",
    "моніторинг обмінників",
    "рейтинг обмінників",
    "топ криптообмінників",
    "информационный портал о криптовалютах",
    "новости криптовалют",
    "обзоры криптовалют",
    "рейтинги криптобирж",
)

TARGET_TITLE_MARKERS = (
    "crypto",
    "exchange",
    "exchanger",
    "otc",
    "usdt",
    "wallet",
    "крипто",
    "кошелек",
    "кошелёк",
    "обмен",
    "обмін",
)

EDITORIAL_TITLE_MARKERS = (
    "how to ",
    "what is ",
    "как купить",
    "как обменять",
    "курс валют",
    "новости",
    "объявления",
    "оголошення",
    "криптобиржи, обменники",
    "лучшие обменники",
    "список обменников",
)

EMAIL_RE = re.compile(r"[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}")
TG_LINK_RE = re.compile(r"(?:https?://)?(?:t\.me|telegram\.me)/([A-Za-z0-9_]{4,32})", re.I)
TG_HANDLE_RE = re.compile(r"(?<!\w)@([A-Za-z0-9_]{4,32})(?!\w)")


class TitleParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag == "title":
            self._in_title = True

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data.strip() + " "


class DuckDuckGoResultParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag != "a":
            return
        attributes = dict(attrs)
        classes = attributes.get("class", "").split()
        href = attributes.get("href", "")
        if "result__a" in classes and href:
            self.links.append(href)


def fetch(url, timeout=5):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        content_type = response.headers.get("Content-Type", "")
        raw = response.read(1_000_000)
    if "text" not in content_type and "html" not in content_type and "xml" not in content_type:
        return ""
    encoding = "utf-8"
    match = re.search(r"charset=([\w-]+)", content_type, re.I)
    if match:
        encoding = match.group(1)
    return raw.decode(encoding, errors="ignore")


def domain_of(url):
    host = urllib.parse.urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def base_url(url):
    parsed = urllib.parse.urlparse(url)
    return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, "", "", "", ""))


def clean_url(url):
    url = html.unescape(url)
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return ""
    return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))


def is_skipped(url):
    domain = domain_of(url)
    if domain.endswith(BLOCKED_DOMAIN_SUFFIXES):
        return True
    return any(domain == item or domain.endswith("." + item) for item in SKIP_DOMAINS)


def read_lines(path):
    file_path = Path(path)
    if not file_path.exists():
        return []
    return [
        line.strip()
        for line in file_path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def search_bing_html(query, max_results):
    params = urllib.parse.urlencode(
        {"q": query, "setlang": "ru", "cc": "RU", "mkt": "ru-RU"}
    )
    html_text = fetch(f"{BING_SEARCH_URL}?{params}", timeout=20)
    links = re.findall(
        r'<li[^>]*class="[^"]*\bb_algo\b[^"]*"[^>]*>[\s\S]*?'
        r'<h2[^>]*>[\s\S]*?<a[^>]+href="([^"]+)"',
        html_text,
        flags=re.I,
    )
    results = []
    seen = set()
    for link in links:
        url = clean_url(link)
        if not url or is_skipped(url):
            continue
        domain = domain_of(url)
        if domain in seen:
            continue
        seen.add(domain)
        results.append(url)
        if len(results) >= max_results:
            break
    return results


def normalize_duckduckgo_url(url):
    url = html.unescape(url)
    if url.startswith("//"):
        url = "https:" + url
    parsed = urllib.parse.urlparse(url)
    if parsed.netloc.endswith("duckduckgo.com") and parsed.path.startswith("/l/"):
        target = urllib.parse.parse_qs(parsed.query).get("uddg", [""])[0]
        return clean_url(target)
    return clean_url(url)


def search_duckduckgo(query, max_results):
    params = urllib.parse.urlencode({"q": query, "kl": "ru-ru"})
    html_text = fetch(f"{DUCKDUCKGO_HTML_URL}?{params}", timeout=20)
    parser = DuckDuckGoResultParser()
    parser.feed(html_text)
    results = []
    seen = set()
    for link in parser.links:
        url = normalize_duckduckgo_url(link)
        if not url or is_skipped(url):
            continue
        domain = domain_of(url)
        if domain in seen:
            continue
        seen.add(domain)
        results.append(url)
        if len(results) >= max_results:
            break
    return results


def resolve_redirect(url, referer=""):
    headers = {"User-Agent": USER_AGENT}
    if referer:
        headers["Referer"] = referer
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=20) as response:
        return clean_url(response.geturl())


def search_bestchange(max_results):
    html_text = fetch(BESTCHANGE_URL, timeout=20)
    rows = re.findall(r'<tr[^>]+onclick="ccl\([^>]+>([\s\S]*?)</tr>', html_text, flags=re.I)
    results = []
    seen = set()
    for row in rows:
        link_match = re.search(r'href="(/click\.php\?[^"]+)"', row, flags=re.I)
        if not link_match:
            continue
        click_url = urllib.parse.urljoin(BESTCHANGE_URL, html.unescape(link_match.group(1)))
        try:
            url = resolve_redirect(click_url, referer=BESTCHANGE_URL)
        except Exception:
            continue
        if not url or is_skipped(url):
            continue
        domain = domain_of(url)
        if not domain or domain in seen or domain.endswith("bestchange.ru"):
            continue
        seen.add(domain)
        results.append(url)
        if len(results) >= max_results:
            break
        time.sleep(0.25)
    return results


def visible_text(html_text):
    text = re.sub(r"<script[\s\S]*?</script>", " ", html_text, flags=re.I)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def page_title(html_text):
    parser = TitleParser()
    parser.feed(html_text)
    return re.sub(r"\s+", " ", parser.title).strip()[:110]


def extract_contacts(text):
    emails = sorted({x.strip(".,;:()[]<>").lower() for x in EMAIL_RE.findall(text)})
    handles = set(TG_LINK_RE.findall(text))
    visible = visible_text(text)
    handles.update(TG_HANDLE_RE.findall(visible))
    excluded_handles = {
        "charset",
        "font",
        "import",
        "keyframes",
        "media",
        "namespace",
        "page",
        "property",
        "share",
        "support",
        "supports",
        "telegram",
        "username",
    }
    telegram = sorted(
        "@" + handle.lstrip("@")
        for handle in handles
        if handle.lower() not in excluded_handles
    )
    return telegram[:3], emails[:3]


def classify_and_score(text, telegram, email):
    low = text.lower()
    score = 1
    sphere = "криптосервис"

    if any(marker in low for marker in NON_TARGET_MARKERS):
        return "нецелевой", 1

    has_exchange = any(x in low for x in ("обменник", "обмен usdt", "exchanger", "exchange"))
    has_otc = any(x in low for x in ("otc", "p2p", "арбитраж"))
    has_fintech = any(x in low for x in ("payment", "gateway", "эквайринг", "платежный шлюз", "pay-in", "pay-out"))
    has_wallet = any(x in low for x in ("wallet", "кошелек", "кошелёк"))
    has_cards = any(x in low for x in ("visa", "mastercard", "виртуальные карты", "card"))
    has_usdt = "usdt" in low or "tether" in low
    has_crypto = any(x in low for x in ("crypto", "крипто", "bitcoin", "btc", "blockchain", "tron", "trc20"))
    has_rub = any(x in low for x in ("rub", "руб", "рубль", "сбп", "карта"))

    if not (has_usdt or has_crypto):
        return "нецелевой", 1

    if has_exchange:
        sphere = "криптообменник"
        score += 3
    elif has_otc:
        sphere = "OTC / арбитраж"
        score += 3
    elif has_fintech:
        sphere = "финтех / платежи"
        score += 2
    elif has_wallet:
        sphere = "криптокошелек"
        score += 2

    if has_usdt and has_rub:
        score += 2
    if has_cards:
        score += 1
    if telegram:
        score += 1
    if email:
        score += 1
    if any(x in low for x in ("резерв", "reserve", "отзывы", "reviews", "support")):
        score += 1

    return sphere, max(1, min(10, score))


def is_target_project(title, text):
    title_low = title.lower()
    text_low = text.lower()
    if not any(marker in title_low for marker in TARGET_TITLE_MARKERS):
        return False
    if any(marker in title_low for marker in EDITORIAL_TITLE_MARKERS):
        return False
    has_crypto = any(marker in text_low for marker in ("usdt", "tether", "crypto", "крипто", "trc20"))
    has_service = any(
        marker in text_low
        for marker in ("обмен", "обмін", "exchange", "exchanger", "otc", "wallet", "кошелек", "кошелёк")
    )
    return has_crypto and has_service


def scan_site(url, scan_pages=3):
    combined = ""
    title = ""
    found_telegram = []
    found_email = []
    root = base_url(url)

    for path in CONTACT_PATHS[:scan_pages]:
        try:
            page = fetch(root + path)
        except Exception:
            continue
        if not page:
            continue
        if not title:
            title = page_title(page)
        text = visible_text(page)
        combined += " " + text[:150_000]
        tg, email = extract_contacts(page + " " + text)
        found_telegram.extend(tg)
        found_email.extend(email)
        if found_telegram or found_email:
            break
        time.sleep(0.2)

    found_telegram = sorted(set(found_telegram))
    found_email = sorted(set(found_email))
    if not is_target_project(title, combined):
        sphere, score = "нецелевой", 1
    else:
        sphere, score = classify_and_score(
            combined + " " + title + " " + domain_of(url),
            found_telegram,
            found_email,
        )
    return {
        "Название проекта": title or domain_of(url),
        "Сфера": sphere,
        "Telegram": ", ".join(found_telegram),
        "Email": ", ".join(found_email),
        "Оценка 1-10 для покупки франшизы": str(score),
    }


def existing_keys(csv_path):
    path = Path(csv_path)
    if not path.exists():
        return set()
    keys = set()
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        for row in reader:
            key = "|".join((row.get("Название проекта", ""), row.get("Telegram", ""), row.get("Email", ""))).lower()
            keys.add(key)
    return keys


def append_rows(csv_path, rows):
    path = Path(csv_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists()
    with path.open("a", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=HEADERS)
        if not exists:
            writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Collect public Altyn franchise leads into a simple CSV.")
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--queries", default=str(Path(__file__).with_name("queries.txt")))
    parser.add_argument("--out", default=str(Path(__file__).with_name("altyn_leads.csv")))
    parser.add_argument("--search-results", type=int, default=10)
    parser.add_argument("--max-queries", type=int, default=5)
    parser.add_argument("--scan-pages", type=int, default=3)
    parser.add_argument("--min-score", type=int, default=5)
    args = parser.parse_args()

    queries = read_lines(args.queries)
    if not queries:
        raise SystemExit("No queries found.")

    keys = existing_keys(args.out)
    rows = []
    seen_domains = set()

    def collect_candidates(candidates):
        for url in candidates:
            if len(rows) >= args.limit:
                break
            domain = domain_of(url)
            if not domain or domain in seen_domains:
                continue
            seen_domains.add(domain)
            print(f"Scanning: {domain}")
            try:
                row = scan_site(url, scan_pages=max(1, min(6, args.scan_pages)))
            except Exception as exc:
                print(f"Scan failed: {exc}")
                continue
            if not row["Telegram"] and not row["Email"]:
                continue
            if row["Сфера"] == "нецелевой":
                continue
            if int(row["Оценка 1-10 для покупки франшизы"]) < args.min_score:
                continue
            key = "|".join((row["Название проекта"], row["Telegram"], row["Email"])).lower()
            if key in keys:
                continue
            keys.add(key)
            rows.append(row)
            print(f"Added: {row['Название проекта']} / {row['Оценка 1-10 для покупки франшизы']}")
            time.sleep(0.4)

    print("Searching: BestChange exchangers")
    try:
        bestchange_candidates = search_bestchange(max(args.limit * 3, 30))
        collect_candidates(bestchange_candidates)
    except Exception as exc:
        print(f"BestChange search failed: {exc}")

    for query in queries[: args.max_queries]:
        if len(rows) >= args.limit:
            break
        print(f"Searching: {query}")
        try:
            candidates = search_bing_html(query, args.search_results)
            if not candidates:
                candidates = search_duckduckgo(query, args.search_results)
        except Exception as exc:
            print(f"Search failed: {exc}")
            continue
        collect_candidates(candidates)

    append_rows(args.out, rows)
    print(f"Done. Added {len(rows)} leads to {args.out}")


if __name__ == "__main__":
    main()
