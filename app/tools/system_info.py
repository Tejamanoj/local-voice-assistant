
from datetime import datetime, timedelta
import platform


def get_current_time() -> str:
    """Return the current local time and date."""
    now = datetime.now().astimezone()
    return now.strftime("It is %I:%M %p on %A, %d %B %Y.")


def get_current_date() -> str:
    """Return today's date."""
    today = datetime.now().astimezone().date()
    return today.strftime("Today is %A, %d %B %Y.")


def get_yesterday_date() -> str:
    """Return yesterday's date."""
    yesterday = datetime.now().astimezone().date() - timedelta(days=1)
    return yesterday.strftime("Yesterday was %A, %d %B %Y.")


def get_tomorrow_date() -> str:
    """Return tomorrow's date."""
    tomorrow = datetime.now().astimezone().date() + timedelta(days=1)
    return tomorrow.strftime("Tomorrow is %A, %d %B %Y.")


def get_system_info() -> str:
    """Return basic computer information."""
    return (
        f"Operating system: {platform.system()} "
        f"{platform.release()}\n"
        f"{get_current_time()}\n"
        f"{get_current_date()}"
    )