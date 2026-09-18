from pathlib import Path


class Paths:
    """
    Central project paths container.

    Provides a single source of truth to avoid
      hardcoding paths across modules.
    """

    BASE = Path(__name__).parent.parent

    CONFIGS_DIR = BASE / "configs"
    API_TEMPLATES_JSON = CONFIGS_DIR / "api_templates.json"

    KERNEL_DIR = BASE / "kernel"
    CORE_DIR = KERNEL_DIR / "core"
    IO_DIR = KERNEL_DIR / "io"
    MODELS_DIR = KERNEL_DIR / "models"
    STRUCTURES_DIR = KERNEL_DIR / "structures"
    UTILS_DIR = KERNEL_DIR / "utils"

    TESTS_DIR = BASE / "tests"

    @staticmethod
    def shorter(base: Path, path: Path) -> Path:
        """
        Convert absolute path to relative path based on base directory.
        """
        return path.relative_to(base)
