from pathlib import Path


class LoadApiTemplatesError(Exception):
    """Raised when the API templates file can't be loaded or parsed."""

    def __init__(self, path: Path) -> None:
        super().__init__(f"Unable to load API templates from file: '{path}'.")


class EmptyApiTemplatesError(Exception):
    """Raised when no valid API templates remain after filtering."""

    def __init__(self, path: Path) -> None:
        super().__init__(f"No valid API templates found in: '{path}'.")


class MalformedPhoneNumberError(Exception):
    """Raised when the supplied phone number doesn't match the expected Iranian format."""

    def __init__(self, phone: str) -> None:
        super().__init__(
            f"Malformed phone number: '{phone}'. "
            "Expected Iranian mobile format (e.g. 0912xxxxxxx)."
        )


class MalformedProxyError(Exception):
    """Raised when the supplied proxy URL is not valid."""

    def __init__(self, proxy: str) -> None:
        super().__init__(f"Malformed proxy URL: '{proxy}'.")


class UnsupportedProxyError(Exception):
    """Raises when proxy scheme is valid but not supported."""

    def __init__(self, proxy: str) -> None:
        super().__init__(
            f"Unsupported proxy type: '{proxy}'. Only HTTP/HTTPS are supported."
        )
