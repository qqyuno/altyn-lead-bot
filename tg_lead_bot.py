#!/usr/bin/env python3
import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
import urllib.error
import uuid
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


HEADERS = [
    "Название проекта",
    "Сфера",
    "Telegram",
    "Email",
    "Оценка 1-10 для покупки франшизы",
]

BUTTON_COLLECT = "Собрать TG-контакты"
BUTTON_TRAVEL = "Туристические обменники"
BUTTON_NEXT = "Следующий контакт"
BUTTON_COUNT = "Сколько лидов"
BUTTON_STATUS = "Статус сбора"

MAIN_KEYBOARD = {
    "keyboard": [
        [{"text": BUTTON_COLLECT}, {"text": BUTTON_TRAVEL}],
        [{"text": BUTTON_NEXT}],
        [{"text": BUTTON_COUNT}, {"text": BUTTON_STATUS}],
    ],
    "resize_keyboard": True,
    "is_persistent": True,
}


def env(name, default=""):
    return os.environ.get(name, default).strip()


BOT_TOKEN = env("BOT_TOKEN")
LEADS_CSV = Path(env("LEADS_CSV", str(Path(__file__).with_name("altyn_leads.csv"))))
LEAD_STATE_JSON = Path(env("LEAD_STATE_JSON", str(Path(__file__).with_name("lead_state.json"))))
INITIAL_LEADS_CSV = Path(__file__).with_name("initial_leads.csv")
HUNTER_SCRIPT = Path(__file__).with_name("lead_hunter.py")
TOURIST_QUERIES = Path(__file__).with_name("tourist_queries.txt")
ALLOWED_USER_IDS = {
    int(x.strip())
    for x in env("ALLOWED_USER_IDS").split(",")
    if x.strip().isdigit()
}
REPORT_CHAT_ID = env("REPORT_CHAT_ID")
AUTO_COLLECT_INTERVAL_HOURS = float(env("AUTO_COLLECT_INTERVAL_HOURS", "0") or 0)
AUTO_COLLECT_LIMIT = max(1, min(100, int(env("AUTO_COLLECT_LIMIT", "30") or 30)))

COLLECT_LOCK = threading.Lock()
COLLECT_STATE = {
    "running": False,
    "started_at": 0.0,
    "last_finished_at": 0.0,
    "last_result": "Сбор ещё не запускался.",
}
PENDING_SEARCH = set()
LEAD_CURSORS = {}

DAILY_TARGET = 50
MOSCOW_TZ = ZoneInfo("Europe/Moscow")
EMPTY_REVIEW_STATE = {"contacted": [], "skipped": [], "sent_events": []}


def api(method, payload=None, timeout=35, attempts=3):
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is empty.")
    data = urllib.parse.urlencode(payload or {}).encode()
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(url, data=data, timeout=timeout) as response:
                result = json.loads(response.read().decode("utf-8"))
            if not result.get("ok"):
                parameters = result.get("parameters") or {}
                retry_after = int(parameters.get("retry_after", 0) or 0)
                if retry_after and attempt < attempts:
                    time.sleep(min(retry_after, 30))
                    continue
                raise RuntimeError(result.get("description", "Telegram API error"))
            return result
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code == 429 and attempt < attempts:
                try:
                    body = json.loads(exc.read().decode("utf-8"))
                    retry_after = int((body.get("parameters") or {}).get("retry_after", 5))
                except Exception:
                    retry_after = 5
                time.sleep(min(retry_after, 30))
                continue
        except (urllib.error.URLError, TimeoutError) as exc:
            last_error = exc
            if attempt < attempts:
                time.sleep(1.5 * attempt)
                continue
    raise RuntimeError(f"Telegram API request failed: {last_error}")


def send(chat_id, text, keyboard=True, reply_markup=None):
    payload = {
        "chat_id": chat_id,
        "text": text[:3900],
        "disable_web_page_preview": "true",
    }
    if reply_markup is not None:
        payload["reply_markup"] = json.dumps(reply_markup, ensure_ascii=False)
    elif keyboard:
        payload["reply_markup"] = json.dumps(MAIN_KEYBOARD, ensure_ascii=False)
    return api("sendMessage", payload)


