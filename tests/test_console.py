import sys
import asyncio
from unittest.mock import patch, MagicMock

import pytest

from kernel.console.console import Console
from kernel.console.colors import Color
from kernel.console.tags import EventTag, ConsoleTag, ResponseTag


class TestConsoleInstanceHelpers:

    @pytest.fixture
    def console(self) -> Console:
        return Console()

    def test_apply_color_wraps_string(self, console) -> None:
        result = console._apply_color("hello", Color.RED)

        assert result.startswith(Color.RED)
        assert result.endswith(Color.RESET)
        assert "hello" in result

    def test_fromat_time_disabled(self, console) -> None:
        assert console._format_time(allow_time=False) == ""

    def test_fromat_time_empty_format(self) -> None:
        console = Console(time_frmt="")

        assert console._format_time(allow_time=True) == ""

    def test_format_time_enabled(self, console) -> None:
        result = console._format_time(allow_time=True)
        assert result.count(":") == 2

    def test_format_tags_empty(self, console) -> None:
        assert console._format_tags([]) == ""

    def test_format_tags_single(self, console) -> None:
        result = console._format_tags([ConsoleTag.NOTICE])

        assert "[NOTICE]" in result

    def test_format_tags_multiple(self, console) -> None:
        result = console._format_tags((ConsoleTag.ERROR, EventTag.JAILED))

        assert "[ERROR]" in result
        assert "[JAILED]" in result

    def test_format_payloads_none_dict(self, console) -> None:
        assert console._format_payloads(None, accept_none=True) == ""

    def test_format_payloads_empty_dict(self, console) -> None:
        assert console._format_payloads({}, accept_none=True) == ""

    def test_format_payloads_basic(self, console) -> None:
        result = console._format_payloads({"k": "v"}, accept_none=True)

        assert "k: v" in result
        assert result.startswith("<")
        assert result.endswith(">")

    def test_format_payloads_reject_none(self, console) -> None:
        result = console._format_payloads({"a": 1, "b": None}, accept_none=False)

        assert "a: 1" in result
        assert "b" not in result

    def test_format_payloads_accept_none(self, console) -> None:
        result = console._format_payloads({"a": None}, accept_none=True)

        assert "a: None" in result

    def test_format_payloads_custom_delimiters(self) -> None:
        console = Console(open_delimiter="[", close_delimiter="]")
        result = console._format_payloads({"x": 9}, accept_none=True)
        assert result.startswith("[") and result.endswith("]")


class TestEmitSyncPath:

    @pytest.fixture
    def console(self) -> Console:
        return Console(time_frmt="")

    def test_emit_prints_without_logger(self, console, capsys) -> None:
        console._emit(
            tags=(ConsoleTag.NOTICE,), message="hello", payloads=None, color=Color.CYAN
        )

        captured = capsys.readouterr()

        assert "hello" in captured.out
        assert "[NOTICE]" in captured.out

    def test_emit_includes_payload(self, console, capsys) -> None:
        console._emit(
            tags=[], message="msg", payloads={"foo": "bar"}, color=Color.WHITE
        )

        captured = capsys.readouterr()

        assert "foo: bar" in captured.out


