import asyncio
import os
import logging
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, StateFilter
from aiogram.fsm.state import default_state
from aiogram.types import Message
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext

from additional_functionality.fetch import fetch_data
from additional_functionality.additional import calc_time, parse_duration
from keyboard_markup import keyboard, cancel_keyboard

from db.db_interaction import (init_db, get_user_thresholds_database, set_user_threshold_database,
                               add_user_if_not_exists_simple, show_user_data,
                               get_status_message_id, set_status_message_id)
from additional_functionality.slow_parsing import find_data
from additional_functionality.task_manager import TaskManager


load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")


INTERVAL = 30

logging.basicConfig(level=logging.INFO)
bot = Bot(TELEGRAM_BOT_TOKEN)
dp = Dispatcher()

task_manager = TaskManager()

class Cfg(StatesGroup):
    waiting_kpp = State()
    waiting_threshold = State()


async def send_long_message(user_id: int, text: str):
    MAX_LEN = 4000
    for i in range(0, len(text), MAX_LEN):
        await bot.send_message(user_id, text[i:i+MAX_LEN])


async def update_status_message(user_id: int, text: str):
    message_id = await get_status_message_id(user_id)
    if message_id:
        try:
            await bot.edit_message_text(text, chat_id=user_id, message_id=message_id)
            return
        except TelegramBadRequest as e:
            if "message is not modified" in str(e).lower():
                return
            pass
    msg = await bot.send_message(user_id, text)
    await set_status_message_id(user_id, msg.message_id)
    try:
        await bot.pin_chat_message(user_id, msg.message_id)
    except TelegramBadRequest:
        pass


async def send_periodic_data(user_id: int, interval: int):
    while True:
        try:
            thresholds = await get_user_thresholds_database(user_id)

            logging.info("Перевірка запущена для юзера %s", user_id)

            if not thresholds:
                await asyncio.sleep(interval)
                continue

            for threshold_data in thresholds:
                kpp_id = threshold_data["kpp_id"]
                country_id = threshold_data["country_id"]
                threshold = threshold_data["threshold"]

                await asyncio.sleep(1)

                entry = await fetch_data(country_id=country_id, target_id=kpp_id)

                if not entry:
                    continue

                wait_time = entry.get("wait_time")
                if wait_time is None:
                    continue

                if threshold is not None and wait_time > threshold:
                    title = entry.get("title", "Невідомо")
                    is_paused = entry.get("is_paused", False)
                    vehicle_count = entry.get("vehicle_in_active_queues_counts", "н/д")
                    text = (
                        "Знайдено:\n"
                        f"{title}\n"
                        f"Черга {'не ' if not is_paused else ''}затримується\n"
                        f"Час очікування: {calc_time(wait_time)}\n"
                        f"Черга авто: {vehicle_count}"
                    )
                    for i in range(5):
                        await send_long_message(user_id, text)
                        await asyncio.sleep(5)


            await asyncio.sleep(interval)

        except asyncio.CancelledError:
            logging.info(f"Таска для юзера {user_id} відмінена.")
            break
        except Exception as exc:
            logging.exception("Помилка під час надсилання: %s", exc)
            await asyncio.sleep(interval)  # не падаємо, а чекаємо



@dp.message(CommandStart(), StateFilter(default_state))
async def cmd_start(message: Message):
    user_id = message.from_user.id
    await add_user_if_not_exists_simple(user_id)
    await update_status_message(user_id, "🔴 Моніторинг зупинено")
    await message.answer("Бот запущено. Використовуйте кнопки для керування роботою бота", reply_markup=keyboard)


@dp.message(F.text == "🟢 Почати перевірку", StateFilter(default_state))
async def start_checking(message: Message):
    user_id = message.from_user.id
    if task_manager.is_active(user_id):
        await message.answer("Перевірка вже запущена")
        return

    thresholds = await get_user_thresholds_database(user_id)
    if not thresholds:
        await message.answer("⚠️ У вас ще немає збережених КПП.")
        return

    # Запускаємо одну задачу, яка перевіряє всі КПП цього юзера
    task_manager.start_task(
        user_id,
        send_periodic_data(user_id, INTERVAL)
    )
    await update_status_message(user_id, "🟢 Моніторинг активний")
    await message.answer(f"✅ Запустив перевірку. Дані приходитимуть кожні {INTERVAL} секунд.")



