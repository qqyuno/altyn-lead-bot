#!/usr/bin/env python3
import argparse
import concurrent.futures
import csv
import html
import random
import re
import sys
import time
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path


BING_SEARCH_URL = "https://www.bing.com/search"
BESTCHANGE_URLS = (
    "https://www.bestchange.ru/tether-trc20-to-sberbank.html",
    "https://www.bestchange.ru/sberbank-to-tether-trc20.html",
    "https://www.bestchange.ru/tether-trc20-to-tinkoff.html",
    "https://www.bestchange.ru/tinkoff-to-tether-trc20.html",
    "https://www.bestchange.ru/tether-trc20-to-cash-ruble.html",
    "https://www.bestchange.ru/cash-ruble-to-tether-trc20.html",
    "https://www.bestchange.ru/tether-trc20-to-visa-mastercard-rub.html",
    "https://www.bestchange.ru/visa-mastercard-rub-to-tether-trc20.html",
)
MONITORING_SOURCES = (
    ("OKChanger", "https://www.okchanger.ru/"),
    ("OKChanger list", "https://www.okchanger.ru/exchangers"),
    ("WellCrypto", "https://wellcrypto.io/ru/exchangers/monitoring/"),
    ("KursExpert", "https://kurs.expert/"),
    ("Exnode", "https://exnode.ru/"),
    ("RateEx", "https://rateex.ru/"),
    ("Glazok", "https://glazok.org/"),
    ("MonitObmen", "https://monitobmen.ru/"),
)
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

CONTACT_PATHS = (
    "",
    "/contacts",
    "/contact",
    "/contact-us",
    "/partners",
    "/partnership",
    "/affiliate",
    "/cooperation",
    "/business",
    "/about",
    "/team",
    "/support",
    "/help",
)
CONTACT_LINK_MARKERS = (
    "contact",
    "partner",
    "affiliate",
    "cooperat",
    "business",
    "commercial",
    "team",
    "support",
    "help",
    "feedback",
    "telegram",
    "social",
    "контакт",
    "партнер",
    "партнёр",
    "сотруднич",
    "коммерц",
    "команда",
    "поддерж",
    "помощ",
    "соцсет",
    "мессендж",
)
SKIP_DOMAINS = {
    "bestchange.ru",
    "exchangesumo.com",
    "google.com",
    "glazok.org",
    "kurs.expert",
    "minfin.com.ua",
    "monitoring-obmennikov.ru",
    "monitobmen.ru",
    "okchanger.com",
    "okchanger.ru",
    "rateex.ru",
    "wellcrypto.io",
    "exnode.io",
    "exnode.ru",
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

MONITOR_PROFILE_MARKERS = (
    "/exchange/",
    "/exchanger/",
    "/exchangers/",
    "/obmennik/",
    "/review/",
    "/service/",
)
MONITOR_OUTBOUND_TEXT_MARKERS = (
    "continue",
    "exchange",
    "go to",
    "site",
    "website",
    "обменять",
    "перейти",
    "продолжить",
    "сайт",
    "ссылка",
)
MONITOR_REDIRECT_PATH_MARKERS = ("/click", "/go/", "/out/", "/redirect")

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
    "crypto news",
    "cryptocurrency news",
    "what is cryptocurrency",
)

TARGET_TITLE_MARKERS = (
    "academy",
    "affiliate",
    "blog",
    "card",
    "channel",
    "community",
    "crypto",
    "exchange",
    "exchanger",
    "fintech",
    "founder",
    "game",
    "media",
    "otc",
    "payment",
    "startup",
    "steam",
    "trader",
    "trading",
    "usdt",
    "visa",
    "wallet",
    "web3",
    "академ",
    "арбитраж",
    "блог",
    "виртуальн",
    "зарубеж",
    "канал",
    "карт",
    "команд",
    "комьюнити",
    "крипто",
    "кошелек",
    "кошелёк",
    "обмен",
    "обмін",
    "оплат",
    "пополн",
    "подпис",
    "p2p",
    "трафик",
    "traffic",
    "affiliate",
    "cpa",
    "webmaster",
    "вебмастер",
    "стартап",
    "трейдер",
    "трейдинг",
)

