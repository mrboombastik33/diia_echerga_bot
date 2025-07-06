import aiohttp
import asyncio
import uuid

async def fetch_data(country_id: int = 167, target_id: int = 17) -> dict | None:
    URL = "https://back.echerha.gov.ua/api/v4/workload/1?country_id={}"

    HEADERS = {
        "accept": "application/json, text/plain, */*",
        "x-client-locale": "uk",
        "x-user-agent": "UABorder/3.2.2 Web/1.1.0 User/guest",
        "origin": "https://echerha.gov.ua",
        "x-request-id": str(uuid.uuid4()),
    }

    async with aiohttp.ClientSession() as session:
        async with session.get(URL.format(country_id), headers=HEADERS, timeout=10) as resp:
            resp.raise_for_status()
            data = await resp.json()

            entry = next(
                (row for row in data["data"] if row["id"] == target_id),
                None
            )
            return entry

async def main():
    result = await fetch_data()
    if result:
        print("Знайдено:", result)
    else:
        print("Об’єкт із id=17 не знайдено!")

if __name__ == "__main__":
    asyncio.run(main())

