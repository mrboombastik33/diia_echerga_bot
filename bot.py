import asyncio
import os
import logging
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext

from fetch import fetch_data
from additional import calc_time, parse_duration
from keyboard_markup import keyboard

from db.db_interaction import init_db, get_user_threshold, set_user_threshold, add_user_if_not_exists


load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

"""Hardcoded info about certain country"""
TARGET_ID = 17
COUNTRY_ID = 167

INTERVAL = 60 * 5

logging.basicConfig(level=logging.INFO)
bot = Bot(TELEGRAM_BOT_TOKEN)
dp = Dispatcher()

user_tasks = {}

class Cfg(StatesGroup):
    waiting_threshold = State()


async def send_periodic_data(user_id: int):
    while True:
        try:
            threshold = await get_user_threshold(user_id)
            entry = await fetch_data(country_id=COUNTRY_ID, target_id=TARGET_ID)

            if entry:
                if entry["wait_time"] > threshold:
                    text = (
                        "Знайдено:\n"
                        f"{entry['title']}\n"
                        f"Черга {'не ' if not entry['is_paused'] else ''}затримується\n"
                        f"Час очікування: {calc_time(entry['wait_time'])}\n"
                        f"Черга авто: {entry['vehicle_in_active_queues_counts']}"
                    )
                    for _ in range(10):
                        await bot.send_message(user_id, text)
                        await asyncio.sleep(10)
            else:
                await bot.send_message(user_id, "Об'єкт не знайдено!")
            await asyncio.sleep(INTERVAL)

        except asyncio.CancelledError:
            logging.info(f"Task for user {user_id} cancelled.")
            break
        except Exception as exc:
            logging.exception("Помилка під час надсилання: %s", exc)



@dp.message(CommandStart())
async def cmd_start(message: Message):
    user_id = message.from_user.id
    await add_user_if_not_exists(user_id)
    await message.answer("Бот запущено. Використовуйте кнопки для керування роботою бота", reply_markup=keyboard)

@dp.message(F.text == "🟢 Почати перевірку")
async def start_checking(message: Message):
    user_id = message.from_user.id
    await add_user_if_not_exists(user_id)
    task = user_tasks.get(user_id)
    if task and not task.done():
        await message.answer("Перевірка вже запущена")
        return
    user_tasks[user_id] = asyncio.create_task(send_periodic_data(user_id))
    await message.answer("Запустив перевірку. Дані приходитимуть кожні "
                         f"{INTERVAL} секунд.")

@dp.message(F.text == "🔴 Зупинити перевірку")
async def stop_checking(message: Message):
    user_id = message.from_user.id
    task = user_tasks.get(user_id)
    if task and not task.done():
        task.cancel()
        user_tasks.pop(user_id, None)
        await message.answer("Зупинив перевірку. ")
    else:
        await message.answer("Перевірка вже неактивна.")

@dp.message(F.text == "🟡 Час для перевірки")
async def set_threshold(message: Message, state: FSMContext):
    user_id = message.from_user.id
    await add_user_if_not_exists(user_id)
    await stop_checking(message)
    await message.answer("Введіть поріг у форматі «10 днів 7 годин 5 хвилин» (10 7 5).")
    await state.set_state(Cfg.waiting_threshold)

@dp.message(Cfg.waiting_threshold)
async def save_threshold(message: Message, state: FSMContext):
    user_id = message.from_user.id
    await add_user_if_not_exists(user_id)
    try:
        wait_threshold = parse_duration(message.text)
        await set_user_threshold(user_id, wait_threshold)
        await message.answer(f"Новий поріг: {wait_threshold} секунд.")
        await state.clear()
        await start_checking(message)
    except ValueError as err:
        await message.answer(f"Помилка: {err}\nСпробуйте ще раз.")


async def main():
    await init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
