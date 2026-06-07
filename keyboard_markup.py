from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🟢 Почати перевірку")],
        [KeyboardButton(text="🔴 Зупинити перевірку")],
        [KeyboardButton(text="🟡 Вибрати час та КПП для перевірки")],
        [KeyboardButton(text="🔵 Показати дані про КПП")],
        [KeyboardButton(text="⚙️ Мої налаштування КПП")]
    ],
        resize_keyboard=True
)

cancel_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="❌ Скасувати")]
    ],
    resize_keyboard=True
)
