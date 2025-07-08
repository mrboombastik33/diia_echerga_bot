from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text = 'Почати перевірку')],
        [KeyboardButton(text = 'Зупинити первірку')]
    ],
        resize_keyboard=True
)
