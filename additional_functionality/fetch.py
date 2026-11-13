import aiohttp
import asyncio
import uuid
import logging
import time

WORKLOAD_URL = "https://back.echerha.gov.ua/api/v5/workload/1"

# Паузи між повторами після 429, якщо API не віддав Retry-After
RETRY_DELAYS = (2, 4, 8)
MAX_RETRY_AFTER = 120

_session: aiohttp.ClientSession | None = None
_lock: asyncio.Lock | None = None
# Спільна для всього процесу пауза: після 429 жоден виклик не б'є в API до її кінця
_cooldown_until: float = 0.0
# Остання успішна відповідь: country_id -> (monotonic-час, rows)
_cache: dict[int | None, tuple[float, list[dict]]] = {}


def _headers() -> dict:
    return {
        "accept": "application/json, text/plain, */*",
        "X-Client-Locale": "uk",
        "X-User-Agent": "UABorder/3.2.2 Web/1.1.0 User/guest",
        "origin": "https://echerha.gov.ua",
        "referer": "https://echerha.gov.ua/workload/truck/1",
        "X-Request-Id": str(uuid.uuid4()),
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }


def _get_session() -> aiohttp.ClientSession:
    global _session
    if _session is None or _session.closed:
        _session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10))
    return _session


def _get_lock() -> asyncio.Lock:
    global _lock
    if _lock is None:
        _lock = asyncio.Lock()
    return _lock


async def close_session() -> None:
    global _session, _lock, _cooldown_until
    if _session is not None and not _session.closed:
        await _session.close()
    _session = None
    _lock = None
    _cooldown_until = 0.0
    _cache.clear()


def cooldown_remaining() -> float:
    return max(0.0, _cooldown_until - time.monotonic())


def _start_cooldown(resp: aiohttp.ClientResponse, attempt: int) -> float:
    """Ставить спільну паузу після 429 і повертає її тривалість."""
    global _cooldown_until
    raw = resp.headers.get("Retry-After")
    delay = None
    if raw:
        try:
            delay = min(max(float(raw), 0), MAX_RETRY_AFTER)
        except ValueError:
            pass
    if delay is None:
        delay = RETRY_DELAYS[min(attempt, len(RETRY_DELAYS) - 1)]

    limit_headers = {k: v for k, v in resp.headers.items()
                     if k.lower() == "retry-after" or "ratelimit" in k.lower() or "rate-limit" in k.lower()}
    logging.warning("fetch_workload: 429, пауза %.1f с (спроба %d), заголовки ліміту: %s",
                    delay, attempt + 1, limit_headers or "немає")
    _cooldown_until = max(_cooldown_until, time.monotonic() + delay)
    return delay


async def fetch_workload(country_id: int | None = None, wait: bool = True) -> list[dict] | None:
    """Повертає список усіх КПП (поле `data`) або None, якщо отримати не вдалося.

    Запити йдуть по одному (lock), а після 429 діє спільна пауза (Retry-After або 2/4/8 с).
    wait=True: чекає паузу й повторює до len(RETRY_DELAYS) разів (для циклу моніторингу).
    wait=False: якщо пауза активна або інший запит уже йде — одразу None; на 429 не повторює
    (для кнопок, щоб не блокувати відповіді користувачу).
    """
    url = WORKLOAD_URL if country_id is None else f"{WORKLOAD_URL}?country_id={country_id}"
    lock = _get_lock()

    if not wait and (lock.locked() or cooldown_remaining() > 0):
        return None

    async with lock:
        for attempt in range(len(RETRY_DELAYS) + 1):
            remaining = cooldown_remaining()
            if remaining > 0:
                if not wait:
                    return None
                await asyncio.sleep(remaining)

            try:
                async with _get_session().get(url, headers=_headers()) as resp:
                    if resp.status == 429:
                        _start_cooldown(resp, attempt)
                        if wait and attempt < len(RETRY_DELAYS):
                            continue
                        return None
                    if resp.status != 200:
                        body = await resp.text()
                        logging.error("fetch_workload: API status %s, body: %s", resp.status, body[:200])
                        return None
                    data = await resp.json()
            except asyncio.CancelledError:
                raise
            except Exception:
                logging.exception("Помилка при отриманні даних для country_id=%s", country_id)
                return None

            if not isinstance(data, dict):
                logging.error("fetch_workload: unexpected response type: %s", type(data))
                return None
            rows = data.get("data", [])
            if not isinstance(rows, list):
                return None
            _cache[country_id] = (time.monotonic(), rows)
            return rows

    return None


async def get_entry(country_id: int, target_id: int, max_age: float = 60.0) -> tuple[dict | None, float | None]:
    """Стан одного КПП для кнопок: (entry, вік_даних_у_секундах).

    Бере свіжий кеш; якщо кеш старший за max_age — пробує один запит без очікування;
    якщо не вийшло — віддає застарілий кеш (з віком), інакше (None, None).
    """
    cached = _cache.get(country_id)
    now = time.monotonic()
    if cached and now - cached[0] <= max_age:
        rows, age = cached[1], now - cached[0]
    else:
        fresh = await fetch_workload(country_id, wait=False)
        if fresh is not None:
            rows, age = fresh, 0.0
        elif cached:
            rows, age = cached[1], time.monotonic() - cached[0]
        else:
            return None, None
    entry = next((row for row in rows if row.get("id") == target_id), None)
    return entry, age


async def fetch_data(country_id: int = 167, target_id: int = 17) -> dict | None:
    rows = await fetch_workload(country_id)
    if rows is None:
        return None
    return next((row for row in rows if row.get("id") == target_id), None)


async def main():
    try:
        result = await fetch_data()
        if result:
            print("Знайдено:", result)
        else:
            print("Об’єкт не знайдено!")
        print(type(result))
    finally:
        await close_session()

if __name__ == "__main__":
    asyncio.run(main())
