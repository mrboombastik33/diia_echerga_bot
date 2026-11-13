"""fetch_workload проти локального aiohttp-сервера, який емулює echerha API."""
import pytest
from aiohttp import web

import additional_functionality.fetch as f

ROW = {"id": 17, "country_id": 167, "title": "Ягодин", "wait_time": 600}


@pytest.fixture
async def api(monkeypatch):
    """Повертає (state, set_handler). state['calls'] — список запитів."""
    state = {"calls": [], "handler": None}

    async def handler(request):
        state["calls"].append(request)
        return await state["handler"](request, len(state["calls"]))

    app = web.Application()
    app.router.add_get("/w", handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]

    monkeypatch.setattr(f, "WORKLOAD_URL", f"http://127.0.0.1:{port}/w")
    monkeypatch.setattr(f, "RETRY_DELAYS", (0.01, 0.01, 0.01))
    yield state
    await f.close_session()
    await runner.cleanup()


def ok(rows):
    return web.json_response({"data": rows})


async def test_success_and_request_shape(api):
    async def h(req, n):
        return ok([ROW])
    api["handler"] = h

    rows = await f.fetch_workload(167)

    assert rows == [ROW]
    req = api["calls"][0]
    assert req.query["country_id"] == "167"
    assert req.headers["X-Client-Locale"] == "uk"
    assert "X-Request-Id" in req.headers


async def test_no_country_id_means_no_query(api):
    async def h(req, n):
        return ok([])
    api["handler"] = h
    await f.fetch_workload()
    assert "country_id" not in api["calls"][0].query


async def test_request_id_unique_per_request(api):
    async def h(req, n):
        return ok([])
    api["handler"] = h
    await f.fetch_workload(1)
    await f.fetch_workload(1)
    ids = {c.headers["X-Request-Id"] for c in api["calls"]}
    assert len(ids) == 2


async def test_429_then_success(api):
    async def h(req, n):
        return web.Response(status=429) if n < 3 else ok([ROW])
    api["handler"] = h

    assert await f.fetch_workload(167) == [ROW]
    assert len(api["calls"]) == 3


async def test_429_forever_gives_up_after_retries(api):
    async def h(req, n):
        return web.Response(status=429, text="too many")
    api["handler"] = h

    assert await f.fetch_workload(167) is None
    assert len(api["calls"]) == len(f.RETRY_DELAYS) + 1


async def test_retry_after_header_is_respected(api, monkeypatch):
    sleeps = []
    real_sleep = f.asyncio.sleep

    async def fake_sleep(d):
        sleeps.append(d)
        await real_sleep(0)
    monkeypatch.setattr(f.asyncio, "sleep", fake_sleep)

    async def h(req, n):
        return web.Response(status=429, headers={"Retry-After": "7"}) if n == 1 else ok([ROW])
    api["handler"] = h

    assert await f.fetch_workload(167) == [ROW]
    assert sleeps == [7.0]


async def test_retry_after_is_capped(api, monkeypatch):
    sleeps = []
    real_sleep = f.asyncio.sleep

    async def fake_sleep(d):
        sleeps.append(d)
        await real_sleep(0)
    monkeypatch.setattr(f.asyncio, "sleep", fake_sleep)

    async def h(req, n):
        return web.Response(status=429, headers={"Retry-After": "9999"}) if n == 1 else ok([])
    api["handler"] = h

    await f.fetch_workload(1)
    assert sleeps == [f.MAX_RETRY_AFTER]


async def test_garbage_retry_after_falls_back_to_default(api, monkeypatch):
    sleeps = []
    real_sleep = f.asyncio.sleep

    async def fake_sleep(d):
        sleeps.append(d)
        await real_sleep(0)
    monkeypatch.setattr(f.asyncio, "sleep", fake_sleep)

    async def h(req, n):
        return web.Response(status=429, headers={"Retry-After": "soon"}) if n == 1 else ok([])
    api["handler"] = h

    await f.fetch_workload(1)
    assert sleeps == [f.RETRY_DELAYS[0]]


@pytest.mark.parametrize("status", [500, 502, 404])
async def test_other_errors_are_not_retried(api, status):
    async def h(req, n):
        return web.Response(status=status)
    api["handler"] = h

    assert await f.fetch_workload(1) is None
    assert len(api["calls"]) == 1


async def test_non_dict_json_returns_none(api):
    async def h(req, n):
        return web.json_response([1, 2, 3])
    api["handler"] = h
    assert await f.fetch_workload(1) is None


async def test_data_not_a_list_returns_none(api):
    async def h(req, n):
        return web.json_response({"data": "oops"})
    api["handler"] = h
    assert await f.fetch_workload(1) is None


async def test_invalid_json_returns_none(api):
    async def h(req, n):
        return web.Response(text="<html>", content_type="application/json")
    api["handler"] = h
    assert await f.fetch_workload(1) is None


async def test_network_error_returns_none(monkeypatch):
    monkeypatch.setattr(f, "WORKLOAD_URL", "http://127.0.0.1:1/w")  # ніхто не слухає
    try:
        assert await f.fetch_workload(1) is None
    finally:
        await f.close_session()


async def test_fetch_data_finds_target(api):
    async def h(req, n):
        return ok([{"id": 1}, ROW])
    api["handler"] = h
    assert await f.fetch_data(167, 17) == ROW
    assert await f.fetch_data(167, 999) is None


async def test_find_data_by_name(api):
    from additional_functionality.slow_parsing import find_data

    async def h(req, n):
        return ok([ROW, {"id": 2, "country_id": 5, "title": "Краківець"}])
    api["handler"] = h

    assert await find_data("ягод") == [17, 167]
    assert await find_data("КРАК") == [2, 5]
    assert await find_data("немає такого") is None


async def test_find_data_returns_none_on_api_failure(api):
    from additional_functionality.slow_parsing import find_data

    async def h(req, n):
        return web.Response(status=500)
    api["handler"] = h
    assert await find_data("x") is None


async def test_session_is_reused_and_recreated_after_close(api):
    async def h(req, n):
        return ok([])
    api["handler"] = h

    await f.fetch_workload(1)
    s1 = f._session
    await f.fetch_workload(1)
    assert f._session is s1

    await f.close_session()
    await f.fetch_workload(1)
    assert f._session is not s1
