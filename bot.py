import asyncio
import os

from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, KeyboardButton
import logging
from dotenv import load_dotenv


from fetch import fetch_data
from additional import calc_time
from keyboard_markup import keyboard

load_dotenv()

API_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
USER_ID = os.getenv('TELEGRAM_USER_ID')

TARGET_ID = 17
COUNTRY_ID = 167
INTERVAL = 165600

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

async def send_periodic_data():
    while True:
        try:
            entry = await fetch_data(country_id=COUNTRY_ID, target_id=TARGET_ID)
            if entry:
                if entry['wait_time'] > 0:
                    text = (f"Знайдено: \n{entry['title']}, \nЧерга {"не" if not entry['is_paused'] else ''} затримується, \n"
                        f"Час очікування: {calc_time(entry['wait_time'])}, \nЧерга авто: {entry['vehicle_in_active_queues_counts']}"
                        )
                else :
                    await bot.send_message(USER_ID, f'Час очікування менше за {INTERVAL}')
            else:
                text = "Об'єкт не знайдено!"
            await bot.send_message(USER_ID, text)
        except Exception as e:
            logging.error(f"Помилка під час надсилання: {e}")
        await asyncio.sleep(10)


@dp.message(CommandStart())
async def start_handler(message: Message):
    await message.reply(f"Бот запущено", reply_markup=keyboard)

async def main():
    asyncio.create_task(send_periodic_data())
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
