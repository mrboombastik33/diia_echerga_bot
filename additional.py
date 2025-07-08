import re

UNIT_TO_SECONDS = {
    "сек": 1, "секунд": 1, "секунда": 1, "секунди": 1,
    "хв": 60, "хвилин": 60, "хвилина": 60, "хвилини": 60,
    "год": 3600, "годин": 3600, "година": 3600, "години": 3600,
    "дн": 86400, "день": 86400, "дні": 86400, "днів": 86400,
}


def calc_time(seconds: int) -> str:
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



def parse_duration_ua(text: str) -> int:
    total = 0
    # знаходимо пари «число + слово»
    for number, unit in re.findall(r"(\d+)\s*([А-Яа-яІіЇїЄє]+)", text):
        unit = unit.lower().rstrip(".")          # нормалізуємо регістр і обрізаємо крапку
        if unit not in UNIT_TO_SECONDS:
            raise ValueError(f"Невідома одиниця: {unit}")
        total += int(number) * UNIT_TO_SECONDS[unit]
    return total
