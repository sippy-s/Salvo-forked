import sys
import asyncio
import ctypes as ct
from typing import Any
from datetime import datetime
from collections.abc import Sequence

from kernel.console.colors import Color
from kernel.console.tags import Tag, ConsoleTag, EventTag, SystemTag, ResponseTag


class Console:
    """
    Async-aware colored console logger with structured output.

    Designed for CLI tools, async applications, and high-throughput logging
      where non-blocking output is preferred but graceful fallback to sync print
      is required.
    """

    @staticmethod
    def _enable_ansi_support() -> None:
        """
        Enable ANSI escape code processing on Windows terminals.

        Uses the Windows Console API to turn on virtual terminal
          processing. On non-Windows systems this is a no-op.
        """
        if sys.platform != "win32":
            return

        STD_OUTPUT_HANDLE = -11
        ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004

        try:
            kernel32 = ct.windll.kernel32
            handle = kernel32.getStdHandle(STD_OUTPUT_HANDLE)

            if handle == -1:
                return

            mode = ct.c_ulong()

            if not kernel32.GetConsoleMode(handle, ct.byref(mode)):
                return

            mode.value |= ENABLE_VIRTUAL_TERMINAL_PROCESSING
            kernel32.SetConsoleMode(handle, mode)

        except Exception:
            return

    @staticmethod
    def tab(n: int = 1) -> str:
        """Return a string with n * 4 space characters."""
        return " " * 4 * n

    @staticmethod
    def clear_screen() -> None:
        """Clear the terminal viewport using ANSI escape codes."""
        print("\033[H\033[J", end="")

    @staticmethod
    def shutdown(exit_code: int = 0) -> None:
        """
        Terminate the interpreter immediately with 'exit_code'.

        Args:
            exit_code | int: The exit status (default: 0).
        """
        sys.exit(exit_code)

    def __init__(
        self,
        time_frmt: str = "%H:%M:%S",
        open_delimiter: str = "<",
        close_delimiter: str = ">",
    ) -> None:
        """
        Args:
            time_frmt | str: strftime format for the optional
              time-stamp prefix (default: '%H:%M:%S').

            open_delimiter | str: Opening bracket for the
              payload area (default: '<').

            close_delimiter | str: Closing bracket for the
              payload area (default: '>').
        """
        self._enable_ansi_support()

        self._time_frmt = time_frmt
        self._open_delimiter = open_delimiter
        self._close_delimiter = close_delimiter

        self._logger_queue: asyncio.Queue[str | None] = asyncio.Queue(maxsize=1000)
        self._logger_task: asyncio.Task[None] | None = None

        self._dropped_logs = 0

    @property
    def dropped_logs(self) -> int:
        return self._dropped_logs

    def _apply_color(self, string: str, color: Color) -> str:
        """
        Wrap **string** with the given ANSI color and a reset code.

        Args:
            string | str: The text to color.

            color | Color: The color to apply.

        Returns:
            str: the color-wrapped string.
        """
        return f"{color}{string}{Color.RESET}"

    def _format_time(self, allow_time: bool) -> str:
        """
        Return the current timestamp formatted using the configured time format.

        If timestamping is disabled or format string is empty, returns an empty string.

        Args:
            allow_time | bool: Whether to include timestamp in output.

        Returns:
            str: Formatted timestamp or empty string.
        """
        if not allow_time or not self._time_frmt:
            return ""

        return datetime.now().strftime(self._time_frmt)

    def _format_payloads(
        self, payloads: dict[str, Any] | None, accept_none: bool
    ) -> str:
        """
        Convert a payload dictionary into a formatted string.

        Args:
            payloads | dict[str, Any]|None: Key-value pairs to display.

            accept_none | bool: If 'False',
              entries whose value is 'None' are omitted

        Returns:
            str: A string such as ' <key1: value1, key2: value2>'
              or an empty string when no payloads remain.
        """
        if not payloads:
            return ""

        if not accept_none:
            payloads = {k: v for k, v in payloads.items() if v is not None}

        if not payloads:
            return ""

        formatted = ", ".join(f"{k}: {v}" for k, v in payloads.items())
        return f"{self._open_delimiter}{formatted}{self._close_delimiter}"

    def _format_tags(self, tags: Sequence[Tag]) -> str:
        """
        Format a sequence of tags into a single bracketed string.

        Each tag is rendered using its string representation and wrapped
          in square brackets.

        Example:
            (NOTICE, JAILED) -> "[NOTICE] [JAILED]"

        Args:
            tags | Sequence[Tag]: Collection of console/system/event tags.

        Returns:
            str: Formatted tag string or an empty string if not tags exists.
        """
        if not tags:
            return ""

        return " ".join(f"[{t}]" for t in tags)

    async def _logger_drain(self) -> None:
        """
        Continuously drain the internal logger queue and print each entry.

        This coroutine runs as a background task. It pulls callables from
          '_logger_queue' one by one and invokes them. A 'None' sentinel is used
          to signal graceful shutdown.
        """

        while True:
            log = await self._logger_queue.get()

            if log is None:
                self._logger_queue.task_done()
                break

            print(log)
            self._logger_queue.task_done()

    def _emit(
        self,
        tags: Sequence[Tag],
        message: str,
        payloads: dict[str, Any] | None,
        color: Color,
        allow_time: bool = True,
        accept_none: bool = True,
    ) -> None:
        """
        Build a formatted log entry and output it.

        When the background log-drain task is active, the message is enqueued
          for asynchronous I/O to avoid blocking the caller. If the logger has
          not been started (or has already been stopped), the message is printed
          directly so that early/late output is never lost.

        Args:
            tags | Sequence[Tag]: The log tags.

            message | str: The main message body.

            payloads | dict[str, Any]|None: Payload data to
              display alongside the message.

            color | Color: ANSI color for the line.

            allow_time | bool: Whether to prepend a
              time-stamp (default: 'True').

            accept_none | bool: Whether to display
              payload entries with a 'None' value (default: 'True').
        """
        log_sections = (
            self._format_time(allow_time),
            self._format_tags(tags),
            message,
            self._format_payloads(payloads, accept_none),
        )

        composed_log = " ".join(filter(None, log_sections))
        colored_log = self._apply_color(composed_log, color)

        if self._logger_task is not None and not self._logger_task.done():
            try:
                self._logger_queue.put_nowait(colored_log)

            except asyncio.QueueFull:
                self._dropped_logs += 1

        else:
            print(colored_log)

    def start_logger(self) -> None:
        """
        Launch the background log-drain task.

        Creates an 'asyncio.Task' that runs '_logger_drain'. Must be called
          from within a running event loop. If the logger is already running,
          the call is a no-op.
        """
        if self._logger_task is None:
            self._logger_task = asyncio.create_task(self._logger_drain())

    async def stop_logger(self) -> None:
        """
        Gracefully shutdown the log-drain task.

        Sends a 'None' sentinel through the queue, waits for the background
          task to finish, and resets '_logger_task' to 'None'. Safe to call even
          if the logger was never started.
        """
        if self._logger_task is not None:
            await self._logger_queue.put(None)
            await self._logger_task

            self._logger_task = None

    def input(
        self, prompt: str, color: Color = Color.LIGHT_CYAN, allow_time: bool = True
    ) -> str:
        """
        Display a colored prompt and wait for user input.

        Args:
            prompt | str: The text shown to the user.

            color | Color: ANSI color for the prompt.

            allow_time | bool: Whether to prepend a
              time-stamp (default: 'True')

        Returns:
            str: The stripped user input.
        """
        time = self._format_time(allow_time)
        colored_prompt = self._apply_color(f"{time} {prompt}", color)

        return input(colored_prompt).strip()

    def event(
        self, severity: ConsoleTag, event: EventTag, message: str, **kwargs
    ) -> None:
        """
        Emit a structured event log with both severity and event tags.

        Events are used to represent lifecycle or state changes in the system.

        Example:
            00:00:00 [Notice] [FREED] API has been freed.

        Args:
            severity | ConsoleTag: Log severity level (e.g. NOTICE, WARNING).

            event | EventTag: Specific event type (e.g. JAILED, FREED).

            message | str: Main log message.

            kwargs: Optional payload data attached to the event.
        """
        self._emit(
            tags=(
                severity,
                event,
            ),
            message=message,
            payloads=kwargs,
            color=event.color,
        )

    def notice(self, message: str, **kwargs) -> None:
        """
        Emit a NOTICE level log.

        Used for general informational messages that are not warnings or errors.

        Args:
            message | str: Log message content.
            kwargs: Optional payload data.
        """
        tag = ConsoleTag.NOTICE

        self._emit(tags=(tag,), message=message, payloads=kwargs, color=tag.color)

    def warning(self, message: str, **kwargs) -> None:
        """
        Emit a WARNING level log.

        Used for potential issues that do not stop execution but may require attention.

        Args:
            message | str: Log message content.
            kwargs: Optional payload data.
        """
        tag = ConsoleTag.WARNING

        self._emit(tags=(tag,), message=message, payloads=kwargs, color=tag.color)

    def critical(self, message: str, **kwargs) -> None:
        """
        Emit a CRITICAL level log.

        Used for severe errors that indicate system instability or failure conditions.

        Args:
            message | str: Log message content.
            kwargs: Optional payload data.
        """
        tag = ConsoleTag.CRITICAL

        self._emit(tags=(tag,), message=message, payloads=kwargs, color=tag.color)

    def error(self, message: str, **kwargs) -> None:
        """
        Emit a ERROR level log.

        Used when an operation fails but the system can continue running.

        Args:
            message | str: Log message content.
            kwargs: Optional payload data.
        """
        tag = ConsoleTag.ERROR

        self._emit(tags=(tag,), message=message, payloads=kwargs, color=tag.color)

    def response(self, _id: int, status: ResponseTag, source: str, **kwargs) -> None:
        """
        Emit a structured response log for APIs requests.

        This is typically used to log request/response cycles with status tracking.

        Example:
            00:00:00 [01] [SUCCESS] example.com <status_code: 200>
            00:00:00 [237] [FAILURE] example.com <status_code: 429>

        Args:
            _id | int: Request or correlation identifier.

            status | ResponseTag: Result status (SUCCESS, ...).

            source | str: API source name.

            kwargs: Optional payload data (excluded if None values are disabled).
        """
        self._emit(
            tags=(
                f"{_id:02d}",
                status,
            ),
            message=source,
            payloads=kwargs,
            color=status.color,
            accept_none=False,
        )

    def summary(self, success: int, failure: int, total_time: float) -> None:
        """
        Emit a final aggregated summary of system execution.

        Includes success/failure counts, success rate, runtime, and dropped logs.

        Example:
            Time: 12.5s | Total: 100 | Success: 90 | Failure: 10 | Success Rate: 90.0% <dropped_logs: 0>
        """
        total = success + failure
        rate = (success / total) * 100 if total != 0 else 0.0

        message = (
            f"Time: {total_time:.1f}s | "
            f"Total: {total} | Success: {success} | "
            f"Failure: {failure} | Success Rate: {rate:.1f}%"
        )
        tag = SystemTag.SUMMARY

        self._emit(
            tags=(tag,),
            message=message,
            payloads={"dropped_logs": self._dropped_logs},
            color=tag.color,
        )