class TestPublicLogMethods:

    @pytest.fixture
    def console(self) -> Console:
        return Console(time_frmt="")

    def test_notice(self, console, capsys) -> None:
        console.notice("test notice")
        out = capsys.readouterr().out

        assert "[NOTICE]" in out
        assert "test notice" in out

    def test_warning(self, console, capsys) -> None:
        console.warning("test warning")
        out = capsys.readouterr().out

        assert "[WARNING]" in out

    def test_error(self, console, capsys) -> None:
        console.error("test error")
        out = capsys.readouterr().out

        assert "[ERROR]" in out

    def test_critical(self, console, capsys) -> None:
        console.critical("test critical")
        out = capsys.readouterr().out

        assert "[CRITICAL]" in out

    def test_event(self, console, capsys) -> None:
        console.event(ConsoleTag.NOTICE, EventTag.FREED, "API freed")
        out = capsys.readouterr().out

        assert "[NOTICE]" in out
        assert "[FREED]" in out
        assert "API freed" in out

    def test_response_success(self, console, capsys) -> None:
        console.response(1, ResponseTag.SUCCESS, "example.com", status_code=200)
        out = capsys.readouterr().out

        assert "[SUCCESS]" in out
        assert "example.com" in out
        assert "status_code: 200" in out

    def test_response_filters_none_payload(self, console, capsys) -> None:
        console.response(2, ResponseTag.FAILURE, "example.com", retry=None)
        out = capsys.readouterr().out

        assert "retry" not in out

    def test_summary_correct_rate(self, console, capsys) -> None:
        console.summary(success=90, failure=10, total_time=12.5)
        out = capsys.readouterr().out

        assert "90.0%" in out
        assert "Total: 100" in out
        assert "12.5" in out

    def test_summary_zero_total(self, console, capsys) -> None:
        console.summary(success=0, failure=0, total_time=1.0)
        out = capsys.readouterr().out

        assert "0.0%" in out

    def test_notice_with_kwargs(self, console, capsys) -> None:
        console.notice("msg", user="alice", count=5)
        out = capsys.readouterr().out

        assert "user: alice" in out
        assert "count: 5" in out

    def test_input_returns_stripped(self, console) -> None:
        with patch("builtins.input", return_value="  hello  "):
            result = console.input("prompt> ", Color.GREEN)

        assert result == "hello"


@pytest.mark.asyncio
class TestAsyncLogger:

    async def test_start_creates_task(self) -> None:
        console = Console(time_frmt="")
        console.start_logger()

        assert console._logger_task is not None
        assert not console._logger_task.done()

        await console.stop_logger()

    async def test_stop_sets_task_done(self) -> None:
        console = Console(time_frmt="")
        console.start_logger()

        await console.stop_logger()
        assert console._logger_task is None

    async def test_start_twice_is_no_op(self) -> None:
        console = Console(time_frmt="")
        console.start_logger()
        task1 = console._logger_task
        console.start_logger()

        assert console._logger_task
        await console.stop_logger()

    async def test_stop_without_start_is_safe(self) -> None:
        console = Console(time_frmt="")
        await console.stop_logger()

    async def test_message_flushed_before_stop(slef, capsys) -> None:
        console = Console(time_frmt="")
        console.start_logger()
        console.notice("async-notice-1")
        console.notice("async-notice-2")

        await console.stop_logger()

        out = capsys.readouterr()

        assert "async-notice-1"
        assert "async-notice-2"

    async def test_enqueues_when_logger_running(self, capsys) -> None:
        console = Console(time_frmt="")
        console.start_logger()
        console.warning("queued warning")

        await console.stop_logger()

        out = capsys.readouterr()

        assert "queued warning"

    async def test_dropped_logs_counter(self) -> None:
        console = Console(time_frmt="")
        console.start_logger()

        await console.stop_logger()

        console2 = Console(time_frmt="")
        console2.start_logger()

        for _ in range(1000):
            try:
                console2._logger_queue.put_nowait("x")

            except asyncio.QueueFull:
                break

        initial = console2.dropped_logs
        console2._emit([], "overflow", None, Color.WHITE)

        await console2.stop_logger()

        assert console2.dropped_logs >= initial

    async def test_dropped_logs_initial_zero(self) -> None:
        console = Console(time_frmt="")

        assert console.dropped_logs == 0


class TestAnsiSupport:

    def test_non_windows_is_no_op(self) -> None:
        with patch.object(sys, "platform", "linux"):
            Console._enable_ansi_support()

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
    def test_windows_sets_mode(self) -> None:
        Console._enable_ansi_support()

    def test_windows_handles_exception_gracefully(self) -> None:
        with patch.object(sys, "platform", "win32"):
            import ctypes

            mock_kernel = MagicMock()
            mock_kernel.getStdHandle.return_value = -1

            with patch("ctypes.windll", create=True) as mock_windll:
                mock_windll.kernel32 = mock_kernel
                Console._enable_ansi_support()
