import aiohttp
import asyncio
import uuid
import logging

async def fetch_data(country_id: int = 167, target_id: int = 17) -> dict | None:
    URL = "https://back.echerha.gov.ua/api/v5/workload/1?country_id={}"

    HEADERS = {
        "accept": "application/json, text/plain, */*",
        "X-Client-Locale": "uk",
        "X-User-Agent": "UABorder/3.2.2 Web/1.1.0 User/guest",
        "origin": "https://echerha.gov.ua",
        "referer": "https://echerha.gov.ua/workload/truck/1",
        "X-Request-Id": str(uuid.uuid4()),
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(URL.format(country_id), headers=HEADERS, timeout=10) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    logging.error("fetch_data: API status %s, body: %s", resp.status, body[:200])
                    return None
                data = await resp.json()
                if not isinstance(data, dict):
                    logging.error("fetch_data: unexpected response type: %s", type(data))
                    return None

                entry = next(
                    (row for row in data.get("data", []) if row.get("id") == target_id),
                    None
                )
                return entry
    except Exception:
        logging.exception("Помилка при отриманні даних для country_id=%s target_id=%s", country_id, target_id)
        return None

async def main():
    result = await fetch_data()
    if result:
        print("Знайдено:", result)
    else:
        print("Об’єкт не знайдено!")
    print(type(result))

if __name__ == "__main__":
    asyncio.run(main())
