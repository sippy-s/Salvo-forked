from kernel.core.engine import Engine
from kernel.core.api_factory import ApiFactory
from kernel.parser import setup_parser
from kernel.console.console import Console
from kernel.utils.utils import check_network_access
from kernel.exceptions import LoadApiTemplatesError, EmptyApiTemplatesError


def main() -> None:
    """
    Application entry point for the Salvo execution engine.

    This function is responsible for:
        1. Parsing and validating CLI arguments
        2. Initializing console output system
        3. Ensure the device has network access
        4. Ensuring safe execution conditions (proxy confirmation)
        5. Loading and validating API templates
        6. Constructing the runtime Engine
        7. Launching the execution lifecycle

    Execution flow:
        CLI -> Config -> Console -> Safety checks -> API loading -> Engine -> Run

    Failure handling:
        - Invalid or empty API templates -> graceful shutdown (exit code 1)
        - Unexpected runtime errors -> logged and terminated safely
        - KeyboardInterrupt -> clean shutdown (exit code 0)
    """
    config = setup_parser().parse_args()

    console = Console()

    if not check_network_access():
        console.error(
            "No network connection. Please check your internet and try again."
        )
        console.shutdown(1)

    if config.proxy is None and not config.fallback:
        confirm = console.input(
            "No proxy configured. continue with your own IP address? (y/n): "
        ).lower()

        if confirm not in ("y", "yes"):
            console.notice("Mission aborted by operator.")
            console.shutdown(0)

    try:
        context = {"phone": config.phone}
        api_factory = ApiFactory(config.api_templates, context)
        api_factory.build()

        console.notice(f"Loaded {api_factory.count} valid API templates successfully.")

    except (LoadApiTemplatesError, EmptyApiTemplatesError) as e:
        console.error(str(e))
        console.shutdown(1)

    console.clear_screen()

    try:
        engine = Engine(
            api_slots=api_factory.api_slots,
            console=console,
            config=config,
        )
        engine.launch()

    except Exception as e:
        console.error(f"Unexpected error: {str(e)}.")
        console.shutdown(1)


if __name__ == "__main__":
    try:
        main()

    except KeyboardInterrupt:
        Console.shutdown(0)
