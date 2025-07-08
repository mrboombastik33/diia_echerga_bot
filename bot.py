import asyncio
import os
import logging
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message

from fetch import fetch_data
from additional import calc_time
from keyboard_markup import keyboard

load_dotenv()
API_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
USER_ID = int(os.getenv("TELEGRAM_USER_ID"))

"""Hardcoded info about certain country"""
TARGET_ID = 17
COUNTRY_ID = 167

INTERVAL = 10
WAIT_THRESHOLD = 0

logging.basicConfig(level=logging.INFO)
bot = Bot(API_TOKEN)
dp = Dispatcher()

periodic_task: asyncio.Task | None = None

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
                else:
                    text = (f"Час очікування менше за {WAIT_THRESHOLD // 3600}год")
            else:
                text = "Об'єкт не знайдено!"
            await bot.send_message(USER_ID, text)
            await asyncio.sleep(INTERVAL)
        except asyncio.CancelledError:
            logging.info("Закінчено виконання завдання.")
            break
        except Exception as exc:
            logging.exception("Помилка під час надсилання: %s", exc)


def is_owner(message: Message) -> bool:
    return message.from_user and message.from_user.id == USER_ID


@dp.message(CommandStart())
async def cmd_start(message: Message):
    if not is_owner(message):
        return
    await message.answer("Бот запущено", reply_markup=keyboard)

@dp.message(F.text == "Почати перевірку")
async def start_checking(message: Message):
    global periodic_task
    if not is_owner(message):
        return

    if periodic_task and not periodic_task.done():
        await message.answer("Перевірка вже запущена")
        return

    periodic_task = asyncio.create_task(send_periodic_data())
    await message.answer("Запустив перевірку. Дані приходитимуть кожні "
                         f"{INTERVAL} секунд.")

@dp.message(F.text == "Зупинити перевірку")
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

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