EDITORIAL_TITLE_MARKERS = (
    "how to ",
    "what is ",
    "review ",
    "как купить",
    "как обменять",
    "как оформить",
    "как пополнить",
    "курс валют",
    "новости",
    "обзор",
    "лучшие ",
    "топ ",
    "объявления",
    "оголошення",
    "криптобиржи, обменники",
    "лучшие обменники",
    "список обменников",
)

RUBLE_MARKET_MARKERS = (
    "rub",
    ".ru",
    ".рф",
    "руб",
    "рубль",
    "рублей",
    "сбп",
    "мир",
    "карта мир",
    "россия",
    "рф",
    "русский",
    "русск",
    "рунет",
    "москва",
    "санкт-петербург",
    "спб",
    "russian traffic",
    "ru traffic",
)

EXCHANGE_MARKERS = (
    "обменник",
    "криптообменник",
    "обменять usdt",
    "купить usdt",
    "продать usdt",
    "отдаете",
    "получаете",
    "создать заявку",
    "заявка на обмен",
    "резерв",
    "reserve",
    "exchanger",
    "currency exchange",
    "crypto exchange",
)

OTC_P2P_MARKERS = (
    "otc",
    "p2p",
    "p2p desk",
    "p2p trading",
    "p2p арбитраж",
    "крипто арбитраж",
    "арбитраж криптовалют",
    "обнал",
    "наличные",
)

TRAFFIC_TEAM_MARKERS = (
    "арбитраж трафика",
    "traffic arbitrage",
    "crypto traffic",
    "финансовый трафик",
    "cpa",
    "cpa network",
    "affiliate",
    "affiliate marketing",
    "партнерская программа",
    "партнёрская программа",
    "вебмастер",
    "webmaster",
    "leadgen",
    "лидогенерация",
)

PAYMENT_INFRA_MARKERS = (
    "payment gateway",
    "crypto payment gateway",
    "accept crypto payments",
    "merchant",
    "merchants",
    "checkout",
    "invoice",
    "invoices",
    "e-commerce",
    "ecommerce",
    "plugins",
    "plugin",
    "mass payouts",
    "payouts",
    "pay-in",
    "pay-out",
    "эквайринг",
    "платежный шлюз",
    "платёжный шлюз",
    "прием платежей",
    "приём платежей",
)

LOW_INTENT_INFRA_MARKERS = (
    "gift card",
    "gift cards",
    "подарочные карты",
    "licensed",
    "mica",
    "global businesses",
    "global business",
)

EMAIL_RE = re.compile(r"[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}")
TG_LINK_RE = re.compile(
    r"(?:https?://)?(?:t\.me|telegram\.me|telegram\.dog)/([A-Za-z0-9_]{4,32})",
    re.I,
)
TG_HANDLE_RE = re.compile(r"(?<!\w)@([A-Za-z0-9_]{4,32})(?!\w)")
TG_USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{4,32}$")
DOMAIN_IN_TEXT_RE = re.compile(r"\b(?:www\.)?([a-z0-9][a-z0-9-]*(?:\.[a-z0-9-]+)+)\b", re.I)
PUBLIC_EMAIL_DOMAINS = {
    "gmail.com",
    "icloud.com",
    "mail.ru",
    "outlook.com",
    "proton.me",
    "protonmail.com",
    "yahoo.com",
    "yandex.ru",
}
TG_RESERVED_PATHS = {
    "addlist",
    "addstickers",
    "confirmphone",
    "invoice",
    "joinchat",
    "login",
    "proxy",
    "s",
    "setlanguage",
    "share",
}


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


class SiteLinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self._href = ""
        self._text = []

    def handle_starttag(self, tag, attrs):
        if tag != "a" or self._href:
            return
        self._href = dict(attrs).get("href", "")
        self._text = []

    def handle_data(self, data):
        if self._href:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag != "a" or not self._href:
            return
        text = re.sub(r"\s+", " ", " ".join(self._text)).strip()
        self.links.append((html.unescape(self._href), text))
        self._href = ""
        self._text = []


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


def navigation_url(url):
    url = html.unescape(url)
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return ""
    return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", parsed.query, ""))


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
    html_text = fetch(f"{DUCKDUCKGO_HTML_URL}?{params}", timeout=12)
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