@dp.message(F.text == "🔴 Зупинити перевірку", StateFilter(default_state))
async def stop_checking(message: Message):
    user_id = message.from_user.id
    if task_manager.is_active(user_id):
        task_manager.stop_tasks(user_id)
        await update_status_message(user_id, "🔴 Моніторинг зупинено")
        await message.answer("Перевірку зупинено.")
    else:
        await message.answer("ℹ️ Перевірка вже неактивна.")


# Вибір КПП
@dp.message(F.text == "🟡 Вибрати час та КПП для перевірки", StateFilter(default_state))
async def set_kpp(message: Message, state: FSMContext):
    await message.answer("Введіть назву пропускного пункту", reply_markup=cancel_keyboard)
    await state.set_state(Cfg.waiting_kpp)


@dp.message(Cfg.waiting_kpp, F.text == "❌ Скасувати")
async def cancel_kpp_input(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Скасовано.", reply_markup=keyboard)


@dp.message(Cfg.waiting_kpp, F.text)
async def save_kpp(message: Message, state: FSMContext):
    kpp_name = message.text
    kpp_data = await find_data(kpp_name)

    if not kpp_data:
        await message.answer("КПП не знайдено. Спробуйте ще раз.")
        return

    await state.update_data(kpp_id=kpp_data[0], country_id = kpp_data[1])
    await message.answer("КПП збережено. Тепер введіть час перевірки (наприклад: 10 7 5 - 10 днів 7 годин 5 хвилин)", reply_markup=cancel_keyboard)
    await state.set_state(Cfg.waiting_threshold)


# Встановлюємо час
@dp.message(Cfg.waiting_threshold, F.text == "❌ Скасувати")
async def cancel_threshold_input(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Скасовано.", reply_markup=keyboard)


@dp.message(Cfg.waiting_threshold, F.text)
async def save_threshold(message: Message, state: FSMContext):
    user_id = message.from_user.id
    await add_user_if_not_exists_simple(user_id)

    data = await state.get_data()
    if "kpp_id" not in data or "country_id" not in data:
        await message.answer("⚠️ Сесія закінчилася. Почніть спочатку: 🟡 Вибрати час та КПП")
        await state.clear()
        return

    kpp_id = data["kpp_id"]
    country_id = data["country_id"]
    try:
        wait_threshold = parse_duration(message.text)
    except ValueError as e:
        await message.answer(f"❌ Неправильний формат: {e}")
        return

    await set_user_threshold_database(user_id, wait_threshold, kpp_id, country_id)

    was_active = task_manager.is_active(user_id)
    if was_active:
        task_manager.stop_tasks(user_id)
        task_manager.start_task(
            user_id,
            send_periodic_data(user_id, INTERVAL)
        )
        await update_status_message(user_id, "🟢 Моніторинг активний")

    await state.clear()
    await message.answer("✅ Поріг збережено.")


@dp.message(F.text == "🔵 Показати дані про КПП", StateFilter(default_state))
async def show_data(message : Message):
    user_id = message.from_user.id
    kpps = await show_user_data(user_id)
    if not kpps:
        await message.answer("⚠️ У вас ще немає збережених КПП.")
        return
    text = "Ваші сессії:\n"
    for data in kpps:
        kpp = await fetch_data(data["country_id"], data["id"])
        if not kpp:
            continue
        title = kpp.get("title", "Невідомо")
        wait_time = kpp.get("wait_time", 0)
        text += f"\nНазва: {title} \nЧас очікування: {calc_time(wait_time)}\n"
    await send_long_message(user_id, text)


@dp.message(F.text == "⚙️ Мої налаштування КПП", StateFilter(default_state))
async def show_kpp_settings(message: Message):
    user_id = message.from_user.id
    kpps = await show_user_data(user_id)
    if not kpps:
        await message.answer("⚠️ У вас ще немає збережених КПП.")
        return

    text = "Ваші налаштування:\n"
    for data in kpps:
        kpp = await fetch_data(data["country_id"], data["id"])
        if not kpp:
            continue
        title = kpp.get("title", "Невідомо")
        text += f"\nНазва: {title}\nПоріг очікування: {calc_time(data['threshold'])}\n"
    await send_long_message(user_id, text)


async def main():
    await init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
