import argparse
from pathlib import Path

import pytest

from kernel.models.runtime_config import RuntimeConfig
from kernel.parser import Mode, Parser, setup_parser


def make_parser() -> Parser:
    return setup_parser()


def parse_args(args: list[str]) -> RuntimeConfig:
    return make_parser().parse_args(args)


@pytest.fixture()
def parser() -> Parser:
    return make_parser()


@pytest.fixture()
def valid_phone() -> str:
    return "09120000000"


@pytest.fixture()
def valid_proxy() -> str:
    return "http://127.0.0.1:8080"


class TestMode:

    def test_unlimited_value(self) -> None:
        assert Mode.UNLIMITED == "unlimited"

    def test_limited_value(self) -> None:
        assert Mode.LIMITED == "limited"

    def test_mode_from_string(self) -> None:
        assert Mode("unlimited") is Mode.UNLIMITED
        assert Mode("limited") is Mode.LIMITED

    def test_invalid_mode_raises(self) -> None:
        with pytest.raises(ValueError):
            Mode("invalid_mode")


class TestValidRange:

    def test_valid_value_equals_minimum(self) -> None:
        validator = Parser.valid_range(1)
        assert validator("1") == 1

    def test_valid_value_above_minimum(self) -> None:
        validator = Parser.valid_range(0)
        assert validator("42") == 42

    def test_value_below_minimum_raises(self) -> None:
        validator = Parser.valid_range(5)

        with pytest.raises(argparse.ArgumentTypeError, match="at least"):
            validator("4")

    def test_non_integer_raises(self) -> None:
        validator = Parser.valid_range(0)

        with pytest.raises(argparse.ArgumentTypeError, match="Invalid integer"):
            validator("abc")

    def test_float_string_raises(self) -> None:
        validator = Parser.valid_range(0)

        with pytest.raises(argparse.ArgumentTypeError, match="Invalid integer"):
            validator("1.5")

    def test_default_minimum_is_zero(self) -> None:
        validator = Parser.valid_range()
        assert validator("0") == 0

    def test_negative_minimum_allows_negative_values(self) -> None:
        validator = Parser.valid_range(-10)
        assert validator("-5") == -5


class TestRequiredArguments:

    def test_missing_target_exists(self, parser: Parser) -> None:
        with pytest.raises(SystemExit) as exc:
            parser.parse_args([])

        assert exc.value.code != 0

    def test_target_is_accepted(self, valid_phone) -> None:
        config = parse_args(["-t", valid_phone])
        assert config.phone is not None


class TestModeArgument:

    def test_default_mode_is_limited(self, valid_phone) -> None:
        config = parse_args(["-t", valid_phone])
        assert config.bounded is True

    def test_explicit_limited_mode(self, valid_phone) -> None:
        config = parse_args(["-t", valid_phone, "-m", "limited"])
        assert config.bounded is True

    def test_unlimited_mode(self, valid_phone) -> None:
        config = parse_args(["-t", valid_phone, "-m", "unlimited"])
        assert config.bounded is False

    def test_invalid_mode_exists(self, parser: Parser, valid_phone) -> None:
        with pytest.raises(SystemExit):
            parser.parse_args(["-t", valid_phone, "-m", "turbo"])


class TestLimitArgument:

    def test_limit_accepted_in_limited_mode(self, valid_phone) -> None:
        config = parse_args(["-t", valid_phone, "-m", "limited", "-l", "100"])
        assert config.limit == 100

    def test_limit_with_unlimited_mode_exists(
        self, parser: Parser, valid_phone
    ) -> None:
        with pytest.raises(SystemExit):
            parser.parse_args(["-t", valid_phone, "-m", "unlimited", "-l", "50"])

    def test_limit_zero_exists(self, parser: Parser, valid_phone) -> None:
        with pytest.raises(SystemExit):
            parser.parse_args(["-t", valid_phone, "-l", "0"])

    def test_limit_negative_exists(self, parser: Parser, valid_phone) -> None:
        with pytest.raises(SystemExit):
            parser.parse_args(["-t", valid_phone, "-l", "-5"])

    def test_no_limit_in_unlimited_mode_is_none(self, valid_phone) -> None:
        config = parse_args(["-t", valid_phone, "-m", "unlimited"])
        assert config.limit is None

    def test_no_limit_in_limited_mode_is_none(self, valid_phone) -> None:
        config = parse_args(["-t", valid_phone, "-m", "limited"])
        assert config.limit is None


