import aiohttp
import uuid
import logging

async def find_data(kpp_name: str):
    HEADERS = {
        "accept": "application/json, text/plain, */*",
        "x-client-locale": "uk",
        "x-user-agent": "UABorder/3.2.2 Web/1.1.0 User/guest",
        "origin": "https://echerha.gov.ua",
        "x-request-id": str(uuid.uuid4()),
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://back.echerha.gov.ua/api/v4/workload/1", headers=HEADERS, timeout=10
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    logging.error("find_data: API status %s, body: %s", resp.status, body[:200])
                    return None
                data = await resp.json()
                if not isinstance(data, dict):
                    logging.error("find_data: unexpected response type: %s", type(data))
                    return None
                for kpp in data.get("data", []):
                    if kpp_name.lower() in kpp.get("title", "").lower():
                        return [kpp["id"], kpp["country_id"]]
    except Exception:
        logging.exception("Помилка при пошуку КПП за назвою: %s", kpp_name)
        return None
