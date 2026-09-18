import socket


def check_network_access(timeout: int = 10) -> bool:
    """
    Check network connectivity by connecting to Google DNS (8.8.8.8:53).

    Args:
        timeout | int: connection timeout in seconds (default: 10).

    Returns:
        True if connection successful, False otherwise.
    """
    try:
        with socket.create_connection(address=("8.8.8.8", 53), timeout=timeout):
            return True

    except OSError:
        return False
