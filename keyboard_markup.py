from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text = 'Почати перевірку')],
        [KeyboardButton(text = 'Зупинити перевірку')]
    ],
        resize_keyboard=True
)
