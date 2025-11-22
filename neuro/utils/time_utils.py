"""
Time constants.
"""

import datetime
import time


# Codes.
CODE_DATE = "%Y%m%d"
CODE_DATE_ISO = "%Y-%m-%d"
CODE_DATE_SI = "%d. %m. %Y"
CODE_MOMENT = "%Y%m%d%H%M%S"
CODE_MOMENT_2 = "%Y%m%d_%H%M%S"
CODE_MOMENT_3 = "%Y-%m-%d-%H-%M-%S"
CODE_MOMENT_4 = "%Y-%m-%d_%H-%M-%S"
CODE_MOMENT_SI = "%Y-%m-%d %H:%M:%S"
CODE_MONTH = "%Y_%m"
CODE_PHOTO = "%Y:%m:%d %H:%M:%S"
CODE_TIME = "%H%M%S"
CODE_TIME_SI = "%H:%M:%S"
CODE_YEAR = "%Y"

# Datetime strings.
CURRENT_TIME_SI = datetime.datetime.now().strftime(CODE_TIME_SI)
DATE = datetime.datetime.now().strftime(CODE_DATE)
DATE_ISO = datetime.datetime.now().strftime(CODE_DATE_ISO)
MOMENT = datetime.datetime.now().strftime(CODE_MOMENT)
MOMENT_2 = datetime.datetime.now().strftime(CODE_MOMENT_2)
MOMENT_3 = datetime.datetime.now().strftime(CODE_MOMENT_3)
MOMENT_4 = datetime.datetime.now().strftime(CODE_MOMENT_4)
MOMENT_SI = datetime.datetime.now().strftime(CODE_MOMENT_SI)
MONTH = datetime.datetime.now().strftime(CODE_MONTH)
TODAY_SI = datetime.datetime.now().strftime(CODE_DATE_SI)
UNIX = time.time()
UNIX_INT = int(round(UNIX, 0))
UNIX_ROUND = round(UNIX, 2)
YEAR = datetime.datetime.now().strftime(CODE_YEAR)


def get_time_string(seconds):
    days = int(seconds // (24 * 3600))
    hours = int((seconds % (24 * 3600)) // 3600)
    minutes = int((seconds % 3600) // 60)
    remaining_seconds = int(seconds % 60)

    time_parts = []
    if days > 0:
        time_parts.append(f"{days} days")
    if hours > 0:
        time_parts.append(f"{hours} h")
    if minutes > 0:
        time_parts.append(f"{minutes} min")
    if remaining_seconds > 0 or not time_parts:  # Always show seconds if no other units are printed
        time_parts.append(f"{remaining_seconds} s")

    return " ".join(time_parts)
