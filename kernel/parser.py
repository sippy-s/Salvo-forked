import argparse
from enum import StrEnum
from pathlib import Path
from collections.abc import Callable

from kernel.paths import Paths
from kernel.models.runtime_config import RuntimeConfig
from kernel.utils.validators import phone_validator, proxy_validator
from kernel.exceptions import (
    MalformedProxyError,
    UnsupportedProxyError,
    MalformedPhoneNumberError,
)


class Mode(StrEnum):
    """
    Execution mode of the application.

    - UNLIMITED: runs without limit and bounding
    - LIMITED: runs with a predefined success limit and jailing
    """

    UNLIMITED = "unlimited"
    LIMITED = "limited"


class CustomFormatter(
    argparse.RawDescriptionHelpFormatter, argparse.ArgumentDefaultsHelpFormatter
):
    """
    Custom argparse formatter combining:

      - ArgumentDefaultsHelpFormatter:
          Automatically shows default values in help output.

      - RawDescriptionHelpFormatter:
          Preserves formatting (newlines, spacing) in description and epilog.

    This ensures CLI help output is both readable and informative.
    """

    pass


class Parser(argparse.ArgumentParser):
    """
    Extended ArgumentParser with built-in argument validation rules.

    Adds post-parse validation for cross-arguments constraints such as:
      mode vs limit compatibility.
    """

    def parse_args(self, *args, **kwargs) -> RuntimeConfig:
        """
        Parses CLI arguments and performs additional validation checks.

        Returns:
            Parsed and validated arguments using RuntimeConfig dataclass.

        Raises:
            SystemExit: via self.error() if validation fails.
        """
        args = super().parse_args(*args, **kwargs)

        mode = Mode(args.mode)
        if mode == Mode.UNLIMITED and args.limit is not None:
            self.error("'limit' switch can't be used in 'unlimited' mode.")

        try:
            phone = phone_validator(args.target)

        except MalformedPhoneNumberError as e:
            self.error(e)

        proxy = None
        if args.proxy is not None:
            try:
                proxy = proxy_validator(args.proxy)

            except (MalformedProxyError, UnsupportedProxyError) as e:
                self.error(e)

        bounded = args.mode == Mode.LIMITED
        fail_tolerance = args.fail_tolerance if bounded else 0
        limit = args.limit if bounded else None
        fallback = args.fallback and proxy is not None

        if bounded and fail_tolerance > 0 and fail_tolerance < (args.concurrency // 2):
            self.error(
                f"fail-tolerance ({args.fail_tolerance}) is low for "
                f"{args.concurrency} workers. Consider increasing it "
                "to avoid premature stops."
            )

        return RuntimeConfig(
            phone=phone,
            limit=limit,
            bounded=bounded,
            fail_tolerance=fail_tolerance,
            concurrency=args.concurrency,
            timeout=args.timeout,
            api_templates=args.api_templates,
            proxy=proxy,
            fallback=fallback,
            ssl=args.ssl,
        )

    @staticmethod
    def valid_range(minimum: int = 0) -> Callable[[str], int]:
        """
        Return a validator accepting integers greater than
          or equal to 'minumum'.
        """

        def _validator(value: str) -> int:
            try:
                int_value = int(value)

            except ValueError:
                raise argparse.ArgumentTypeError(f"Invalid integer value: '{value}'.")

            if int_value < minimum:
                raise argparse.ArgumentTypeError(
                    f"Value must be at least '{minimum}', got '{int_value}'."
                )
            return int_value

        return _validator


def setup_parser() -> Parser:
    """Initialize and return configured CLI argument parser."""

    parser = Parser(
        prog="Salvo",
        description="High-performance SMS-Bomber; "
        "Powered by intelligent scheduling and quota control.",
        epilog=(
            "Examples:\n"
            "    python salvo.py -t 0912xxxxxxx\n"
            "    python salvo.py -t +98912xxxxxxx -m unlimited\n"
            "    python salvo.py -t 98912xxxxxxx -m limited\n"
            "    python salvo.py -t +98-912-xxx-xxxx -m limited -l 200\n"
            "    python salvo.py -t 98-912-xxx-xxxx -c 10 --timeout 10\n"
            "    python salvo.py -t +98(912)-xxx-xxxx --proxy http://0.0.0.0:1234 --fallback\n"
            "    python salvo.py -t 0912xxxxxxx --ssl\n\n"
            "API templates format (JSON):\n"
            "    [\n"
            "        {\n"
            '            "source": "example.com",\n'
            '            "url": "https://example.com/sms?phone=98{phone}",\n'
            '            "method": "GET",\n'
            '            "capacity": 10,\n'
            '            "ticket": 62\n'
            "        },\n"
            "        {\n"
            '            "source": "sample.ir",\n'
            '            "url": "https://sample.ir/auth/sms",\n'
            '            "json": {"identifier": "0{phone}"},\n'
            '            "data": {"identifier": "0{phone}"},\n'
            '            "method": "POST",\n'
            '            "capacity": 20,\n'
            '            "ticket": 100\n'
            "        },\n"
            "    ]\n"
            "    - API names starting with '#' are ignored, ticket = 0 and capacity = 0 disables the API.\n\n"
        ),
        formatter_class=CustomFormatter,
    )

    # Required target phone number
    parser.add_argument(
        "-t",
        "--target",
        required=True,
        metavar="PHONE",
        help="Target phone number (e.g. 0912xxxxxxx)",
    )

    parser.add_argument(
        "-m",
        "--mode",
        type=Mode,
        choices=tuple(Mode),
        default=Mode.LIMITED,
        help="Execution mode (controls bounding behavior)",
    )

    parser.add_argument(
        "-l",
        "--limit",
        type=parser.valid_range(1),
        metavar="N",
        help="Success limit when running in 'limited' mode",
    )

    parser.add_argument(
        "--fail-tolerance",
        type=parser.valid_range(1),
        default=6,
        metavar="N",
        help="Maximum consecutive failures before stopping or "
        "triggering fallback (if proxy exists and fallback is on)",
    )

    parser.add_argument(
        "-c",
        "--concurrency",
        type=parser.valid_range(1),
        default=6,
        metavar="N",
        help="Number of concurrent workers",
    )

    parser.add_argument(
        "--timeout",
        type=parser.valid_range(1),
        default=5,
        metavar="SECONDS",
        help="HTTP request timeout in seconds",
    )

    parser.add_argument(
        "--api-templates",
        type=Path,
        default=Paths.shorter(Paths.BASE, Paths.API_TEMPLATES_JSON),
        metavar="FILE",
        help="Path to API templates json file",
    )

    parser.add_argument("--proxy", metavar="URL", help="Proxy URL")

    parser.add_argument(
        "--fallback", action="store_true", help="Enable fallback behaviour"
    )

    parser.add_argument(
        "--ssl", action="store_true", help="Enable SSL certificate verification"
    )

    return parser