def send_document(chat_id, file_path, caption=""):
    boundary = "----AltynLeadBot" + uuid.uuid4().hex
    body = bytearray()

    def add_field(name, value):
        body.extend(f"--{boundary}\r\n".encode())
        body.extend(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        body.extend(str(value).encode("utf-8"))
        body.extend(b"\r\n")

    add_field("chat_id", chat_id)
    if caption:
        add_field("caption", caption[:900])

    body.extend(f"--{boundary}\r\n".encode())
    body.extend(
        f'Content-Disposition: form-data; name="document"; filename="{file_path.name}"\r\n'.encode()
    )
    body.extend(b"Content-Type: text/csv\r\n\r\n")
    body.extend(file_path.read_bytes())
    body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode())

    request = urllib.request.Request(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument",
        data=bytes(body),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        result = json.loads(response.read().decode("utf-8"))
    if not result.get("ok"):
        raise RuntimeError(result.get("description", "Telegram upload failed"))
    return result


def allowed(user_id):
    return not ALLOWED_USER_IDS or user_id in ALLOWED_USER_IDS


def ensure_csv():
    LEADS_CSV.parent.mkdir(parents=True, exist_ok=True)
    if not LEADS_CSV.exists():
        if INITIAL_LEADS_CSV.exists() and INITIAL_LEADS_CSV.resolve() != LEADS_CSV.resolve():
            shutil.copyfile(INITIAL_LEADS_CSV, LEADS_CSV)
        else:
            with LEADS_CSV.open("w", encoding="utf-8-sig", newline="") as file:
                csv.DictWriter(file, fieldnames=HEADERS).writeheader()


def load_rows():
    ensure_csv()
    with LEADS_CSV.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def save_row(row):
    ensure_csv()
    with LEADS_CSV.open("a", encoding="utf-8-sig", newline="") as file:
        csv.DictWriter(file, fieldnames=HEADERS).writerow(row)


def normalize_contact(value):
    return re.sub(r"\s+", "", (value or "").strip().lower())


def duplicate_of(candidate, rows=None):
    rows = rows if rows is not None else load_rows()
    candidate_name = (candidate.get("Название проекта") or "").strip().lower()
    candidate_tg = normalize_contact(candidate.get("Telegram", ""))
    candidate_email = normalize_contact(candidate.get("Email", ""))
    for row in rows:
        name = (row.get("Название проекта") or "").strip().lower()
        tg = normalize_contact(row.get("Telegram", ""))
        email = normalize_contact(row.get("Email", ""))
        if candidate_tg and tg and candidate_tg in tg:
            return row
        if candidate_email and email and candidate_email in email:
            return row
        if candidate_name and candidate_name == name:
            return row
    return None


def ensure_state():
    LEAD_STATE_JSON.parent.mkdir(parents=True, exist_ok=True)
    if not LEAD_STATE_JSON.exists():
        save_state(EMPTY_REVIEW_STATE.copy())


def load_state():
    ensure_state()
    try:
        state = json.loads(LEAD_STATE_JSON.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        state = EMPTY_REVIEW_STATE.copy()
    return {
        "contacted": list(dict.fromkeys(state.get("contacted", []))),
        "skipped": list(dict.fromkeys(state.get("skipped", []))),
        "sent_events": [event for event in state.get("sent_events", []) if isinstance(event, dict)],
    }


def save_state(state):
    LEAD_STATE_JSON.parent.mkdir(parents=True, exist_ok=True)
    normalized = {
        "contacted": sorted(set(state.get("contacted", []))),
        "skipped": sorted(set(state.get("skipped", []))),
        "sent_events": state.get("sent_events", []),
    }
    LEAD_STATE_JSON.write_text(
        json.dumps(normalized, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def row_key(row):
    raw = "|".join((row.get(header, "") or "").strip().lower() for header in HEADERS)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def row_is_new(row, state=None):
    state = state or load_state()
    key = row_key(row)
    return key not in state["contacted"] and key not in state["skipped"]


def mark_lead(lead_id, status):
    state = load_state()
    for bucket in ("contacted", "skipped"):
        if lead_id in state[bucket]:
            state[bucket].remove(lead_id)
    if status in state:
        state[status].append(lead_id)
    if status == "contacted":
        day = datetime.now(MOSCOW_TZ).date().isoformat()
        already_counted = any(
            event.get("lead_id") == lead_id and event.get("day") == day
            for event in state["sent_events"]
        )
        if not already_counted:
            state["sent_events"].append({"lead_id": lead_id, "day": day})
    save_state(state)


def sent_today(state=None, day=None):
    state = state or load_state()
    day = day or datetime.now(MOSCOW_TZ).date().isoformat()
    return len(
        {
            event.get("lead_id")
            for event in state.get("sent_events", [])
            if event.get("day") == day and event.get("lead_id")
        }
    )


def cmd_today():
    sent = sent_today()
    remaining = max(0, DAILY_TARGET - sent)
    return f"Сегодня отправлено: {sent}/{DAILY_TARGET}\nОсталось до плана: {remaining}"


def reset_review_state():
    LEAD_CURSORS.clear()
    save_state(EMPTY_REVIEW_STATE.copy())
    return "Сбросил разбор. Все лиды снова будут показываться в очереди."


def score_of(row):
    try:
        return int(row.get("Оценка 1-10 для покупки франшизы", "0"))
    except (TypeError, ValueError):
        return 0


def priority_label(row):
    score = score_of(row)
    if score >= 9:
        return "высокий"
    if score >= 7:
        return "средний"
    return "низкий"


def lead_reason(row):
    sphere = (row.get("Сфера") or "").lower()
    reasons = []
    if "обмен" in sphere:
        reasons.append("похож на обменник")
    elif "трейдинг" in sphere or "арбитраж" in sphere:
        reasons.append("похож на трейдинг/арбитражную команду")
    elif "otc" in sphere:
        reasons.append("похож на OTC/P2P-команду")
    elif "блогер" in sphere or "сообщество" in sphere:
        reasons.append("есть своя криптоаудитория")
    elif "трафик" in sphere or "affiliate" in sphere:
        reasons.append("есть команда по привлечению трафика")
    elif "стартап" in sphere:
        reasons.append("похож на крипто/финтех-стартап")
    elif "финтех" in sphere or "платеж" in sphere:
        reasons.append("скорее партнер/инфраструктура, не основной лид")
    if telegram_url(row.get("Telegram", "")):
        reasons.append("есть Telegram для быстрого контакта")
    if row.get("Email"):
        reasons.append("есть email")
    if score_of(row) >= 8:
        reasons.append("оценка 8+")
    return ", ".join(reasons) or "публичный контакт из целевой базы"


def format_row(row, index):
    tg = row.get("Telegram") or "-"
    return (
        f"{row.get('Название проекта', 'Проект')}\n"
        f"{tg}"
    )


def telegram_url(value):
    match = re.search(r"(?:https?://)?(?:t\.me|telegram\.me)/([A-Za-z0-9_]{4,32})", value, re.I)
    if not match:
        match = re.search(r"@([A-Za-z0-9_]{4,32})", value)
    if not match:
        return ""
    return f"https://t.me/{match.group(1)}"


def ranked_rows():
    rows = sorted(load_rows(), key=score_of, reverse=True)
    seen = set()
    unique = []
    for row in rows:
        contact = telegram_url(row.get("Telegram", "")).lower()
        if not contact or contact in seen:
            continue
        seen.add(contact)
        unique.append(row)
    return unique


def cursor_key(user_id, min_score):
    return f"{user_id}:{min_score}"


def lead_keyboard(row, min_score=1):
    buttons = []
    contact_url = telegram_url(row.get("Telegram", ""))
    lead_id = row_key(row)
    if contact_url:
        buttons.append([{"text": "Открыть чат", "url": contact_url}])
    buttons.append(
        [
            {"text": "Отправил → следующий", "callback_data": f"work:{min_score}:{lead_id}"},
            {"text": "Пропустить", "callback_data": f"skip:{min_score}:{lead_id}"},
        ]
    )
    return {"inline_keyboard": buttons}


def send_next_lead(chat_id, user_id, min_score=1):
    state = load_state()
    rows = [
        row
        for row in ranked_rows()
        if row_is_new(row, state) and score_of(row) >= min_score
    ]
    if not rows:
        total = len(ranked_rows())
        if total:
            scope = "горячие лиды 8+" if min_score >= 8 else "лиды"
            send(
                chat_id,
                f"Все {scope} из текущей базы уже разобраны: часть взята в работу, часть пропущена. "
                "Можно нажать «Собрать TG-контакты».",
            )
        else:
            send(chat_id, "База пока пустая. Нажми «Собрать TG-контакты».")
        return
    key = cursor_key(user_id, min_score)
    position = LEAD_CURSORS.get(key, 0) % len(rows)
    row = rows[position]
    LEAD_CURSORS[key] = position + 1
    text = format_row(row, position + 1) + f"\n\nОсталось контактов: {len(rows)}"
    send(chat_id, text, keyboard=False, reply_markup=lead_keyboard(row, min_score=min_score))


def send_rows(chat_id, rows):
    if not rows:
        send(chat_id, "Ничего не найдено.")
        return
    chunk = ""
    for index, row in enumerate(rows, 1):
        item = format_row(row, index)
        candidate = f"{chunk}\n\n{item}" if chunk else item
        if len(candidate) > 3700:
            send(chat_id, chunk)
            chunk = item
        else:
            chunk = candidate
    if chunk:
        send(chat_id, chunk)


def cmd_start():
    return (
        "Altyn Lead Bot\n\n"
        "Собирает только публичные Telegram-контакты и показывает каждый один раз.\n\n"
        "/collect 100 - собрать контакты\n"
        "/travel 100 - обменники в туристических странах\n"
        "/next - открыть следующий контакт\n"
        "/today - план на сегодня\n"
        "/count - показать остаток\n"
        "/status - статус сбора"
    )


def cmd_count():
    rows = ranked_rows()
    state = load_state()
    new_rows = sum(row_is_new(row, state) for row in rows)
    return (
        f"TG-контактов: {len(rows)}\n"
        f"Осталось: {new_rows}\n"
        f"Сегодня: {sent_today(state)}/{DAILY_TARGET}\n"
        f"Отправлено: {len(state['contacted'])}\n"
        f"Пропущено: {len(state['skipped'])}"
    )


def top_rows(text):
    parts = text.split()
    limit = 10
    if len(parts) > 1 and parts[1].isdigit():
        limit = max(1, min(30, int(parts[1])))
    return sorted(load_rows(), key=score_of, reverse=True)[:limit]


def search_rows(query):
    query = query.strip().lower()
    if not query:
        return []
    matches = []
    for row in load_rows():
        haystack = " ".join(row.get(header, "") for header in HEADERS).lower()
        if query in haystack:
            matches.append(row)
    return sorted(matches, key=score_of, reverse=True)[:20]


def cmd_add(text):
    if COLLECT_STATE["running"]:
        return "Сейчас идёт сбор. Добавь запись после его завершения, чтобы CSV не пересёкся по записи."
    raw = text.partition(" ")[2].strip()
    parts = [x.strip() for x in raw.split("|")]
    if len(parts) != 5:
        return "Формат: /add Название | Сфера | @telegram | email | 8"
    name, sphere, telegram, email, score = parts
    if not name:
        return "Укажи название проекта."
    if not score.isdigit() or not (1 <= int(score) <= 10):
        return "Оценка должна быть числом от 1 до 10."
    row = {
        "Название проекта": name,
        "Сфера": sphere,
        "Telegram": telegram,
        "Email": email,
        "Оценка 1-10 для покупки франшизы": score,
    }
    duplicate = duplicate_of(row)
    if duplicate:
        return f"Похоже, уже есть в базе: {duplicate.get('Название проекта', name)}"
    save_row(row)
    return f"Добавил: {name} / {score}/10"


def collection_status():
    if COLLECT_STATE["running"]:
        elapsed = max(1, int((time.time() - COLLECT_STATE["started_at"]) / 60))
        return f"Сбор идёт {elapsed} мин. Бот проверяет сайты и ищет публичные контакты."
    return COLLECT_STATE["last_result"]


def parsed_collection_counts(output, fallback_added):
    match = re.search(r"Done\. Added (\d+) leads, updated (\d+) leads", output or "")
    if not match:
        return fallback_added, 0
    return int(match.group(1)), int(match.group(2))


def collection_command(limit, telegram_only=False, queries_path=None):
    command = [
        sys.executable,
        str(HUNTER_SCRIPT),
        "--limit",
        str(limit),
        "--out",
        str(LEADS_CSV),
    ]
    if telegram_only:
        max_queries = "120" if queries_path else "60"
        command.extend(
            [
                "--telegram-only",
                "--query-only",
                "--max-queries",
                max_queries,
                "--search-results",
                "10",
            ]
        )
    if queries_path:
        command.extend(["--queries", str(queries_path)])
    return command


def run_collection(chat_id, limit, telegram_only=False, queries_path=None, segment_name=""):
    before = len(load_rows())
    try:
        command = collection_command(limit, telegram_only, queries_path)
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=1800,
            check=False,
        )
        after = len(load_rows())
        added, updated = parsed_collection_counts(completed.stdout, max(0, after - before))
        if completed.returncode == 0:
            segment = f" ({segment_name})" if segment_name else ""
            result = (
                f"Сбор завершён{segment}. Новых лидов: {added}. Обновлено контактов: {updated}. "
                f"Всего в базе: {after}.\n"
                "Нажми «Следующий лид», чтобы начать разбор контактов."
            )
        else:
            detail = (completed.stderr or completed.stdout or "неизвестная ошибка").strip()[-700:]
            result = f"Сбор завершился с ошибкой. База сохранена.\n{detail}"
    except subprocess.TimeoutExpired:
        result = "Сбор остановлен через 30 минут по тайм-ауту. Уже найденные записи сохранены."
    except Exception as exc:
        result = f"Не удалось завершить сбор: {exc}"
    finally:
        COLLECT_STATE.update(
            running=False,
            last_finished_at=time.time(),
            last_result=result,
        )
        COLLECT_LOCK.release()
    try:
        send(chat_id, result)
    except Exception as exc:
        print(f"Could not send collection report: {exc}")


def start_collection(
    chat_id,
    limit=20,
    telegram_only=False,
    queries_path=None,
    segment_name="",
):
    limit = max(1, min(300, int(limit)))
    if not COLLECT_LOCK.acquire(blocking=False):
        send(chat_id, collection_status())
        return
    COLLECT_STATE.update(running=True, started_at=time.time())
    send(
        chat_id,
        (
            f"Запустил сбор до {limit} новых лидов с публичным Telegram"
            + (f" в сегменте «{segment_name}»." if segment_name else ".")
            if telegram_only
            else f"Запустил сбор до {limit} новых лидов."
        )
        + " Можно закрыть Telegram: по завершении пришлю результат.",
    )
    threading.Thread(
        target=run_collection,
        args=(chat_id, limit, telegram_only, queries_path, segment_name),
        daemon=True,
    ).start()


def export_csv(chat_id):
    ensure_csv()
    rows = load_rows()
    send_document(chat_id, LEADS_CSV, f"База Altyn: {len(rows)} лидов")


def telegram_rows(limit=100):
    rows = [row for row in ranked_rows() if telegram_url(row.get("Telegram", ""))]
    seen = set()
    selected = []
    for row in rows:
        contact = telegram_url(row.get("Telegram", "")).lower()
        if contact in seen:
            continue
        seen.add(contact)
        selected.append(row)
        if len(selected) >= limit:
            break
    return selected


def export_telegram_contacts(chat_id, limit=100):
    limit = max(1, min(1000, int(limit)))
    rows = telegram_rows(limit)
    if not rows:
        send(chat_id, "В базе пока нет Telegram-контактов. Запусти /collecttg 100.")
        return

    export_path = LEADS_CSV.with_name(f"telegram_contacts_{uuid.uuid4().hex[:8]}.csv")
    try:
        with export_path.open("w", encoding="utf-8-sig", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=HEADERS)
            writer.writeheader()
            writer.writerows(rows)
        send_document(
            chat_id,
            export_path,
            f"Публичные Telegram-контакты: {len(rows)}. Проекты отсортированы по приоритету.",
        )
    finally:
        export_path.unlink(missing_ok=True)


def handle_message(message):
    chat_id = message["chat"]["id"]
    user_id = message.get("from", {}).get("id", 0)
    if not allowed(user_id):
        send(chat_id, "Нет доступа.", keyboard=False)
        return

    text = (message.get("text") or "").strip()
    if text.startswith("/start") or text.startswith("/help"):
        send(chat_id, cmd_start())
    elif text.startswith("/travel"):
        parts = text.split()
        limit = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 100
        start_collection(
            chat_id,
            limit,
            telegram_only=True,
            queries_path=TOURIST_QUERIES,
            segment_name="туристические обменники",
        )
    elif text.startswith("/collecttg"):
        parts = text.split()
        limit = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 100
        start_collection(chat_id, limit, telegram_only=True)
    elif text.startswith("/collect"):
        parts = text.split()
        limit = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 100
        start_collection(chat_id, limit, telegram_only=True)
    elif text == BUTTON_COLLECT:
        start_collection(chat_id, 100, telegram_only=True)
    elif text == BUTTON_TRAVEL:
        start_collection(
            chat_id,
            100,
            telegram_only=True,
            queries_path=TOURIST_QUERIES,
            segment_name="туристические обменники",
        )
    elif text.startswith("/next"):
        parts = text.split()
        min_score = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 1
        send_next_lead(chat_id, user_id, min_score=max(1, min(10, min_score)))
    elif text == BUTTON_NEXT:
        send_next_lead(chat_id, user_id, min_score=1)
    elif text.startswith("/count") or text == BUTTON_COUNT:
        send(chat_id, cmd_count())
    elif text.startswith("/today"):
        send(chat_id, cmd_today())
    elif text.startswith("/top"):
        send_rows(chat_id, top_rows(text))
    elif text.startswith("/search"):
        query = text.partition(" ")[2].strip()
        if not query:
            PENDING_SEARCH.add(user_id)
            send(chat_id, "Напиши название, сферу, Telegram или email для поиска.")
        else:
            send_rows(chat_id, search_rows(query))
    elif user_id in PENDING_SEARCH and not text.startswith("/"):
        PENDING_SEARCH.discard(user_id)
        send_rows(chat_id, search_rows(text))
    elif text.startswith("/export"):
        export_csv(chat_id)
    elif text.startswith("/tglist"):
        parts = text.split()
        limit = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 100
        export_telegram_contacts(chat_id, limit)
    elif text.startswith("/status") or text == BUTTON_STATUS:
        send(chat_id, collection_status())
    elif text.startswith("/add"):
        send(chat_id, cmd_add(text))
    else:
        send(chat_id, "Не понял запрос. Используй кнопки или напиши /help")


def handle_callback(callback):
    user_id = callback.get("from", {}).get("id", 0)
    message = callback.get("message") or {}
    chat_id = message.get("chat", {}).get("id")
    if not chat_id:
        api("answerCallbackQuery", {"callback_query_id": callback["id"]})
        return
    if not allowed(user_id):
        api("answerCallbackQuery", {"callback_query_id": callback["id"]})
        send(chat_id, "Нет доступа.", keyboard=False)
        return
    data = callback.get("data") or ""
    if data.startswith("next:"):
        api("answerCallbackQuery", {"callback_query_id": callback["id"]})
        min_score = int(data.partition(":")[2] or 1)
        send_next_lead(chat_id, user_id, min_score=max(1, min(10, min_score)))
    elif data.startswith("work:"):
        parts = data.split(":", 2)
        min_score = parts[1] if len(parts) == 3 else "1"
        lead_id = parts[2] if len(parts) == 3 else parts[1]
        mark_lead(lead_id, "contacted")
        api(
            "answerCallbackQuery",
            {
                "callback_query_id": callback["id"],
                "text": f"Сегодня: {sent_today()}/{DAILY_TARGET}",
            },
        )
        send_next_lead(chat_id, user_id, min_score=max(1, min(10, int(min_score or 1))))
    elif data.startswith("skip:"):
        parts = data.split(":", 2)
        min_score = parts[1] if len(parts) == 3 else "1"
        lead_id = parts[2] if len(parts) == 3 else parts[1]
        mark_lead(lead_id, "skipped")
        api("answerCallbackQuery", {"callback_query_id": callback["id"], "text": "Пропустил"})
        send_next_lead(chat_id, user_id, min_score=max(1, min(10, int(min_score or 1))))
    else:
        api("answerCallbackQuery", {"callback_query_id": callback["id"]})


def configure_commands():
    commands = [
        {"command": "collect", "description": "Собрать TG-контакты"},
        {"command": "travel", "description": "Обменники в туристических странах"},
        {"command": "next", "description": "Открыть следующий контакт"},
        {"command": "today", "description": "План 50 касаний на сегодня"},
        {"command": "count", "description": "Сколько контактов осталось"},
        {"command": "status", "description": "Статус сбора"},
        {"command": "help", "description": "Помощь"},
    ]
    api("setMyCommands", {"commands": json.dumps(commands, ensure_ascii=False)})


def auto_collect_loop():
    if AUTO_COLLECT_INTERVAL_HOURS <= 0 or not REPORT_CHAT_ID:
        return
    time.sleep(60)
    while True:
        start_collection(REPORT_CHAT_ID, AUTO_COLLECT_LIMIT, telegram_only=True)
        time.sleep(max(1, AUTO_COLLECT_INTERVAL_HOURS) * 3600)


def poll():
    ensure_csv()
    configure_commands()
    if AUTO_COLLECT_INTERVAL_HOURS > 0 and REPORT_CHAT_ID:
        threading.Thread(target=auto_collect_loop, daemon=True).start()
    offset = 0
    print("Lead bot is running.")
    while True:
        try:
            result = api("getUpdates", {"timeout": 25, "offset": offset})
            for update in result.get("result", []):
                offset = max(offset, update["update_id"] + 1)
                message = update.get("message")
                if message:
                    handle_message(message)
                callback = update.get("callback_query")
                if callback:
                    handle_callback(callback)
        except Exception as exc:
            print(f"Bot error: {exc}")
            time.sleep(5)


if __name__ == "__main__":
    poll()