class TestFailTolerance:

    def test_default_fail_tolerance(self, valid_phone) -> None:
        config = parse_args(["-t", valid_phone])
        assert config.fail_tolerance == 6

    def test_custom_fail_tolerance(self, valid_phone) -> None:
        config = parse_args(["-t", valid_phone, "--fail-tolerance", "20"])
        assert config.fail_tolerance == 20

    def test_zero_fail_tolerance_exits(self, parser: Parser, valid_phone) -> None:
        with pytest.raises(SystemExit):
            parser.parse_args(["-t", valid_phone, "--fail_tolerance", "0"])

    def test_low_fail_tolerance_for_high_concurrency_exits(
        self, parser: Parser, valid_phone
    ) -> None:
        with pytest.raises(SystemExit):
            parser.parse_args(["-t", valid_phone, "-c", "20", "--fail-tolerance", "2"])

    def test_adequate_fail_for_concurrency_passes(self, valid_phone) -> None:
        config = parse_args(["-t", valid_phone, "-c", "10", "--fail-tolerance", "5"])
        assert config.fail_tolerance == 5

    def test_fail_tolerance_ignored_in_unlimited_mode(self, valid_phone) -> None:
        config = parse_args(
            ["-t", valid_phone, "-m", "unlimited", "--fail-tolerance", "20"]
        )
        assert config.fail_tolerance == 0


class TestConcurrencyArgument:

    def test_default_concurrency(self, valid_phone) -> None:
        config = parse_args(["-t", valid_phone])
        assert config.concurrency == 6

    def test_custom_concurrency(self, valid_phone) -> None:
        config = parse_args(["-t", valid_phone, "-c", "20", "--fail-tolerance", "10"])
        assert config.concurrency == 20

    def test_zero_concurrency_exits(self, parser: Parser, valid_phone) -> None:
        with pytest.raises(SystemExit):
            parser.parse_args(["-t", valid_phone, "-c", "0"])

    def test_negative_concurrency_exits(self, parser: Parser, valid_phone) -> None:
        with pytest.raises(SystemExit):
            parser.parse_args(["-t", valid_phone, "-c", "-1"])


class TestTimeoutArgument:

    def test_default_timeout(self, valid_phone) -> None:
        config = parse_args(["-t", valid_phone])
        assert config.timeout == 5

    def test_custom_timeout(self, valid_phone) -> None:
        config = parse_args(["-t", valid_phone, "--timeout", "20"])
        assert config.timeout == 20

    def test_zero_timeout_exits(self, parser: Parser, valid_phone) -> None:
        with pytest.raises(SystemExit):
            parser.parse_args(["-t", valid_phone, "--timeout", "0"])


class TestProxyArgument:

    def test_no_proxy_is_none(slef, valid_phone):
        config = parse_args(["-t", valid_phone])
        assert config.proxy is None

    def test_valid_proxy_is_parsed(self, valid_phone, valid_proxy) -> None:
        config = parse_args(["-t", valid_phone, "--proxy", valid_proxy])
        assert config.proxy == valid_proxy

    def test_malformed_proxy_exits(self, parser: Parser, valid_phone) -> None:
        with pytest.raises(SystemExit):
            parser.parse_args(["-t", valid_phone, "--proxy", "not_a_proxy"])

    def test_unsupported_scheme_exits(self, parser: Parser, valid_phone) -> None:
        with pytest.raises(SystemExit):
            parser.parse_args(["-t", valid_phone, "--proxy", "socks5://127.0.0.1:9050"])
            parser.parse_args(["-t", valid_phone, "--proxy", "ftp://127.0.0.1:21"])


