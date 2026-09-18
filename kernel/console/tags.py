from enum import Enum

from kernel.console.colors import Color


class Tag(Enum):
    """
    Base enum for console-facing tags.

    Associates a human-readable label with a display color.
    """

    def __init__(self, label: str, color: Color) -> None:
        self._label = label
        self._color = color

    def __str__(self) -> str:
        return self._label

    @property
    def label(self) -> str:
        return self._label

    @property
    def color(self) -> Color:
        return self._color


class SystemTag(Tag):
    """System-level aggregated reports."""

    SUMMARY = ("SUMMARY", Color.CYAN)


class ConsoleTag(Tag):
    """Log severity tags for console output."""

    ERROR = ("ERROR", Color.RED)
    NOTICE = ("NOTICE", Color.CYAN)
    WARNING = ("WARNING", Color.YELLOW)
    CRITICAL = ("CRITICAL", Color.MAGENTA)


class EventTag(Tag):
    """Application lifecycle and status-change events."""

    PURGED = ("PURGED", Color.PINK)
    JAILED = ("JAILED", Color.ORANGE)
    FREED = ("FREED", Color.LIGHT_BLUE)

    FALLBACK = ("FALLBACK", Color.BLUE)


class ResponseTag(Tag):
    """Possible outcomes of an API request."""

    SUCCESS = ("SUCCESS", Color.GREEN)
    FAILURE = ("FAILURE", Color.RED)
    ZOMBIE = ("ZOMBIE", Color.SWAMP)
