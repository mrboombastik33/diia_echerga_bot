import aiohttp
import asyncio
import uuid
import logging

WORKLOAD_URL = "https://back.echerha.gov.ua/api/v5/workload/1"

# Паузи між повторами після 429, якщо API не віддав Retry-After
RETRY_DELAYS = (2, 4, 8)
MAX_RETRY_AFTER = 30

_session: aiohttp.ClientSession | None = None


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


async def close_session() -> None:
    global _session
    if _session is not None and not _session.closed:
        await _session.close()
    _session = None


def _retry_delay(resp: aiohttp.ClientResponse, attempt: int) -> float:
    retry_after = resp.headers.get("Retry-After")
    if retry_after:
        try:
            return min(max(float(retry_after), 0), MAX_RETRY_AFTER)
        except ValueError:
            pass
    return RETRY_DELAYS[attempt]


async def fetch_workload(country_id: int | None = None) -> list[dict] | None:
    """Повертає список усіх КПП (поле `data`) або None, якщо отримати не вдалося.

    На 429 робить до len(RETRY_DELAYS) повторів з паузою (Retry-After або 2/4/8 с).
    """
    url = WORKLOAD_URL if country_id is None else f"{WORKLOAD_URL}?country_id={country_id}"

    for attempt in range(len(RETRY_DELAYS) + 1):
        try:
            async with _get_session().get(url, headers=_headers()) as resp:
                if resp.status == 429 and attempt < len(RETRY_DELAYS):
                    delay = _retry_delay(resp, attempt)
                    logging.warning("fetch_workload: 429, повтор через %.1f с (спроба %d)", delay, attempt + 1)
                    await asyncio.sleep(delay)
                    continue
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
        return rows if isinstance(rows, list) else None

    return None


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