class TestFallbackArgument:

    def test_fallback_without_proxy_is_false(self, valid_phone) -> None:
        config = parse_args(["-t", valid_phone, "--fallback"])
        assert config.fallback is False

    def test_fallback_with_proxy_is_true(self, valid_phone, valid_proxy) -> None:
        config = parse_args(["-t", valid_phone, "--proxy", valid_proxy, "--fallback"])
        assert config.fallback is True

    def test_no_fallback_flag_is_false(self, valid_phone, valid_proxy) -> None:
        config = parse_args(["-t", valid_phone, "--proxy", valid_proxy])
        assert config.fallback is False


class TestSSLArgument:

    def test_ssl_default_is_false(self, valid_phone) -> None:
        config = parse_args(["-t", valid_phone])
        assert config.ssl is False

    def test_ssl_flag_enables_ssl(self, valid_phone) -> None:
        config = parse_args(["-t", valid_phone, "--ssl"])
        assert config.ssl is True


class TestApiTemplatesArgument:

    def test_default_api_templates_path(self, valid_phone) -> None:
        config = parse_args(["-t", valid_phone])
        assert isinstance(config.api_templates, Path)

    def test_custom_api_templates_path(self, valid_phone, tmp_path) -> None:
        templates_file = tmp_path / "custom_templates.json"
        templates_file.write_text("[]")

        config = parse_args(["-t", valid_phone, "--api-templates", str(templates_file)])
        assert config.api_templates == templates_file


class TestPhoneValidation:

    def test_invalid_phone_exits(self, parser: Parser) -> None:
        with pytest.raises(SystemExit):
            parser.parse_args(["-t", "not-a_phone"])

    def test_phone_stored_in_config(self, valid_phone) -> None:
        config = parse_args(["-t", valid_phone])
        assert config.phone == "9120000000"

    def test_phone_with_dirt(self) -> None:
        config = parse_args(["-t", "+98-912-000-0000"])
        assert config.phone == "9120000000"


class TestRuntimeConfigOutput:

    def test_returns_runtime_config(self, valid_phone) -> None:
        config = parse_args(["-t", valid_phone])
        assert isinstance(config, RuntimeConfig)

    def test_unlimited_mode_sets_bounded_false(self, valid_phone) -> None:
        config = parse_args(["-t", valid_phone, "-m", "unlimited"])
        assert config.bounded is False
        assert config.limit is None

    def test_limited_mode_with_all_options(self, valid_phone, valid_proxy) -> None:
        config = parse_args(
            [
                "-t",
                valid_phone,
                "-m",
                "limited",
                "-l",
                "50",
                "--fail-tolerance",
                "8",
                "-c",
                "8",
                "--timeout",
                "15",
                "--proxy",
                valid_proxy,
                "--fallback",
                "--ssl",
            ]
        )

        assert config.bounded is True
        assert config.limit == 50
        assert config.fail_tolerance == 8
        assert config.concurrency == 8
        assert config.timeout == 15
        assert config.proxy is not None
        assert config.fallback is True
        assert config.ssl is True


class TestCustomFormatter:

    def test_help_exits_cleanly(self, parser: Parser) -> None:
        with pytest.raises(SystemExit) as exc:
            parser.parse_args(["--help"])

        assert exc.value.code == 0

    def test_help_output_contains_examples(self, parser: Parser, capsys) -> None:
        with pytest.raises(SystemExit):
            parser.parse_args(["--help"])

        captured = capsys.readouterr()
        assert "Examples:" in captured.out


class TestEdgeCases:

    def test_fail_tolerance_excatly_half_concurrency_passes(slef, valid_phone) -> None:
        config = parse_args(["-t", valid_phone, "-c", "10", "--fail-tolerance", "5"])
        assert config.fail_tolerance == 5

    def test_fail_tolerance_one_below_half_concurrency_exits(
        self, parser: Parser, valid_phone
    ) -> None:
        with pytest.raises(SystemExit):
            parser.parse_args(["-t", valid_phone, "-c", "10", "--fail-tolerance", "4"])

    def test_concurrency_one_skips_tolerance_check(self, valid_phone) -> None:
        config = parse_args(["-t", valid_phone, "-c", "1", "--fail-tolerance", "1"])
        assert config.concurrency == 1
