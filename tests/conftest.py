import os
import sys

# bot.py створює Bot(...) на рівні модуля — потрібен токен правильного формату
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "123456:TEST-TOKEN")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