def resolve_redirect(url, referer="", timeout=12):
    headers = {"User-Agent": USER_AGENT}
    if referer:
        headers["Referer"] = referer
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return clean_url(response.geturl())


def search_bestchange_page(source_url, max_results):
    html_text = fetch(source_url, timeout=12)
    rows = re.findall(r'<tr[^>]+onclick="ccl\([^>]+>([\s\S]*?)</tr>', html_text, flags=re.I)
    click_urls = []
    for row in rows:
        link_match = re.search(r'href="(/click\.php\?[^"]+)"', row, flags=re.I)
        if link_match:
            click_urls.append(urllib.parse.urljoin(source_url, html.unescape(link_match.group(1))))
        if len(click_urls) >= max(max_results * 3, 6):
            break

    results = []
    seen = set()
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(6, len(click_urls) or 1)) as executor:
        futures = [executor.submit(resolve_redirect, click_url, source_url, 10) for click_url in click_urls]
        for future in concurrent.futures.as_completed(futures):
            try:
                url = future.result()
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
    return results


def search_bestchange(max_results):
    results = []
    seen = set()
    urls = list(BESTCHANGE_URLS)
    random.shuffle(urls)
    for source_url in urls:
        if len(results) >= max_results:
            break
        try:
            candidates = search_bestchange_page(source_url, max_results - len(results))
        except Exception:
            continue
        for url in candidates:
            domain = domain_of(url)
            if not domain or domain in seen:
                continue
            seen.add(domain)
            results.append(url)
    return results


def monitoring_links(html_text, current_url):
    results = []
    for href, text in parse_site_links(html_text):
        url = navigation_url(urllib.parse.urljoin(current_url, href))
        if url:
            results.append((url, text))
    return results


def is_monitor_profile(url, source_domain):
    if domain_of(url) != source_domain:
        return False
    path = urllib.parse.urlparse(url).path.lower()
    return any(marker in path for marker in MONITOR_PROFILE_MARKERS)


def add_monitor_candidate(results, seen, url, source_domain, max_results):
    if len(results) >= max_results:
        return
    candidate = clean_url(url)
    domain = domain_of(candidate)
    if not candidate or not domain or domain == source_domain or domain in seen or is_skipped(candidate):
        return
    seen.add(domain)
    results.append(candidate)


def search_monitoring_source(source_url, max_results, profile_limit=12):
    source_domain = domain_of(source_url)
    html_text = fetch(source_url, timeout=12)
    links = monitoring_links(html_text, source_url)
    results = []
    seen = set()
    profiles = []

    for url, _ in links:
        if domain_of(url) != source_domain:
            add_monitor_candidate(results, seen, url, source_domain, max_results)
        elif is_monitor_profile(url, source_domain):
            profiles.append(url)

    profiles = list(dict.fromkeys(profiles))
    random.shuffle(profiles)

    def scan_profile(profile_url):
        candidates = []
        try:
            profile_html = fetch(profile_url, timeout=7)
        except Exception:
            return candidates
        for url, anchor_text in monitoring_links(profile_html, profile_url):
            if len(candidates) >= 3:
                break
            if domain_of(url) != source_domain:
                candidates.append(url)
                continue
            path = urllib.parse.urlparse(url).path.lower()
            text_low = anchor_text.lower()
            looks_outbound = any(marker in path for marker in MONITOR_REDIRECT_PATH_MARKERS) or any(
                marker in text_low for marker in MONITOR_OUTBOUND_TEXT_MARKERS
            )
            if not looks_outbound:
                continue
            try:
                resolved = resolve_redirect(url, referer=profile_url, timeout=8)
            except Exception:
                continue
            candidates.append(resolved)
        return candidates

    selected_profiles = profiles[:profile_limit]
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(6, len(selected_profiles) or 1)) as executor:
        futures = [executor.submit(scan_profile, profile_url) for profile_url in selected_profiles]
        for future in concurrent.futures.as_completed(futures):
            try:
                candidates = future.result()
            except Exception:
                continue
            for candidate in candidates:
                add_monitor_candidate(results, seen, candidate, source_domain, max_results)
                if len(results) >= max_results:
                    break
            if len(results) >= max_results:
                break
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


