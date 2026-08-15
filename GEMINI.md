# diia_echerga_bot

Telegram bot for monitoring queue times at border checkpoints (єЧерга / eCherga).

## Stack
- **Framework**: `aiogram` 3.x
- **Database**: SQLite (`aiosqlite`)
- **HTTP Client**: `aiohttp` / `requests` / `playwright`
- **Environment**: `python-dotenv`

## Project Structure
- `bot.py` - Main bot entry point, handlers, and background polling.
- `keyboard_markup.py` - Reply and inline keyboard markups.
- `db/`
  - `db_setup.py` - Database schema initialization (`users`, `user_thresholds`).
  - `db_interaction.py` - Database operations for thresholds and user state.
- `additional_functionality/`
  - `fetch.py` - API interaction for checkpoint data.
  - `slow_parsing.py` - Backup/web parsing using Playwright.
  - `task_manager.py` - Background task handling for user checks.
  - `additional.py` - Helper utilities for time and text formatting.

## Setup & Running
1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Configure `.env`:
   ```env
   TELEGRAM_BOT_TOKEN=your_telegram_bot_token
   ```
3. Run the bot:
   ```bash
   python bot.py
   ```
