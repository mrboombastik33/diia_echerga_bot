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