def parse_site_links(html_text):
    parser = SiteLinkParser()
    try:
        parser.feed(html_text)
    except Exception:
        return []
    return parser.links


def telegram_handle_from_href(href):
    value = html.unescape(href or "").replace("\\/", "/")
    if value.startswith("//"):
        value = "https:" + value
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme.lower() == "tg" and parsed.netloc.lower() == "resolve":
        handle = urllib.parse.parse_qs(parsed.query).get("domain", [""])[0]
    elif parsed.netloc.lower().removeprefix("www.") in {
        "t.me",
        "telegram.me",
        "telegram.dog",
    }:
        handle = parsed.path.strip("/").split("/", 1)[0]
    else:
        return ""
    handle = handle.lstrip("@").strip()
    if handle.lower() in TG_RESERVED_PATHS or not TG_USERNAME_RE.fullmatch(handle):
        return ""
    return handle


def telegram_contact_score(handle, context, source_url):
    low = f"{handle} {context} {source_url}".lower()
    score = 10

    if any(
        marker in low
        for marker in (
            "partner",
            "partnership",
            "affiliate",
            "cooperat",
            "business",
            "commercial",
            "bizdev",
            "sales",
            "owner",
            "founder",
            "партнер",
            "партнёр",
            "сотруднич",
            "бизнес",
            "коммерц",
            "продаж",
            "владел",
            "руковод",
        )
    ):
        score += 100
    elif any(marker in low for marker in ("manager", "admin", "contact", "team", "менеджер", "админ", "контакт")):
        score += 70
    elif any(marker in low for marker in ("support", "help", "operator", "поддерж", "помощ", "оператор")):
        score += 40

    if any(marker in low for marker in ("news", "channel", "rates", "rate", "reserve", "новост", "курс", "резерв")):
        score -= 35
    if any(marker in low for marker in ("chat", "community", "group", "отзывы", "reviews", "чат")):
        score -= 25
    if handle.lower().endswith("bot") or " telegram bot" in low:
        score -= 50
    return score


def extract_telegram_candidates(html_text, source_url=""):
    candidates = {}

    def remember(handle, context):
        if not handle:
            return
        score = telegram_contact_score(handle, context, source_url)
        previous = candidates.get(handle.lower())
        if not previous or score > previous[0]:
            candidates[handle.lower()] = (score, "@" + handle)

    normalized = html_text.replace("\\/", "/")
    for href, anchor_text in parse_site_links(normalized):
        remember(telegram_handle_from_href(href), f"{anchor_text} {href}")

    for match in TG_LINK_RE.finditer(normalized):
        start = max(0, match.start() - 100)
        end = min(len(normalized), match.end() + 100)
        remember(match.group(1), visible_text(normalized[start:end]))

    visible = visible_text(normalized)
    for match in TG_HANDLE_RE.finditer(visible):
        start = max(0, match.start() - 80)
        end = min(len(visible), match.end() + 80)
        remember(match.group(1), visible[start:end])

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
    ranked = sorted(
        (
            (score, display)
            for key, (score, display) in candidates.items()
            if key not in excluded_handles
        ),
        key=lambda item: (-item[0], item[1].lower()),
    )
    return ranked


def extract_contacts(text, source_url=""):
    emails = sorted({x.strip(".,;:()[]<>").lower() for x in EMAIL_RE.findall(text)})
    telegram = [display for _, display in extract_telegram_candidates(text, source_url)]
    return telegram[:3], emails[:3]


def discover_contact_pages(html_text, current_url, root):
    root_domain = domain_of(root)
    candidates = []
    for href, anchor_text in parse_site_links(html_text):
        absolute = clean_url(urllib.parse.urljoin(current_url, href))
        if not absolute or domain_of(absolute) != root_domain:
            continue
        hint = f"{urllib.parse.urlparse(absolute).path} {anchor_text}".lower()
        if not any(marker in hint for marker in CONTACT_LINK_MARKERS):
            continue
        candidates.append(absolute)
    return list(dict.fromkeys(candidates))


