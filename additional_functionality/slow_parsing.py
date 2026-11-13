from additional_functionality.fetch import fetch_workload


async def find_data(kpp_name: str):
    rows = await fetch_workload()
    if rows is None:
        return None
    for kpp in rows:
        if kpp_name.lower() in kpp.get("title", "").lower():
            return [kpp["id"], kpp["country_id"]]
    return None
