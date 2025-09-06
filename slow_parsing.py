import requests, uuid
import asyncio

async def find_data(kpp_name: str):
    HEADERS = {
        "accept": "application/json, text/plain, */*",
        "x-client-locale": "uk",
        "x-user-agent": "UABorder/3.2.2 Web/1.1.0 User/guest",
        "origin": "https://echerha.gov.ua",
        "x-request-id": str(uuid.uuid4()),
    }

    data = requests.get(
        "https://back.echerha.gov.ua/api/v4/workload/1", headers=HEADERS, timeout=10
    ).json()

    for kpp in data["data"]:
        if kpp_name in kpp["title"]:
            return [kpp["id"], kpp["country_id"]]


if __name__ == "__main__":
    asyncio.run(find_data("Чоп"))


