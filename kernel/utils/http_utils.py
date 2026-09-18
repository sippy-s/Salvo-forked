from aiohttp import ClientSession

from kernel.models.api import ApiCall


async def send_single_request(
    session: ClientSession,
    apicall: ApiCall,
    timeout: int,
    headers: dict,
    proxy: str | None = None,
) -> int:
    """
    Execute a single HTTP request using aiohttp.

    Supports GET and POST methods defined in ApiCall.

    Args:
        session | ClientSession: Shared aiohttp ClientSession.

        apicall | ApiCall: API request definition.

        timeout | int: request timeout in seconds.

        headers | dict: HTTP headers  to attach.

        proxy | str|None: Optional proxy URL.

    Returns:
        HTTP status code (0 if unsopported method or failure).
    """
    match apicall.method:
        case "POST":
            async with session.post(
                url=apicall.url,
                json=apicall.json,
                data=apicall.data,
                headers=headers,
                timeout=timeout,
                proxy=proxy,
            ) as response:
                status_code = response.status

        case "GET":
            async with session.get(
                url=apicall.url, headers=headers, timeout=timeout, proxy=proxy
            ) as response:
                status_code = response.status

        case _:
            status_code = 0

    return status_code
