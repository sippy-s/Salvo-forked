import re


class RegexPatterns:
    """
    Centralized container for commonly used regular expressions.

    This class provides precompiled regex patterns used across
      the system for validation and normalization tasks such as:
          - Proxy URL validation
          - General URL validation
          - Iranian phone number validation
          - Phone number normalization
    """

    PROXY: re.Pattern = re.compile(
        r"^(?P<scheme>[a-zA-Z][a-zA-Z0-9+.-]*)://"
        r"(?:[^:@\s]+:[^:@\s]*@)?"
        r"(?:"
        r"\[[0-9a-fA-F:]+\]|"
        r"(?:\d{1,3}\.){3}\d{1,3}|"
        r"[a-zA-Z0-9.-]+"
        r")"
        r"(?::\d{1,5})?"
        r"(?:/.*)?$"
    )

    URL: re.Pattern = re.compile(
        r"^(https?|ftp)://"
        r"(?:(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}|localhost)"
        r"(?::\d{1,5})?"
        r"(?:/\S*)?$"
    )

    IR_PHONE: re.Pattern = re.compile(r"^(?:98|0)?9\d{9}$")

    PHONE_NORM: re.Pattern = re.compile(r"[^0-9]")
