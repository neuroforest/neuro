"""
Time constants.
"""

import datetime
import time


# Codes.
CODE_DATE = "%Y%m%d"
CODE_DATE_SI = "%d. %m. %Y"
CODE_MOMENT = "%Y%m%d%H%M%S"
CODE_MOMENT_2 = "%Y%m%d_%H%M%S"
CODE_MOMENT_SI = "%d. %m. %Y %H:%M:%S"
CODE_MONTH = "%Y_%m"
CODE_PHOTO = "%Y:%m:%d %H:%M:%S"
CODE_TIME = "%H%M%S"
CODE_TIME_SI = "%H:%M:%S"
CODE_YEAR = "%Y"

# Datetime strings.
CURRENT_TIME_SI = datetime.datetime.now().strftime(CODE_TIME_SI)
DATE = datetime.datetime.now().strftime(CODE_DATE)
MOMENT = datetime.datetime.now().strftime(CODE_MOMENT)
MOMENT_2 = datetime.datetime.now().strftime(CODE_MOMENT_2)
MOMENT_SI = datetime.datetime.now().strftime(CODE_MOMENT_SI)
MONTH = datetime.datetime.now().strftime(CODE_MONTH)
TODAY_SI = datetime.datetime.now().strftime(CODE_DATE_SI)
UNIX = time.time()
UNIX_INT = int(round(UNIX, 0))
UNIX_ROUND = round(UNIX, 2)
YEAR = datetime.datetime.now().strftime(CODE_YEAR)