def contains_any(text, markers):
    return any(marker in text for marker in markers)


def classify_and_score(text, telegram, email):
    low = text.lower()
    score = 1
    sphere = "криптосервис"

    if any(marker in low for marker in NON_TARGET_MARKERS):
        return "нецелевой", 1

    has_exchange = contains_any(low, EXCHANGE_MARKERS)
    has_otc = contains_any(low, OTC_P2P_MARKERS)
    has_traffic_team = contains_any(low, TRAFFIC_TEAM_MARKERS)
    has_payment_infra = contains_any(low, PAYMENT_INFRA_MARKERS)
    has_low_intent_infra = contains_any(low, LOW_INTENT_INFRA_MARKERS)
    has_fintech = has_payment_infra
    has_wallet = any(x in low for x in ("wallet", "кошелек", "кошелёк"))
    has_cards = any(x in low for x in ("visa", "mastercard", "виртуальные карты", "card"))
    has_virtual_cards = has_cards and any(
        x in low for x in ("виртуальн", "virtual", "выпуск", "оформить карту", "issue card")
    )
    has_gaming_topup = any(x in low for x in ("steam", "playstation", "ps store", "xbox", "игровой баланс")) and any(
        x in low for x in ("пополн", "оплат", "top up", "top-up", "gift card", "гифт-карт")
    )
    has_subscriptions = any(
        x in low
        for x in (
            "зарубежные сервисы",
            "зарубежных сервисов",
            "международные сервисы",
            "иностранные сервисы",
            "оплата подписок",
            "app store",
            "google play",
            "netflix",
            "spotify",
        )
    )
    has_crossborder = any(
        x in low
        for x in (
            "международные платежи",
            "международных платежей",
            "оплата за рубежом",
            "оплата за границей",
            "cross-border",
            "cross border",
        )
    )
    has_usdt = "usdt" in low or "tether" in low
    has_crypto = any(x in low for x in ("crypto", "крипто", "bitcoin", "btc", "blockchain", "tron", "trc20"))
    has_ruble_market = contains_any(low, RUBLE_MARKET_MARKERS)
    has_public_audience = any(
        x in low
        for x in (
            "audience",
            "blogger",
            "channel",
            "community",
            "influencer",
            "media",
            "subscribers",
            "академия",
            "аудитория",
            "блогер",
            "канал",
            "комьюнити",
            "медиа",
            "подписчик",
            "сообщество",
        )
    )
    has_trading_team = any(
        x in low
        for x in (
            "crypto trading",
            "p2p arbitrage",
            "trading team",
            "арбитраж криптовалют",
            "команда трейдеров",
            "крипто трейдер",
            "криптотрейдер",
            "p2p арбитраж",
            "трейдинг",
            "трейдер",
        )
    )
    has_startup = any(
        x in low
        for x in (
            "co-founder",
            "fintech startup",
            "founder",
            "startup",
            "web3 startup",
            "основатель",
            "стартап",
        )
    )

    if not (
        has_usdt
        or has_crypto
        or has_virtual_cards
        or has_gaming_topup
        or has_subscriptions
        or has_crossborder
        or (has_crypto and (has_public_audience or has_trading_team or has_startup or has_traffic_team))
    ):
        return "нецелевой", 1

    if has_crypto and has_startup:
        sphere = "крипто / финтех стартап"
        score += 4
    elif has_crypto and has_trading_team:
        sphere = "трейдинг / арбитражная команда"
        score += 4
    elif has_crypto and has_traffic_team:
        sphere = "крипто-трафик / affiliate"
        score += 4
    elif has_crypto and has_public_audience:
        sphere = "криптоблогер / сообщество"
        score += 4
    elif has_payment_infra and not (has_exchange or has_otc):
        sphere = "платежная инфраструктура / партнер"
        score += 1
    elif has_exchange:
        sphere = "криптообменник"
        score += 4
    elif has_otc:
        sphere = "OTC / P2P / арбитраж"
        score += 4
    elif has_traffic_team:
        sphere = "команда с трафиком"
        score += 3
    elif has_virtual_cards:
        sphere = "виртуальные карты"
        score += 3
    elif has_gaming_topup:
        sphere = "игровые платежи / пополнение"
        score += 3
    elif has_crossborder or has_subscriptions:
        sphere = "международные платежи"
        score += 2
    elif has_fintech:
        sphere = "финтех / платежи"
        score += 2
    elif has_wallet:
        sphere = "криптокошелек"
        score += 2

    if has_usdt and has_ruble_market:
        score += 2
    elif has_crypto and has_ruble_market:
        score += 1
    if has_cards:
        score += 1
    if has_fintech or has_wallet:
        score += 1
    if has_public_audience or has_trading_team or has_startup or has_traffic_team:
        score += 1
    if telegram:
        score += 1
    if email:
        score += 1
    if any(x in low for x in ("резерв", "reserve", "отзывы", "reviews", "support")):
        score += 1
    if has_traffic_team and (has_usdt or has_crypto):
        score += 1
    if has_payment_infra:
        score -= 2
    if has_low_intent_infra:
        score -= 1

    if not has_ruble_market and sphere in ("криптообменник", "OTC / P2P / арбитраж", "команда с трафиком"):
        score = min(score, 7)
    if sphere == "платежная инфраструктура / партнер":
        score = min(score, 5)
    if has_low_intent_infra and sphere == "платежная инфраструктура / партнер":
        score = min(score, 4)

    return sphere, max(1, min(10, score))


