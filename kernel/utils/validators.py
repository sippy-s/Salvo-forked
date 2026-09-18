from typing import Any

from kernel.utils._regex_patterns import RegexPatterns
from kernel.exceptions import (
    MalformedPhoneNumberError,
    MalformedProxyError,
    UnsupportedProxyError,
)


class ApiValidator:
    """
    Validates API configuration dictionaries before they are
      converted into runtime 'ApiSlot' objects.

    This validator ensures that required fields exist and
      that all values conform to expected types and constraints.
      It also enforces basic safety rules such as mutual exclusivity
      of request payload types (json vs data).
    """

    REQUIRED_FIELDS = {"source", "url", "method", "capacity", "ticket"}

    @classmethod
    def validate(cls, api_config: dict[str, Any]) -> bool:
        """
        Validates a complete API configuration dictionary.

        Checks:
            - Presence of required fields
            - Validity of source, url, method
            - Positive integer constraints for capacity and ticket
            - Payload consistency (json/data mutual exclusivity)

        Returns:
            True if configuration is valid, False otherwise.
        """
        if any(k not in api_config for k in cls.REQUIRED_FIELDS):
            return False

        json_body = api_config.get("json")
        data_body = api_config.get("data")

        if json_body is not None and data_body is not None:
            return False

        return (
            cls._validate_source(api_config["source"])
            and cls._validate_url(api_config["url"])
            and cls._validate_method(api_config["method"])
            and cls._validate_positive_int(api_config["capacity"])
            and cls._validate_positive_int(api_config["ticket"])
            and cls._validate_payload(json_body)
            and cls._validate_payload(data_body)
        )

    @staticmethod
    def _validate_source(source: Any) -> bool:
        """
        Validates the API source identifier.

        Rules:
            - Must be a non-empty string
            - Must not start with '#'
        """
        if not isinstance(source, str):
            return False

        source = source.strip()

        return bool(source) and not source.startswith("#")

    @staticmethod
    def _validate_url(url: Any) -> bool:
        """
        Validates API URL format.

        Ensures the URL matches the expected HTTP/HTTPS pattern
          defined in 'RegexPatterns.URL'.
        """
        if not isinstance(url, str):
            return False

        return bool(RegexPatterns.URL.fullmatch(url))

    @staticmethod
    def _validate_method(method: Any) -> bool:
        """
        Validates HTTP method.

        Allowed methods:
            - GET
            - POST
        """
        if not isinstance(method, str):
            return False

        return method in {"POST", "GET"}

    @staticmethod
    def _validate_positive_int(value: Any) -> bool:
        """
        Validates that a value is a strictly positive integer.

        Rules:
            - Must be of type int (bool is excluded)
            - Must be greater than 0
        """
        return isinstance(value, int) and not isinstance(value, bool) and value > 0

    @staticmethod
    def _validate_payload(value: Any) -> bool:
        """
        Validates request payload structure.

        Allowed values:
            - None
            - Dictionary (JSON-like structure)
        """
        return value is None or isinstance(value, dict)


def phone_validator(phone_number: str) -> str:
    """
    Validates and normalizes an Iranian phone number.

    Process:
        - Ensures input is a string
        - Removes non-numeric characters
        - Validates against Iranian mobile pattern
        - Normalizes prefix (removes leading 0 or 98)

    Returns:
        Normalized phone number.

    Raises:
        MalformedPhoneNumberError: If format is invalid.
    """
    if not isinstance(phone_number, str):
        raise MalformedPhoneNumberError(repr(phone_number))

    phone_number = phone_number.strip()
    normalized = RegexPatterns.PHONE_NORM.sub("", phone_number)

    if RegexPatterns.IR_PHONE.fullmatch(normalized):
        if normalized.startswith("0"):
            normalized = normalized[1:]

        elif normalized.startswith("98"):
            normalized = normalized[2:]

        return normalized

    raise MalformedPhoneNumberError(phone_number)


def proxy_validator(proxy: str) -> str:
    """
    Validates an HTTP/HTTPS proxy URL.

    Rules:
        - Must be a valid string
        - Must match proxy URL pattern defined in 'RegexPatterns.PROXY'
        - Must use either http or https scheme

    Returns:
        validated proxy URL.

    Raises:
        MalformedProxyError: If proxy format is invalid.
        UnsupportedProxyError: If scheme is not http/https.
    """
    if not isinstance(proxy, str):
        raise MalformedProxyError(repr(proxy))

    proxy = proxy.strip()

    match = RegexPatterns.PROXY.fullmatch(proxy)

    if not match:
        raise MalformedProxyError(proxy)

    scheme = match.group("scheme")

    if scheme not in ("http", "https"):
        raise UnsupportedProxyError(proxy)

    return proxy
