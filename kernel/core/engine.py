import asyncio

from fake_useragent import UserAgent
from aiohttp import ClientSession, TCPConnector

from kernel.core.api_pool import ApiPool
from kernel.core.session_tracker import SessionTracker
from kernel.console.console import Console
from kernel.console.tags import ConsoleTag, EventTag, ResponseTag
from kernel.models.api import ApiSlot, ApiCall
from kernel.models.runtime_config import RuntimeConfig
from kernel.utils.http_utils import send_single_request


class Engine:
    """
    High-performance asynchronous execution engine for API workflows.

    The Engine coordinates:
        - concurrent workers
        - API request dispatching
        - credit-based rate limiting (SessionTracker)
        - fallback handling (proxy -> direct)
        - runtime configuration (RuntimeConfig)

    Execution model:
        Workers continuously fetch API calls from ApiPool,
          execute HTTP requests via aiohttp, and report results
          back to SessionTracker for global state control.

    Stop conditions:
        - success limit reached (if bounded mode)
        - consecutive failure threshold exceeded
        - API pool exhaustion
        - external cancellation

    Design goals:
        - deterministic concurrency control
        - minimal shared state mutation
        - safe credit-based limiting
        - clear separation of request lifecycle stages
    """

    def __init__(
        self, api_slots: tuple[ApiSlot], console: Console, config: RuntimeConfig
    ) -> None:
        """
        Initialize the execution engine.

        Args:
            api_slots | tuple[ApiSlot]: Tuple of API definitions used by ApiPool.

            console | Console: Console interface for logging and events.

            config | RuntimeConfig: RuntimeConfig containing validated runtime parameters.

        Initializes:
            - ApiPool for request scheduling
            - SessionTracker for limit/failure control
            - fallback/proxy configuration
            - HTTP headers and user agent generator
        """
        self._api_pool = ApiPool(
            slots=api_slots, console=console, bounded=config.bounded
        )

        self._traker = SessionTracker(
            limit=config.limit, fail_tolerance=config.fail_tolerance, console=console
        )

        self._config = config
        self._proxy = config.proxy
        self._fallback = config.fallback

        self._console = console
        self._fallback_lock = asyncio.Lock()

        self._ua = UserAgent()
        self._headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Accept-Language": "en-US,en;q=0.9",
        }

    async def _dispatch_request(
        self, session: ClientSession, apicall: ApiCall, ua: str
    ) -> tuple[bool, bool | None]:
        """
        Dispatch a single API request and process lifecycle.

        Flow:
            1. Acquire execution slot (credit system)
            2. Execute HTTP request
            3. Evaluate response verdict
            4. Release slot (refund on failure)
            5. Report result to SessionTracker
            6. Return continuation signal + verdict

        Returns:
            (should_continue, verdict)
              verdict is None for ignored/jailed requests.
        """
        if not await self._traker.acquire_slot():
            return (
                False,
                None,
            )

        try:
            status_code = await send_single_request(
                session=session,
                apicall=apicall,
                timeout=self._config.timeout,
                headers={**self._headers, "User-Agent": ua},
                proxy=self._proxy,
            )

        except Exception as e:
            # request failed -> consumes slot
            await self._traker.release_slot(refund=True)

            if self._api_pool.is_jailed_api(apicall.source):
                return (
                    True,
                    None,
                )

            should_continue = await self._traker.report(
                source=apicall.source,
                status_code=0,
                error=type(e).__name__,
            )

            return (
                should_continue,
                False,
            )

        verdict = self._traker.response_verdict(status_code)

        # zombie / jailed api -> ignored from accounting
        if self._api_pool.is_jailed_api(apicall.source):
            await self._traker.release_slot(refund=True)

            self._console.response(
                _id=0,
                status=ResponseTag.ZOMBIE,
                source=apicall.source,
                status_code=status_code,
            )

            return (
                True,
                None,
            )

        # normal flow
        await self._traker.release_slot(refund=not verdict)

        should_continue = await self._traker.report(
            source=apicall.source,
            status_code=status_code,
        )

        return (
            should_continue,
            verdict,
        )

    async def _worker(self, _id: int, session: ClientSession, ua: str) -> None:
        """
        Worker loop responsible for continuous API execution.

        Each worker:
            - pulls API calls from ApiPool
            - executes requests via _dispatch_request
            - updates routing context (last_source / last_verdict)
            - handles fallback switching when failure threshold is exceeded
            - stops when global stop event is triggered

        Args:
            _id | int: Worker identifier.

            session | ClientSession: shared aiohttp session.

            ua | str: random user-agent string (each worker has its own ua).
        """
        last_source = None
        last_verdict = None

        while not self._traker.is_stopped:

            apicall = await self._api_pool.next_call(
                last_source=last_source,
                last_verdict=last_verdict,
            )

            if apicall is None:
                self._console.notice(f"Worker {_id:02d}; API pool fully depleted.")
                return

            should_continue, verdict = await self._dispatch_request(
                session=session, apicall=apicall, ua=ua
            )

            if verdict is None:
                last_source = None
                last_verdict = None
                continue

            last_source = apicall.source
            last_verdict = verdict

            # fallback logic
            async with self._fallback_lock:
                if (
                    self._proxy
                    and self._fallback
                    and self._traker.consec_fail >= self._traker.fail_tolerance
                ):
                    self._console.event(
                        severity=ConsoleTag.NOTICE,
                        event=EventTag.FALLBACK,
                        message=(
                            f"Proxy {self._proxy} failed "
                            f"{self._traker.consec_fail} times. "
                            "Falling back to direct connection"
                        ),
                    )

                    self._fallback = False
                    self._proxy = None

                    await self._traker.reset_consec_fail()
                    await self._traker.clear_stop_event()

            if not should_continue:
                self._traker.stop_event.clear()
                break

        self._console.notice(f"Worker {_id:02d} shutting down; mission stopped.")

    async def _execute(self) -> None:
        """
        Main orchestration loop for the Engine.

        Responsibilities:
            - create HTTP session with concurrency limits
            - spawn worker tasks
            - monitor execution lifecycle
            - collect final statistics
            - ensure graceful shutdown
        """
        self._console.start_logger()
        _start_time = asyncio.get_event_loop().time()

        tcp_connector = TCPConnector(
            ssl=self._config.ssl, limit=self._config.concurrency
        )
        async with ClientSession(connector=tcp_connector) as session:
            try:
                workers = [
                    asyncio.create_task(self._worker(i, session, self._ua.random))
                    for i in range(1, self._config.concurrency + 1)
                ]

                self._console.notice(
                    "All workers are running. Awaiting first response."
                )

                await asyncio.gather(*workers)

            except asyncio.CancelledError:
                self._console.warning("Mission aborted by operator.")

            finally:
                self._traker.stop_event.set()
                _elpased_time = asyncio.get_event_loop().time() - _start_time

                self._console.notice("Mission Completed.")
                self._console.summary(
                    success=self._traker.success,
                    failure=self._traker.failure,
                    total_time=_elpased_time,
                )

                await self._console.stop_logger()

    def launch(self) -> None:
        """
        Entry point for starting the Engine.

        Logs initial configuration and runs the async execution loop.
        """
        self._console.notice(message="Mission Started", **self._config.as_dict)

        asyncio.run(self._execute())