def is_target_project(title, text):
    title_low = title.lower()
    text_low = text.lower()
    if any(marker in title_low for marker in EDITORIAL_TITLE_MARKERS):
        return False
    has_target_title = any(marker in title_low for marker in TARGET_TITLE_MARKERS)
    has_crypto = any(marker in text_low for marker in ("usdt", "tether", "crypto", "крипто", "trc20"))
    has_crypto_service = any(
        marker in text_low
        for marker in (
            "обмен",
            "обмін",
            "exchange",
            "exchanger",
            "otc",
            "p2p",
            "wallet",
            "кошелек",
            "кошелёк",
            "арбитраж",
            "traffic",
            "трафик",
            "affiliate",
            "cpa",
            "вебмастер",
        )
    )
    has_card_service = any(marker in text_low for marker in ("visa", "mastercard", "виртуальн", "virtual card")) and any(
        marker in text_low for marker in ("выпуск", "оформ", "оплат", "issue", "payment", "пополн")
    )
    has_gaming_service = any(marker in text_low for marker in ("steam", "playstation", "ps store", "xbox")) and any(
        marker in text_low for marker in ("пополн", "оплат", "top up", "top-up", "gift card")
    )
    has_crossborder_service = any(
        marker in text_low
        for marker in (
            "зарубежные сервисы",
            "зарубежных сервисов",
            "международные платежи",
            "оплата за рубежом",
            "оплата подписок",
            "cross-border",
        )
    )
    has_audience_project = any(
        marker in text_low
        for marker in (
            "audience",
            "blogger",
            "channel",
            "community",
            "influencer",
            "subscribers",
            "академия",
            "аудитория",
            "блогер",
            "канал",
            "комьюнити",
            "подписчик",
            "сообщество",
        )
    )
    has_team_project = any(
        marker in text_low
        for marker in (
            "affiliate",
            "co-founder",
            "crypto trading",
            "founder",
            "media buying",
            "p2p arbitrage",
            "startup",
            "trading team",
            "web3",
            "арбитраж криптовалют",
            "арбитраж трафика",
            "команда трейдеров",
            "основатель",
            "стартап",
            "трейдер",
            "трейдинг",
        )
    )
    has_personal_brand_target = has_crypto and (has_audience_project or has_team_project)
    return (
        has_target_title
        and (
            (has_crypto and has_crypto_service)
            or has_card_service
            or has_gaming_service
            or has_crossborder_service
        )
    ) or has_personal_brand_target


