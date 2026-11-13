"""send_periodic_data з підміненими API/БД/Telegram: перевіряємо логіку алертів."""
import asyncio

import pytest

import bot as botmod

USER = 42
KPP_A = {"id": 1, "country_id": 10, "title": "Ягодин", "wait_time": 7200,
         "is_paused": False, "vehicle_in_active_queues_counts": 15}
KPP_B = {"id": 2, "country_id": 10, "title": "Краківець", "wait_time": 60}


class Env:
    def __init__(self):
        self.thresholds = []
        self.rows_by_country = {}     # country_id -> rows | None (збій)
        self.fetch_calls = []
        self.sent = []                # (user_id, text) від send_long_message
        self.bot_msgs = []            # bot.send_message
        self.burst_sleep = 0.005      # реальна тривалість "5 с" між повідомленнями серії


@pytest.fixture
def env(monkeypatch):
    e = Env()
    real_sleep = asyncio.sleep

    async def fast_sleep(d):
        # sleep(5) із серії стискаємо; інтервал циклу (<1 с) лишаємо як є
        await real_sleep(e.burst_sleep if d >= 1 else d)

    async def get_thresholds(user_id):
        return list(e.thresholds)

    async def fetch_workload(country_id):
        e.fetch_calls.append(country_id)
        return e.rows_by_country.get(country_id)

    async def send_long_message(user_id, text, reply_markup=None):
        e.sent.append((user_id, text))

    async def bot_send_message(user_id, text, **kw):
        e.bot_msgs.append((user_id, text))

    monkeypatch.setattr(botmod.asyncio, "sleep", fast_sleep)
    monkeypatch.setattr(botmod, "get_user_thresholds_database", get_thresholds)
    monkeypatch.setattr(botmod, "fetch_workload", fetch_workload)
    monkeypatch.setattr(botmod, "send_long_message", send_long_message)
    monkeypatch.setattr(botmod.bot, "send_message", bot_send_message)
    monkeypatch.setattr(botmod, "task_manager", botmod.TaskManager())
    botmod.active_alerts.clear()
    yield e
    botmod.task_manager.stop_tasks(USER)
    botmod.active_alerts.clear()


def th(kpp_id, threshold, country_id=10):
    return {"kpp_id": kpp_id, "country_id": country_id, "threshold": threshold}


def start(interval=0.02):
    botmod.task_manager.start_task(USER, botmod.send_periodic_data(USER, interval))


async def wait_for(cond, timeout=2.0):
    loop = asyncio.get_running_loop()
    end = loop.time() + timeout
    while loop.time() < end:
        if cond():
            return True
        await asyncio.sleep(0.005)
    return cond()


async def test_alert_burst_of_five_when_above_threshold(env):
    env.thresholds = [th(1, 3600)]
    env.rows_by_country = {10: [KPP_A]}
    start()

    assert await wait_for(lambda: len(env.sent) >= 5)
    text = env.sent[0][1]
    assert "Ягодин" in text and "2 годин" in text and "15" in text
    assert "Черга обслуговується" in text
    assert env.sent[0][0] == USER


async def test_paused_queue_text(env):
    env.thresholds = [th(1, 0)]
    env.rows_by_country = {10: [{**KPP_A, "is_paused": True}]}
    start()
    assert await wait_for(lambda: env.sent)
    assert "Черга не обслуговується" in env.sent[0][1]


async def test_no_alert_below_or_equal_threshold(env):
    env.thresholds = [th(1, 7200), th(2, 3600)]  # A == поріг, B нижче порогу
    env.rows_by_country = {10: [KPP_A, KPP_B]}
    start()

    assert await wait_for(lambda: len(env.fetch_calls) >= 3)
    assert env.sent == []


async def test_one_fetch_per_country_per_cycle(env):
    env.thresholds = [th(1, 99999), th(2, 99999), th(3, 99999, country_id=20)]
    env.rows_by_country = {10: [KPP_A, KPP_B], 20: [{"id": 3, "wait_time": 1}]}
    start(interval=0.5)

    assert await wait_for(lambda: len(env.fetch_calls) >= 2)
    await asyncio.sleep(0.05)
    assert sorted(env.fetch_calls) == [10, 20]  # перший цикл: по одному разу


async def test_missing_kpp_or_wait_time_is_ignored(env):
    env.thresholds = [th(999, 0), th(2, 0)]
    env.rows_by_country = {10: [{"id": 2, "title": "без wait_time"}]}
    start()
    assert await wait_for(lambda: len(env.fetch_calls) >= 3)
    assert env.sent == []


