"""fetch_workload проти локального aiohttp-сервера, який емулює echerha API."""
import asyncio

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
    await f.close_session()  # чистий стан: пауза, кеш, lock
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
    assert sleeps == [pytest.approx(7.0, abs=0.1)]


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
    assert sleeps == [pytest.approx(f.MAX_RETRY_AFTER, abs=0.1)]


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
    assert sleeps == [pytest.approx(f.RETRY_DELAYS[0], abs=0.01)]


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


# ---- спільна пауза, режим wait=False, кеш для кнопок ----

async def test_cooldown_is_shared_between_callers(api):
    """Після 429 другий виклик не б'є в API, поки діє пауза першого."""
    async def h(req, n):
        if n == 1:
            return web.Response(status=429, headers={"Retry-After": "0.3"})
        return ok([ROW])
    api["handler"] = h

    first = asyncio.create_task(f.fetch_workload(167))
    await asyncio.sleep(0.05)               # перший отримав 429 і чекає паузу
    t = asyncio.get_running_loop().time()
    second = await f.fetch_workload(167)    # стає в чергу за lock і чекає паузу
    waited = asyncio.get_running_loop().time() - t

    assert await first == [ROW] and second == [ROW]
    assert waited >= 0.2                    # не пішов у API одразу
    times = [c for c in api["calls"]]
    assert len(times) == 3                  # 429 + дві успішні, без зайвих 429


async def test_requests_are_serialized(api):
    inflight = {"now": 0, "max": 0}

    async def h(req, n):
        inflight["now"] += 1
        inflight["max"] = max(inflight["max"], inflight["now"])
        await asyncio.sleep(0.05)
        inflight["now"] -= 1
        return ok([ROW])
    api["handler"] = h

    await asyncio.gather(*(f.fetch_workload(1) for _ in range(4)))
    assert inflight["max"] == 1


async def test_cooldown_survives_giving_up(api):
    """Навіть коли виклик здався після 429, наступний чекає паузу, а не лупить одразу."""
    async def h(req, n):
        return web.Response(status=429, headers={"Retry-After": "0.2"})
    api["handler"] = h

    assert await f.fetch_workload(1, wait=False) is None   # 1 запит, 429, без повторів
    assert len(api["calls"]) == 1
    assert f.cooldown_remaining() > 0
    assert await f.fetch_workload(1, wait=False) is None   # пауза: в API не ходили
    assert len(api["calls"]) == 1


async def test_wait_false_does_not_retry_on_429(api):
    async def h(req, n):
        return web.Response(status=429)
    api["handler"] = h
    assert await f.fetch_workload(1, wait=False) is None
    assert len(api["calls"]) == 1


async def test_wait_false_returns_immediately_when_busy(api):
    gate = asyncio.Event()

    async def h(req, n):
        await gate.wait()
        return ok([ROW])
    api["handler"] = h

    slow = asyncio.create_task(f.fetch_workload(1))
    await asyncio.sleep(0.05)
    assert await f.fetch_workload(1, wait=False) is None   # lock зайнятий
    gate.set()
    assert await slow == [ROW]


async def test_429_logs_rate_limit_headers(api, caplog):
    async def h(req, n):
        return web.Response(status=429, headers={"Retry-After": "5", "X-RateLimit-Remaining": "0"})
    api["handler"] = h
    await f.fetch_workload(1, wait=False)
    assert "Retry-After" in caplog.text and "X-RateLimit-Remaining" in caplog.text


async def test_get_entry_uses_fresh_cache_without_api_call(api):
    async def h(req, n):
        return ok([ROW])
    api["handler"] = h

    await f.fetch_workload(167)
    assert len(api["calls"]) == 1
    entry, age = await f.get_entry(167, 17)
    assert entry == ROW and age < 1
    assert len(api["calls"]) == 1                          # з кешу


async def test_get_entry_refetches_when_cache_is_stale(api):
    async def h(req, n):
        return ok([{**ROW, "wait_time": n}])
    api["handler"] = h

    await f.fetch_workload(167)
    ts, rows = f._cache[167]
    f._cache[167] = (ts - 1000, rows)                      # зістарити кеш
    entry, age = await f.get_entry(167, 17, max_age=60)
    assert entry["wait_time"] == 2 and age == 0
    assert len(api["calls"]) == 2


async def test_get_entry_falls_back_to_stale_cache_when_api_fails(api):
    state = {"fail": False}

    async def h(req, n):
        return web.Response(status=429) if state["fail"] else ok([ROW])
    api["handler"] = h

    await f.fetch_workload(167)
    ts, rows = f._cache[167]
    f._cache[167] = (ts - 500, rows)
    state["fail"] = True
    entry, age = await f.get_entry(167, 17, max_age=60)
    assert entry == ROW and age >= 500                     # застарілі, але є


async def test_get_entry_without_cache_and_api_down(api):
    async def h(req, n):
        return web.Response(status=500)
    api["handler"] = h
    assert await f.get_entry(167, 17) == (None, None)


async def test_get_entry_unknown_kpp(api):
    async def h(req, n):
        return ok([ROW])
    api["handler"] = h
    entry, age = await f.get_entry(167, 999)
    assert entry is None and age is not None
