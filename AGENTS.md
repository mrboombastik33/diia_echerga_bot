# AGENTS.md

Telegram-бот (aiogram 3), який моніторить черги на пунктах пропуску (КПП) через неофіційно використане API `echerha.gov.ua` і шле алерти, коли час очікування перевищує поріг користувача. Інтерфейс бота — українською. Є тести (`tests/`, pytest + pytest-asyncio), лінтера і CI немає.

## Запуск

```bash
source .venv/bin/activate        # або створити venv + pip install -r requirements.txt
echo "TELEGRAM_BOT_TOKEN=..." > .env
python bot.py                    # long polling, окремого білду немає
python -m additional_functionality.fetch   # ручна перевірка API (fetch_data за замовчуванням)
pip install -r requirements-dev.txt && python -m pytest   # тести (~3 с)
```

Змінні середовища: `TELEGRAM_BOT_TOKEN` (обов'язкова), `DATABASE_URL` (опційно; дефолт `sqlite+aiosqlite:///db.sqlite3`, відносно cwd). `postgres://` і `postgresql://` автоматично переписуються на `postgresql+asyncpg://` (деплой на Railway). `.env` і `db.sqlite3` у `.gitignore` — **не читай, не коміть і не виводь** вміст `.env`.

## Архітектура

```
bot.py                         усе: хендлери, FSM, фоновий цикл опитування, main()
keyboard_markup.py             ReplyKeyboard (головна + «Скасувати»)
db/db_setup.py                 engine, async_session, Base (+created_at/updated_at у всіх моделей)
db/db_interaction.py           моделі User, UserSession + усі DB-функції (SQLAlchemy 2.0 async ORM)
additional_functionality/
  fetch.py                     fetch_workload(country_id) -> list[dict] | None (весь список КПП країни;
                               спільна ClientSession, повтори на 429), fetch_data(country_id, target_id),
                               close_session()
  slow_parsing.py              find_data(name) -> [kpp_id, country_id] | None    (пошук КПП за назвою)
  task_manager.py              TaskManager: asyncio.Task на користувача (цикл моніторингу + серії алертів)
  additional.py                calc_time(сек)->рядок, parse_duration("д г хв")->сек
```

Незважаючи на назву, `slow_parsing.py` — це звичайний aiohttp-запит, не Playwright/Selenium.

### Потік даних

1. `/start` → `add_user_if_not_exists_simple`.
2. «🟡 Вибрати…» → FSM `Cfg.waiting_kpp` (пошук підрядка в `title` через `find_data`) → `Cfg.waiting_threshold` (формат `<дні> <години> <хвилини>`) → `set_user_threshold_database` (upsert по `(user_id, kpp_id)`).
3. «🟢 Почати перевірку» → `task_manager.start_task(user_id, send_periodic_data(...))`. Одна таска на користувача кожні `INTERVAL`=15 с робить **один запит на кожну країну** його КПП і перевіряє всі КПП з цієї відповіді.
4. Якщо `wait_time > threshold` — запускається серія `_send_alert_burst`: повідомлення **5 разів з паузою 5 с**. Серія йде окремою таскою (не блокує цикл), для пари `(user_id, kpp_id)` одночасно лише одна (`active_alerts`); коли серія закінчилась, а умова ще тримається — стартує нова. Це навмисно: алерт має будити людину.
5. Якщо успішних запитів немає понад `BLIND_AFTER`=180 с — один раз «⚠️ дані недоступні», після відновлення один раз «✅».
6. Статус «🟢/🔴 Моніторинг…» — одне закріплене повідомлення; його `message_id` зберігається в `user_table.status_message_id`, оновлюється через `edit_message_text`, при невдачі шлеться нове й пінниться.

### Схема БД (створюється `Base.metadata.create_all` у `init_db`, міграцій немає)

- `user_table`: `id` (Telegram user id, PK), `status_message_id`
- `user_session`: PK `(user_id → user_table.id, kpp_id)`, `country_id`, `threshold` (секунди)

Зміна колонок існуючої таблиці `create_all` **не застосує** — потрібна ручна міграція або видалення `db.sqlite3` (спитай користувача, бо там реальні дані).

### Зовнішнє API

`GET https://back.echerha.gov.ua/api/v5/workload/1[?country_id=N]` → `{"data": [{id, country_id, title, wait_time, is_paused, vehicle_in_active_queues_counts, ...}]}`. Потрібні заголовки `X-Client-Locale`, `X-User-Agent`, `X-Request-Id`, `origin` (регістр має значення — див. коміт `27fe65a`). Версія API вже змінювалась (v5), тож при 4xx/5xx спершу перевір, чи API не змінилось. API віддає `429` (на Railway це траплялось): `fetch_workload` повторює до 3 разів із паузою `Retry-After` (макс. 30 с) або 2/4/8 с, потім повертає `None`. `wait_time` — секунди.

## Конвенції

- Усе асинхронне (aiogram, aiohttp, SQLAlchemy async). Не додавай блокуючих викликів (`requests`, `time.sleep`).
- Нова DB-логіка — у `db/db_interaction.py`, кожна функція відкриває власну `async_session()` і сама комітить.
- Тексти для користувача, коментарі й логи — українською; ідентифікатори й коміти — англійською (`fix: ...`, `feat: ...`).
- Хендлери кнопок матчать `F.text == "<емодзі + текст>"`. Текст у `keyboard_markup.py` і в декораторі в `bot.py` має збігатися символ у символ, інакше кнопка «мовчить». Кожен хендлер кнопки починається з `await state.clear()` (навмисно, див. коміти про FSM leakage).
- Помилки API/мережі в `fetch_workload`/`fetch_data`/`find_data` ловляться і повертають `None` — викликачі мають обробляти `None`.
- Швидкість реакції на чергу критична (черга заповнюється за ~2 хв), а серія алертів навмисно настирлива: не зменшуй кількість повідомлень і не додавай антиспам без прямого прохання.

## Відомі підводні камені

- **`DATABASE_URL` з `.env` ігнорується**: `bot.py` імпортує `db.db_setup` (яке читає `os.getenv` на рівні модуля) *до* виклику `load_dotenv()`. Працює лише справжня змінна середовища. Фікс — викликати `load_dotenv()` до імпортів `db`.
- Таски моніторингу живуть лише в пам'яті: після рестарту бота вони не відновлюються, хоча закріплене повідомлення досі може показувати «🟢 Моніторинг активний».
- `find_data` повертає **перше** збігнене за підрядком КПП і неявний `None`, якщо нічого не знайдено. Заголовки продубльовані у `fetch.py` і `slow_parsing.py`.
- `fetch_data` тягне весь список КПП країни й фільтрує локально (кнопки «Показати дані»/«Мої налаштування» роблять запит на кожен КПП, кешу немає).
- У `show_data` / `show_kpp_settings` КПП, для яких API не відповів, мовчки пропускаються.
- Спільний поллер для багатьох користувачів не робився: користувач фактично один, кожен користувач має власний цикл і власні запити.
- `requirements.txt` — повний `pip freeze` зі зайвим: `playwright`, `selenium`, `webdriver-manager`, `requests`, `httpx`, `beautifulsoup4`, `python-telegram-bot`, `APScheduler` у коді **не використовуються**. Реально потрібні: `aiogram`, `aiohttp`, `SQLAlchemy`, `aiosqlite`, `asyncpg`, `python-dotenv`.
- `GEMINI.md` застарів (каже про Playwright і «`users`, `user_thresholds`»); джерело правди — цей файл.

## Перевірка змін

`python -m pytest`: `tests/test_fetch.py` (API проти локального aiohttp-сервера: 429, `Retry-After`, помилки), `tests/test_bot_loop.py` (цикл моніторингу з підміненими API/БД/Telegram: алерти, дедуп, «сліпота»), `tests/test_additional.py`. `tests/conftest.py` ставить фіктивний токен, бо `bot.py` створює `Bot` при імпорті. У тестах `asyncio.sleep` підмінений, щоб `sleep(5)` серії стискався. Реальне API echerha і Telegram тестами не покриті — для них `python -m additional_functionality.fetch` і живий запуск. Живий запуск бота потребує справжнього токена й може конфліктувати з уже запущеним інстансом (`TelegramConflictError`) — не запускай без потреби.
