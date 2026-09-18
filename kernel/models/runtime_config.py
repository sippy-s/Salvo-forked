from pathlib import Path
from dataclasses import dataclass, asdict


@dataclass(slots=True, frozen=True)
class RuntimeConfig:
    """
    Immutable runtime configuration for the application.

    This dataclass represents the fully parsed and validated CLI state
      after all preprocessing steps (parsing, validation, normalization).

    It is used as the single source of truth for runtime behavior of the Engine.

    Attributes:
        phone | str: target phone number after validation.

        limit | int|None: maximum number of successful operations in bounded mode.

        bounded | bool: whether execution is limited by a success cap.

        fail_tolerance | int: maximum consecutive failures allowed before stop/fallback.

        concurrency | int: number of concurrent workers.

        timeout | int: HTTP request timeout in seconds.

        api_templates | Path: path to API template definition file.

        proxy | str|None: Optional proxy URL for routing requests.

        fallback | bool: whether fallback to direct connection is enabled.

        ssl | bool: whether SSL verification is enabled.
    """

    phone: str
    limit: int | None
    bounded: bool
    fail_tolerance: int
    concurrency: int
    timeout: int
    api_templates: Path
    proxy: str | None
    fallback: bool
    ssl: bool

    @property
    def as_dict(self) -> dict:
        """
        Convert runtime configuration into a dictionary representation.

        Useful for logging, debugging, or displaying startup configuration
          in a human-readable format.

        Returns:
            Dictionary containing all runtime configuration fields.
        """
        return asdict(self)
