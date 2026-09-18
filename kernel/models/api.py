from typing import Literal
from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class ApiCall:
    """
    Immutable representation of a single API request configuration.

    Attributes:
        source | str: Identifier of the API source.

        url | str: Target endpoint URL.

        method | Literal["POST", "GET"]: HTTP method used for the request.

        data | dict|None: From-data payload (used for POST requests).

        json | dict|None: JSON payload (used for POST requests).

    Notes:
        - Either 'data' or 'json' may be used, but not both simultaneously
        - This class is immutable (frozen=True) for safety in scheduling systems
    """

    source: str
    url: str
    method: Literal["POST", "GET"]
    data: dict | None = None
    json: dict | None = None


@dataclass(slots=True)
class ApiSlot:
    """
    Runtime wrapper for an API call with scheduling and state tracking.

    Attributes:
        call | ApiCall: The underlying API request configuration.

        capacity | int: Maximum allowed execution capacity (quota).

        ticket | int: Priority weight used in scheduling (e.g. Fenwick tree weight).

        strikes | int: Number of failed attempts or violations recorded for this slot.

        was_jailed | bool: Indicates whether the API slot is currently suspended.

        jailed_until | float|None: Time-stamp until which this API slot is
          temporarily blocked. None means not jailed.
    """

    index: int

    call: ApiCall

    capacity: int = 0
    ticket: int = 0

    strikes: int = 0
    was_jailed: bool = False
    jailed_until: float | None = None