def scan_site(url, scan_pages=10):
    combined = ""
    title = ""
    telegram_scores = {}
    found_email = []
    root = base_url(url)
    queue = [root]
    queue.extend(root + path for path in CONTACT_PATHS if path)
    seen_pages = set()

    while queue and len(seen_pages) < scan_pages:
        page_url = queue.pop(0)
        if page_url in seen_pages:
            continue
        seen_pages.add(page_url)
        try:
            page = fetch(page_url)
        except Exception:
            continue
        if not page:
            continue
        if not title:
            title = page_title(page)
        text = visible_text(page)
        combined += " " + text[:150_000]
        for score, display in extract_telegram_candidates(page, page_url):
            key = display.lower()
            telegram_scores[key] = max(score, telegram_scores.get(key, -10_000))
        email = sorted({x.strip(".,;:()[]<>").lower() for x in EMAIL_RE.findall(page + " " + text)})
        found_email.extend(email)
        discovered = discover_contact_pages(page, page_url, root)
        queue = discovered + [candidate for candidate in queue if candidate not in discovered]
        time.sleep(0.2)

    ranked_telegram = sorted(
        ((score, handle) for handle, score in telegram_scores.items()),
        key=lambda item: (-item[0], item[1]),
    )
    found_telegram = [handle for _, handle in ranked_telegram[:1]]
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
        "Email": ", ".join(found_email[:3]),
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
            keys.update(row_keys(row))
    return keys


def split_contacts(value):
    return [part.strip().lower() for part in (value or "").split(",") if part.strip()]


def row_keys(row):
    keys = set()
    name = (row.get("Название проекта") or "").strip().lower()
    if name:
        keys.add("name:" + name)
    for handle in split_contacts(row.get("Telegram", "")):
        keys.add("tg:" + handle)
    for email in split_contacts(row.get("Email", "")):
        keys.add("email:" + email)
    if not keys:
        keys.add(
            "raw:"
            + "|".join(
                (
                    row.get("Название проекта", ""),
                    row.get("Telegram", ""),
                    row.get("Email", ""),
                )
            ).lower()
        )
    return keys


def project_key(row):
    name = row.get("Название проекта", "").lower().strip()
    domain_match = DOMAIN_IN_TEXT_RE.search(name)
    if domain_match:
        return "domain:" + domain_match.group(1).removeprefix("www.")

    email_match = EMAIL_RE.search(row.get("Email", ""))
    if email_match:
        email_domain = email_match.group(0).rsplit("@", 1)[-1].lower()
        if email_domain not in PUBLIC_EMAIL_DOMAINS:
            return "domain:" + email_domain

    telegram_match = TG_HANDLE_RE.search(row.get("Telegram", ""))
    if telegram_match:
        return "telegram:" + telegram_match.group(1).lower()

    normalized_name = re.sub(r"[^a-zа-яё0-9]+", "", name)
    generic_names = {
        "обменныйпунктэлектронныхвалют",
        "обменкриптовалют",
        "cryptocurrencyexchange",
        "cryptoexchange",
    }
    if len(normalized_name) < 8 or normalized_name in generic_names:
        return ""
    return "name:" + normalized_name


def merge_lead_rows(current, fresh):
    merged = dict(current)
    if fresh.get("Telegram"):
        merged["Telegram"] = fresh["Telegram"]
    if fresh.get("Email"):
        current_emails = [item.strip() for item in current.get("Email", "").split(",") if item.strip()]
        fresh_emails = [item.strip() for item in fresh.get("Email", "").split(",") if item.strip()]
        merged["Email"] = ", ".join(list(dict.fromkeys(current_emails + fresh_emails))[:3])
    if fresh.get("Сфера") and fresh.get("Сфера") != "нецелевой":
        merged["Сфера"] = fresh["Сфера"]
    merged["Оценка 1-10 для покупки франшизы"] = str(
        max(
            int(current.get("Оценка 1-10 для покупки франшизы", "1") or 1),
            int(fresh.get("Оценка 1-10 для покупки франшизы", "1") or 1),
        )
    )
    return merged


def upsert_rows(csv_path, rows):
    path = Path(csv_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = []
    if path.exists():
        with path.open("r", encoding="utf-8-sig", newline="") as file:
            existing = list(csv.DictReader(file))

    positions = {project_key(row): index for index, row in enumerate(existing) if project_key(row)}
    added = 0
    updated = 0
    for row in rows:
        key = project_key(row)
        if key and key in positions:
            index = positions[key]
            merged = merge_lead_rows(existing[index], row)
            if merged != existing[index]:
                existing[index] = merged
                updated += 1
            continue
        positions[key] = len(existing)
        existing.append(row)
        added += 1

    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=HEADERS)
        writer.writeheader()
        for row in existing:
            writer.writerow(row)
    return added, updated


