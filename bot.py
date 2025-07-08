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


load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_USER_ID = int(os.getenv("TELEGRAM_USER_ID"))

"""Hardcoded info about certain country"""
TARGET_ID = 17
COUNTRY_ID = 167

INTERVAL = 60 * 5

"""К-сть секунд для перевірки"""
WAIT_THRESHOLD = None

logging.basicConfig(level=logging.INFO)
bot = Bot(TELEGRAM_BOT_TOKEN)
dp = Dispatcher()

periodic_task: asyncio.Task | None = None

class Cfg(StatesGroup):
    waiting_threshold = State()


async def send_periodic_data():
    while True:
        try:
            entry = await fetch_data(country_id=COUNTRY_ID, target_id=TARGET_ID)
            if entry:
                if entry["wait_time"] > WAIT_THRESHOLD:
                    text = (
                        "Знайдено:\n"
                        f"{entry['title']}\n"
                        f"Черга {'не ' if not entry['is_paused'] else ''}затримується\n"
                        f"Час очікування: {calc_time(entry['wait_time'])}\n"
                        f"Черга авто: {entry['vehicle_in_active_queues_counts']}"
                    )
                    for i in range(10):
                        await bot.send_message(TELEGRAM_USER_ID, text)
                        await asyncio.sleep(10)
                        i += 1
            else:
                text = "Об'єкт не знайдено!"
                await bot.send_message(TELEGRAM_USER_ID, text)
            await asyncio.sleep(INTERVAL)
        except asyncio.CancelledError:
            logging.info("Закінчено виконання завдання.")
            break
        except Exception as exc:
            logging.exception("Помилка під час надсилання: %s", exc)


def is_owner(message: Message) -> bool:
    return message.from_user and message.from_user.id == TELEGRAM_USER_ID


@dp.message(CommandStart())
async def cmd_start(message: Message):
    if not is_owner(message):
        return
    await message.answer("Бот запущено", reply_markup=keyboard)

@dp.message(F.text == "🟢 Почати перевірку")
async def start_checking(message: Message):
    global WAIT_THRESHOLD, periodic_task
    if WAIT_THRESHOLD is None:
        await bot.send_message(TELEGRAM_USER_ID, " Час не задано, введіть його через команду. ")
        return

    if not is_owner(message):
        return

    if periodic_task and not periodic_task.done():
        await message.answer("Перевірка вже запущена")
        return

    periodic_task = asyncio.create_task(send_periodic_data())
    await message.answer(f"Запустив перевірку. Дані перевірятимуться кожні {INTERVAL} секунд.")

@dp.message(F.text == "🔴 Зупинити перевірку")
async def stop_checking(message: Message):
    global periodic_task
    if not is_owner(message):
        return

    if periodic_task and not periodic_task.done():
        periodic_task.cancel()
        periodic_task = None
        await message.answer("Зупинив перевірку. ")
    else:
        await message.answer("Перевірка вже неактивна.")

@dp.message(F.text == "🟡 Час для перевірки")
async def set_threshold(message: Message, state: FSMContext):
    if not is_owner(message):
        return
    await stop_checking(message)
    await message.answer("Введіть поріг у форматі «10 днів 3 години 5 хвилин».")
    await state.set_state(Cfg.waiting_threshold)

@dp.message(Cfg.waiting_threshold)
async def save_threshold(message: Message, state: FSMContext):
    global WAIT_THRESHOLD
    if not is_owner(message):
        return
    try:
        WAIT_THRESHOLD = parse_duration(message.text)
        await message.answer(f"Новий поріг: {WAIT_THRESHOLD} секунд.")
        await state.clear()
        await start_checking(message)
    except ValueError as err:
        await message.answer(f"Помилка: {err}\nСпробуйте ще раз.")


async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
