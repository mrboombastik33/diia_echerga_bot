from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text='🟢 Почати перевірку')],
        [KeyboardButton(text='🔴 Зупинити перевірку')],
        [KeyboardButton(text='🟡 Час для перевірки')],
    ],
        resize_keyboard=True
)
