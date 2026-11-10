from datetime import datetime, timedelta
from urllib.parse import urlparse
import os
import platform
import subprocess
import shutil
import psutil


def get_current_time() -> str:
    """Return the computer's current local time."""
    now = datetime.now().astimezone()
    return now.strftime("%I:%M %p on %A, %d %B %Y")


def get_current_date() -> str:
    """Return today's local date."""
    today = datetime.now().astimezone().date()
    return today.strftime("%A, %d %B %Y")


def get_tomorrow_date() -> str:
    """Return tomorrow's local date."""
    tomorrow = datetime.now().astimezone().date() + timedelta(days=1)
    return tomorrow.strftime("%A, %d %B %Y")


def get_yesterday_date() -> str:
    """Return yesterday's local date."""
    yesterday = datetime.now().astimezone().date() - timedelta(days=1)
    return yesterday.strftime("%A, %d %B %Y")


def get_system_info() -> str:
    """Return basic Windows and hardware information."""
    memory = psutil.virtual_memory()

    return (
        f"Operating system: {platform.system()} {platform.release()}\n"
        f"Processor: {platform.processor() or 'Unknown'}\n"
        f"RAM total: {memory.total / (1024 ** 3):.1f} GB\n"
        f"RAM available: {memory.available / (1024 ** 3):.1f} GB\n"
        f"Current time: {get_current_time()}"
    )


def get_battery_status() -> str:
    """Return battery status when a battery is available."""
    battery = psutil.sensors_battery()

    if battery is None:
        return "Battery information is unavailable on this computer."

    charging = "charging" if battery.power_plugged else "not charging"
    return f"Battery: {battery.percent:.0f}% and {charging}."


def open_notepad() -> str:
    """Open Windows Notepad."""
    if platform.system() != "Windows":
        return "Opening Notepad is only supported on Windows."

    try:
        subprocess.Popen(
            ["notepad.exe"],
            shell=False,
            creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
        )
        return "Notepad launch requested successfully."
    except OSError as exc:
        return f"Could not open Notepad: {exc}"


def open_calculator() -> str:
    """Open Windows Calculator."""
    if platform.system() != "Windows":
        return "Opening Calculator is only supported on Windows."

    try:
        subprocess.Popen(
            ["calc.exe"],
            shell=False,
            creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
        )
        return "Calculator launch requested successfully."
    except OSError as exc:
        return f"Could not open Calculator: {exc}"


def _find_brave() -> str | None:
    """Find the Brave browser executable on Windows."""
    candidates = [
        shutil.which("brave.exe"),
        shutil.which("brave"),
        os.path.expandvars(
            r"%PROGRAMFILES%\BraveSoftware\Brave-Browser\Application\brave.exe"
        ),
        os.path.expandvars(
            r"%PROGRAMFILES(X86)%\BraveSoftware\Brave-Browser\Application\brave.exe"
        ),
        os.path.expandvars(
            r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\Application\brave.exe"
        ),
    ]

    for candidate in candidates:
        if candidate and os.path.isfile(candidate):
            return candidate

    return None


def open_website(url: str, browser: str = "default") -> str:
    """
    Open a website in Brave, Chrome, Edge, Firefox, or the default browser.
    Accept only HTTP and HTTPS website URLs.
    """
    if platform.system() != "Windows":
        return "Website launching through this tool is currently supported on Windows."

    if not isinstance(url, str):
        return "Invalid website address."

    url = url.strip()

    if not url:
        return "Please provide a website address."

    # Allow natural requests such as "youtube.com" while rejecting
    # non-web schemes such as file:, javascript:, and data:.
    if "://" not in url:
        url = "https://" + url

    parsed = urlparse(url)

    if (
        parsed.scheme.lower() not in ("http", "https")
        or not parsed.hostname
        or any(char.isspace() for char in url)
    ):
        return "Invalid website address. Please provide a valid HTTP or HTTPS URL."

    browser = (browser or "default").strip().lower()

    try:
        if browser == "brave":
            executable = _find_brave()

            if not executable:
                return (
                    "Brave was not found. Please check whether it is installed "
                    "in a standard Windows installation folder."
                )

            subprocess.Popen([executable, url], shell=False)
            return f"Opened {parsed.hostname} in Brave."

        if browser in ("default", "chrome", "edge", "firefox"):
            if browser == "default":
                os.startfile(url)
                return f"Opened {parsed.hostname} in your default browser."

            executable_names = {
                "chrome": ["chrome.exe", "chrome"],
                "edge": ["msedge.exe", "msedge"],
                "firefox": ["firefox.exe", "firefox"],
            }

            executable = next(
                (
                    shutil.which(name)
                    for name in executable_names[browser]
                    if shutil.which(name)
                ),
                None,
            )

            if not executable:
                return f"{browser.title()} was not found on this computer."

            subprocess.Popen([executable, url], shell=False)
            return f"Opened {parsed.hostname} in {browser.title()}."

        return (
            "Unsupported browser. Choose Brave, Chrome, Edge, Firefox, "
            "or default."
        )

    except OSError as exc:
        return f"Could not open the website: {exc}"


def open_youtube_in_brave() -> str:
    """Immediately open YouTube in the Brave browser."""
    return open_website("https://www.youtube.com", "brave")


def open_youtube() -> str:
    """Open YouTube in the computer's default web browser."""
    return open_website("https://www.youtube.com", "default")


# Tool registry: tool name -> callable function.
TOOLS = {
    "get_current_time": get_current_time,
    "get_current_date": get_current_date,
    "get_tomorrow_date": get_tomorrow_date,
    "get_yesterday_date": get_yesterday_date,
    "get_system_info": get_system_info,
    "get_battery_status": get_battery_status,
    "open_notepad": open_notepad,
    "open_calculator": open_calculator,
    "open_youtube_in_brave": open_youtube_in_brave,
    "open_youtube": open_youtube,
}


def execute_tool(name: str, arguments: dict | None = None) -> str:
    """
    Execute a registered tool by name.

    Unknown tools are rejected. Arbitrary Python code or shell commands
    cannot be executed through this interface.
    """
    tool = TOOLS.get(name)

    if tool is None:
        return f"Unknown tool: {name}"

    arguments = arguments or {}

    if not isinstance(arguments, dict):
        return "Tool arguments must be an object."

    try:
        if name == "open_website":
            return open_website(
                url=arguments.get("url", ""),
                browser=arguments.get("browser", "default"),
            )

        if arguments:
            return f"Tool '{name}' does not accept arguments."

        return str(tool())

    except Exception as exc:
        return f"Tool '{name}' failed: {type(exc).__name__}: {exc}"


def get_tool_descriptions() -> str:
    """Return tool names and descriptions for the language model."""
    descriptions = []

    for name, function in TOOLS.items():
        descriptions.append(f"- {name}: {function.__doc__ or 'No description'}")

    descriptions.append(
        "- open_website: Open a website using a validated HTTP or HTTPS URL. "
        "Arguments: url (required), browser (optional: brave, chrome, edge, "
        "firefox, default)."
    )

    return "\n".join(descriptions)