def has_required_contact(row):
    return bool(row.get("Telegram") or row.get("Email"))


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Collect public Altyn franchise leads into a simple CSV.")
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--queries", default=str(Path(__file__).with_name("queries.txt")))
    parser.add_argument("--out", default=str(Path(__file__).with_name("altyn_leads.csv")))
    parser.add_argument("--search-results", type=int, default=6)
    parser.add_argument("--max-queries", type=int, default=18)
    parser.add_argument("--scan-pages", type=int, default=10)
    parser.add_argument("--min-score", type=int, default=5)
    args = parser.parse_args()

    queries = read_lines(args.queries)
    if not queries:
        raise SystemExit("No queries found.")
    random.shuffle(queries)

    keys = existing_keys(args.out)
    rows = []
    seen_domains = set()

    def collect_candidates(candidates, source_cap=None):
        source_start = len(rows)
        pending = []
        for url in candidates:
            domain = domain_of(url)
            if not domain or domain in seen_domains:
                continue
            seen_domains.add(domain)
            print(f"Scanning: {domain}")
            pending.append(url)

        def scan_candidate(url):
            try:
                return scan_site(url, scan_pages=max(1, min(8, args.scan_pages))), ""
            except Exception as exc:
                return None, str(exc)

        scanned = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(5, len(pending) or 1)) as executor:
            future_urls = {executor.submit(scan_candidate, url): url for url in pending}
            for future in concurrent.futures.as_completed(future_urls):
                row, error = future.result()
                if error:
                    print(f"Scan failed ({domain_of(future_urls[future])}): {error}")
                    continue
                if row:
                    scanned.append(row)

        scanned.sort(
            key=lambda item: (
                bool(item.get("Telegram")),
                int(item["Оценка 1-10 для покупки франшизы"]),
            ),
            reverse=True,
        )

        for row in scanned:
            if len(rows) >= args.limit:
                break
            if source_cap is not None and len(rows) - source_start >= source_cap:
                break
            if not has_required_contact(row):
                continue
            if row["Сфера"] == "нецелевой":
                continue
            if int(row["Оценка 1-10 для покупки франшизы"]) < args.min_score:
                continue
            new_keys = row_keys(row)
            if keys.intersection(new_keys):
                continue
            keys.update(new_keys)
            rows.append(row)
            upsert_rows(args.out, [row])
            print(f"Added: {row['Название проекта']} / {row['Оценка 1-10 для покупки франшизы']}")

    print("Searching: BestChange exchangers")
    bestchange_quota = max(1, (args.limit + 2) // 3)
    try:
        bestchange_candidates = search_bestchange(max(bestchange_quota * 3, 8))
        collect_candidates(bestchange_candidates, source_cap=bestchange_quota)
    except Exception as exc:
        print(f"BestChange search failed: {exc}")

    primary_monitorings = list(MONITORING_SOURCES[:4])
    extra_monitorings = list(MONITORING_SOURCES[4:])
    random.shuffle(extra_monitorings)
    monitoring_sources = primary_monitorings + extra_monitorings[:2]
    monitoring_quota = max(1, (args.limit + 2) // 3)
    monitoring_start = len(rows)
    for source_name, source_url in monitoring_sources:
        if len(rows) >= args.limit:
            break
        monitoring_remaining = monitoring_quota - (len(rows) - monitoring_start)
        if monitoring_remaining <= 0:
            break
        print(f"Searching monitoring: {source_name}")
        try:
            candidates = search_monitoring_source(
                source_url,
                max_results=max(monitoring_remaining * 2, 4),
                profile_limit=max(monitoring_remaining * 3, 6),
            )
        except Exception as exc:
            print(f"Monitoring search failed ({source_name}): {exc}")
            continue
        collect_candidates(candidates, source_cap=monitoring_remaining)

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

    print(f"Done. Collected {len(rows)} leads in {args.out}")


if __name__ == "__main__":
    main()
