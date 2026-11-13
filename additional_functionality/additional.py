import re

UNIT_TO_SECONDS = {
    "сек": 1, "секунд": 1, "секунда": 1, "секунди": 1,
    "хв": 60, "хвилин": 60, "хвилина": 60, "хвилини": 60,
    "год": 3600, "годин": 3600, "година": 3600, "години": 3600,
    "дн": 86400, "день": 86400, "дні": 86400, "днів": 86400,
}


def calc_time(seconds: int) -> str:
    if seconds == 0:
        return "0 хвилин"

    time_periods = [60, 3600, 86400]
    result = ''
    time = len(time_periods) - 1

    while time >= 0:
        if time > 0:
            res_time = seconds // time_periods[time]
            seconds = seconds % time_periods[time]
        else:
            res_time = seconds // 60
            seconds = seconds % 60

        if res_time > 0:
            match time:
                case 2:
                    result += f'{res_time} днів '
                case 1:
                    result += f'{res_time} годин '
                case 0:
                    result += f'{res_time} хвилин '
        time -= 1

    return result.strip()


def parse_duration(text: str) -> int:
    parts = text.replace(",", " ").split()

    if len(parts) != 3:
        raise ValueError("Очікую ТРИ числа: <днів> <годин> <хвилин>")

    days, hours, minutes = map(int, parts)

    # Валідація
    if hours < 0 or hours >= 24:
        raise ValueError("Години мають бути в діапазоні 0‑23")
    if minutes < 0 or minutes >= 60:
        raise ValueError("Хвилини мають бути в діапазоні 0‑59")
    if days < 0:
        raise ValueError("Дні не можуть бути від’ємні")

    return days * 86_400 + hours * 3_600 + minutes * 60



_TIMING_UNITS = {"дн": 86_400, "год": 3_600, "хв": 60}
_TIMING_RE = re.compile(r"(\d+)\s*(дн|год|хв)")


def parse_timing_text(text) -> int | None:
    """"7 дн 2 год" / "2 год 24 хв" / "18 хв" / "0 хв" -> секунди; None, якщо формат невідомий."""
    if not isinstance(text, str):
        return None
    parts = _TIMING_RE.findall(text)
    if not parts:
        return None
    return sum(int(n) * _TIMING_UNITS[unit] for n, unit in parts)


def get_wait_seconds(entry: dict) -> int | None:
    """Час очікування КПП в секундах.

    API v5 більше не віддає числове `wait_time`, лише текст `timing.header.text`.
    Числове поле, якщо воно колись повернеться, має пріоритет.
    """
    wait_time = entry.get("wait_time")
    if isinstance(wait_time, (int, float)) and not isinstance(wait_time, bool):
        return int(wait_time)
    timing = entry.get("timing")
    header = timing.get("header") if isinstance(timing, dict) else None
    text = header.get("text") if isinstance(header, dict) else None
    return parse_timing_text(text)