async def test_no_overlapping_bursts_for_same_kpp(env):
    env.burst_sleep = 0.3          # серія повільна, цикл швидкий (кожні 10 мс)
    env.thresholds = [th(1, 0)]
    env.rows_by_country = {10: [KPP_A]}
    start(interval=0.01)

    assert await wait_for(lambda: env.sent)
    await asyncio.sleep(0.15)      # ~15 циклів перевірки за цей час
    assert len(env.sent) == 1      # нова серія не стартувала, поки йде перша
    assert botmod.active_alerts == {(USER, 1)}


async def test_loop_is_not_blocked_by_burst(env):
    """Серія для КПП 1 повільна (0.4 с між повідомленнями), але КПП 2 не чекає."""
    env.burst_sleep = 0.4
    env.thresholds = [th(1, 0)]
    env.rows_by_country = {10: [KPP_A, {**KPP_B, "wait_time": 500}]}
    start(interval=0.01)
    assert await wait_for(lambda: any("Ягодин" in t for _, t in env.sent))

    # додаємо другий КПП, поки перша серія ще йде
    env.thresholds = [th(1, 0), th(2, 0)]
    assert await wait_for(lambda: any("Краківець" in t for _, t in env.sent), timeout=0.3)
    a_msgs = [t for _, t in env.sent if "Ягодин" in t]
    assert len(a_msgs) < 5  # перша серія ще не закінчилась


async def test_stop_cancels_burst_and_frees_key(env):
    env.thresholds = [th(1, 0)]
    env.rows_by_country = {10: [KPP_A]}
    start()
    assert await wait_for(lambda: env.sent)

    botmod.task_manager.stop_tasks(USER)
    await asyncio.sleep(0.05)

    assert botmod.active_alerts == set()
    n = len(env.sent)
    await asyncio.sleep(0.1)
    assert len(env.sent) == n  # більше нічого не надсилається
    assert not botmod.task_manager.is_active(USER)


async def test_alert_resumes_after_burst_finishes_if_still_above(env):
    env.thresholds = [th(1, 0)]
    env.rows_by_country = {10: [KPP_A]}
    start(interval=0.01)
    assert await wait_for(lambda: len(env.sent) >= 10)  # друга серія стартувала


async def test_blind_warning_sent_once_and_recovery_once(env, monkeypatch):
    monkeypatch.setattr(botmod, "BLIND_AFTER", 0.05)
    env.thresholds = [th(1, 99999)]
    env.rows_by_country = {10: None}  # API недоступне
    start(interval=0.01)

    assert await wait_for(lambda: any("⚠️" in t for _, t in env.bot_msgs))
    await asyncio.sleep(0.1)
    assert sum("⚠️" in t for _, t in env.bot_msgs) == 1   # не спамить

    env.rows_by_country = {10: [KPP_A]}
    assert await wait_for(lambda: any("✅" in t for _, t in env.bot_msgs))
    await asyncio.sleep(0.1)
    assert sum("✅" in t for _, t in env.bot_msgs) == 1

    # і знову можна попередити при новому збої
    env.rows_by_country = {10: None}
    assert await wait_for(lambda: sum("⚠️" in t for _, t in env.bot_msgs) == 2)


async def test_no_blind_warning_for_short_outage(env, monkeypatch):
    monkeypatch.setattr(botmod, "BLIND_AFTER", 10)
    env.thresholds = [th(1, 99999)]
    env.rows_by_country = {10: None}
    start(interval=0.01)
    assert await wait_for(lambda: len(env.fetch_calls) >= 5)
    assert env.bot_msgs == []


async def test_partial_failure_is_not_blind(env, monkeypatch):
    """Одна країна відповідає — моніторинг не «сліпий»."""
    monkeypatch.setattr(botmod, "BLIND_AFTER", 0.03)
    env.thresholds = [th(1, 99999), th(3, 99999, country_id=20)]
    env.rows_by_country = {10: [KPP_A], 20: None}
    start(interval=0.01)
    assert await wait_for(lambda: len(env.fetch_calls) >= 10)
    assert env.bot_msgs == []


async def test_no_thresholds_means_no_requests(env):
    env.thresholds = []
    start(interval=0.01)
    await asyncio.sleep(0.1)
    assert env.fetch_calls == []


async def test_loop_survives_unexpected_exception(env, monkeypatch):
    calls = {"n": 0}

    async def flaky(user_id):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("db hiccup")
        return [th(1, 0)]

    monkeypatch.setattr(botmod, "get_user_thresholds_database", flaky)
    env.rows_by_country = {10: [KPP_A]}
    start(interval=0.01)
    assert await wait_for(lambda: env.sent)  # після помилки цикл живий


async def test_cancel_stops_loop_cleanly(env):
    env.thresholds = [th(1, 99999)]
    env.rows_by_country = {10: [KPP_A]}
    start(interval=0.01)
    await wait_for(lambda: env.fetch_calls)
    botmod.task_manager.stop_tasks(USER)
    await asyncio.sleep(0.05)
    assert not botmod.task_manager.is_active(USER)
