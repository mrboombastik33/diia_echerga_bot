import asyncio
import os
import logging
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext

from additional_functionality.fetch import fetch_data
from additional_functionality.additional import calc_time, parse_duration
from keyboard_markup import keyboard

from db.db_interaction import (init_db, get_user_thresholds_database, set_user_threshold_database,
                               add_user_if_not_exists_simple, show_user_data)
from additional_functionality.slow_parsing import find_data
from additional_functionality.task_manager import TaskManager


load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")


INTERVAL = 300

logging.basicConfig(level=logging.INFO)
bot = Bot(TELEGRAM_BOT_TOKEN)
dp = Dispatcher()

task_manager = TaskManager()

class Cfg(StatesGroup):
    waiting_kpp = State()
    waiting_threshold = State()


async def send_periodic_data(user_id: int, interval: int):
    while True:
        try:
            thresholds = await get_user_thresholds_database(user_id)

            print(f"Перевірка запущена для юзера {user_id}")

            if not thresholds:
                await bot.send_message(user_id, "⚠️ У вас немає збережених КПП для перевірки")
                await asyncio.sleep(interval)
                continue

            for threshold_data in thresholds:
                kpp_id = threshold_data["kpp_id"]
                country_id = threshold_data["country_id"]
                threshold = threshold_data["threshold"]

                await asyncio.sleep(1)

                entry = await fetch_data(country_id=country_id, target_id=kpp_id)

                if not entry:
                    await bot.send_message(user_id, f"⚠️ КПП {kpp_id} не знайдено")
                    continue

                if threshold is not None and entry["wait_time"] > threshold:
                    text = (
                        "Знайдено:\n"
                        f"{entry['title']}\n"
                        f"Черга {'не ' if not entry['is_paused'] else ''}затримується\n"
                        f"Час очікування: {calc_time(entry['wait_time'])}\n"
                        f"Черга авто: {entry['vehicle_in_active_queues_counts']}"
                    )
                    for i in range(10):
                        await bot.send_message(user_id, text)
                        await asyncio.sleep(10)


            await asyncio.sleep(interval)

        except asyncio.CancelledError:
            logging.info(f"Таска для юзера {user_id} відмінена.")
            break
        except Exception as exc:
            logging.exception("Помилка під час надсилання: %s", exc)
            await asyncio.sleep(interval)  # не падаємо, а чекаємо



@dp.message(CommandStart())
async def cmd_start(message: Message):
    user_id = message.from_user.id
    await add_user_if_not_exists_simple(user_id)
    await message.answer("Бот запущено. Використовуйте кнопки для керування роботою бота", reply_markup=keyboard)


@dp.message(F.text == "🟢 Почати перевірку")
async def start_checking(message: Message):
    user_id = message.from_user.id
    if task_manager.is_active(user_id):
        await message.answer("Перевірка вже запущена")
        return

    thresholds = await get_user_thresholds_database(user_id)
    if not thresholds:
        await message.answer("⚠️ У вас ще немає збережених КПП.")
        return

    # Запускаємо одну таску, яка перевіряє всі КПП цього юзера
    task_manager.start_task(
        user_id,
        send_periodic_data(user_id, INTERVAL)
    )
    await message.answer(f"✅ Запустив перевірку. Дані приходитимуть кожні {INTERVAL} секунд.")



@dp.message(F.text == "🔴 Зупинити перевірку")
async def stop_checking(message: Message):
    user_id = message.from_user.id
    if task_manager.is_active(user_id):
        task_manager.stop_tasks(user_id)
        await message.answer("Перевірку зупинено.")
    else:
        await message.answer("ℹ️ Перевірка вже неактивна.")


# Вибір КПП
@dp.message(F.text == "🟡 Вибрати час та КПП для перевірки")
async def set_kpp(message: Message, state: FSMContext):
    await message.answer("Введіть назву пропускного пункту")
    await state.set_state(Cfg.waiting_kpp)


@dp.message(Cfg.waiting_kpp)
async def save_kpp(message: Message, state: FSMContext):
    kpp_name = message.text
    kpp_data = await find_data(kpp_name)

    if not kpp_data:
        await message.answer("КПП не знайдено. Спробуйте ще раз.")
        return

    await state.update_data(kpp_id=kpp_data[0], country_id = kpp_data[1])
    await message.answer("КПП збережено. Тепер введіть час перевірки (наприклад: 10 7 5 - 10 днів 7 годин 5 хвилин)")
    await state.set_state(Cfg.waiting_threshold)


# Встановлюємо час
@dp.message(Cfg.waiting_threshold)
async def save_threshold(message: Message, state: FSMContext):
    user_id = message.from_user.id
    await add_user_if_not_exists_simple(user_id)

    data = await state.get_data()
    kpp_id = data["kpp_id"]
    country_id = data["country_id"]
    wait_threshold = parse_duration(message.text)

    await set_user_threshold_database(user_id, wait_threshold, kpp_id, country_id)

    if not task_manager.is_active(user_id):
        await start_checking(message)

    await state.clear()
    await message.answer("✅ Поріг збережено.")


@dp.message(F.text == "🔵 Показати дані про КПП")
async def show_data(message : Message):
    user_id = message.from_user.id
    kpps = await show_user_data(user_id)
    text = "Ваші сессії:\n"
    for data in kpps:
        kpp = await fetch_data(data["country_id"], data["id"])
        text += f"\nНазва: {kpp['title']} \nЧас очікування: {calc_time(kpp['wait_time'])}\n"
    await bot.send_message(user_id, text)


async def main():
    await init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
