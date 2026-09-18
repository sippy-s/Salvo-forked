import random
import asyncio

from kernel.models.api import ApiCall, ApiSlot
from kernel.structures.fenwick_tree import FenwickTree
from kernel.console.console import Console, ConsoleTag, EventTag


class ApiPool:
    """
    Weighted API dispatcher with optional bounded-capacity enforcement
      and failure-aware scheduling.

    ApiPool is responsible for selecting the next executeable ApiCall
      from a pool of ApiSlots using a Fenwick Tree (Binary Indexed Tree)
      for efficient weighted random sampling.

    The pool supports two execution modes:
        - Bounded mode:
            - Each API has limited capacity.
            - Capacity decreases after each selection
            - APIs can be temporarily jailed on failure
            - Repeated failures lead to permanent removal

        - Unbounded mode:
            - Selection is based solely on static ticket weights

    Core responsibilities:
        - Weighted random selection of API calls (O(log n))
        - Dynamic weight updates based on runtime state
        - Failure tracking (strike system)
        - Temprary jail + recovery mechanism
        - Permanent removal after repeated failure cycles
        - Thread-safe execution using asyncio lock

    Internal state:
        - _slots: ordered list of ApiSlot objects (1-based index mapping)
        - _fwt: Fenwick Tree storing current weights
        - _source_index_map: fast lookup from API source → slot index
        - _removed: permanently disabled API indices
        - _lock: ensures atomic execution of next_call()

    Design notes:
        - Fenwick Tree is the single source of truth for weights
        - Slot indices are stable and assigned at factory level
        - Bounded mode only modifies weight dynamics, not structure
    """

    @staticmethod
    def _get_time() -> float:
        """
        Returns the current event-loop time.

        Used for scheduling jail expiration in a monotonic-safe way.
        """
        return asyncio.get_event_loop().time()

    def __init__(
        self, slots: tuple[ApiSlot, ...], console: Console, bounded: bool
    ) -> None:
        """
        Initialize the API pool with pre-built ApiSlots.

        Args:
            slots | tupe[ApiSlot]: Pre-constructed ApiSlot objects (1-based indexed, stable).

            console | Console: console instance used for emitting lifecyc events
              (jail, release, purge, etc...)

            bounded | bool: if True, enables capacity-limited execution mode with
              failure tracking and jail/purge logic.
        """
        self._slots: list[ApiSlot] = sorted(slots, key=lambda slot: slot.index)

        self._bounded = bounded
        self._console = console

        self._fwt = FenwickTree([self._initial_weights(slot) for slot in self._slots])

        self._source_index_map: dict[str, int] = {
            slot.call.source: slot.index for slot in self._slots
        }

        self._removed: set[int] = set()

        if bounded:
            self._strike_limit = 3
            self._jail_seconds = 20.0

        else:
            self._strike_limit = 0
            self._jail_seconds = 0.0

        self._lock = asyncio.Lock()

    @property
    def strike_limit(self) -> int:
        return self._strike_limit

    @property
    def jail_seconds(self) -> float:
        return self._jail_seconds

    def _initial_weights(self, slot: ApiSlot) -> float:
        """
        Compute the initial weight of an ApiSlot at pool construction.

        Bounded mode:
            weight = capacity * ticket

        Unbounded mode:
            weight = ticket

        Args:
            slot | ApiSlot: ApiSlot to compute initial weight for.
        """
        if self._bounded:
            return float(slot.capacity * slot.ticket)
        return float(slot.ticket)

    def _weight_of(self, slot: ApiSlot) -> float:
        """
        Return the current weight of a slot as stored in the Fenwick Tree.

        This is computed via prefix-sum difference:

            weight(i) = sum(i) - sum(i - 1)

        Args:
            slot | ApiSlot: Target Apislot.

        Notes:
            - This is an O(log n) read operation
        """
        return self._fwt.prefix_sum(slot.index) - self._fwt.prefix_sum(slot.index - 1)

    def _set_weight(self, slot: ApiSlot, new_weight: float) -> None:
        """
        Updates the weight of a slot by applying a delta to the Fenwick Tree.

        This method ensures the tree remains consistent by computing:

            delta = new_weight - current_weight

        Args:
            slot | ApiSlot: target ApiSlot.

            new_weight | float: Desired absolute weight value.
        """
        delta = new_weight - self._weight_of(slot)

        if delta != 0:
            self._fwt.update(slot.index, delta)

    def _slot_at(self, index: int) -> ApiSlot:
        """
        Retrieve an ApiSlot by 1-based index.

        Args:
            index | int: 1-based slot index.

        Returns:
            ApiSlot at the given position.
        """
        return self._slots[index - 1]

    def _pick(self) -> ApiCall | None:
        """
        Selects an ApiCall using weighted random sampling.

        Process:
            1. Compute total weight from Fenwick Tree
            2. Generate random target in [0, total]
            3. Locate corresponding slot via Fenwick lower-bound search
            4. Apply bounded-mode side effects (capacity reduction)

        Returns:
            Selected ApiCall or None if no valid slot exists.

        Notes:
            - This is the core selection algorithm (O(log n))
        """
        total = self._fwt.total()

        if total <= 0:
            return None

        target = random.random() * total
        index = self._fwt.query(target)

        if index is None:
            return None

        slot = self._slot_at(index)

        if not self._bounded:
            return slot.call

        slot.capacity -= 1

        if slot.capacity <= 0:
            self._set_weight(slot, 0.0)
            self._removed.add(index)

        else:
            self._set_weight(slot, float(slot.capacity * slot.ticket))

        return slot.call

    async def _acquit_api(self, source: str) -> None:
        """
        Resets failure state for a given API source.

        Behavior:
            - Resets strike counter
            - Clears jail state (if not currently jailed)

        Args:
            source | str: API identifier string (ApiSlot.source).
        """
        index = self._source_index_map.get(source)

        if index is None:
            return

        slot = self._slot_at(index)

        if slot.jailed_until is not None:
            return

        slot.strikes = 0
        slot.was_jailed = False
        slot.jailed_until = None

    async def _strike_api(self, source: str) -> None:
        """
        Registers a failure for the given API source.

        Behavior:
            - Increments strike counter
            - First threshold → temporary jail
            - Second threshold → permanent removal

        Side effects:
            - Updates Fenwick Tree weights
            - Emits console events (JAILED / PURGED)

        Args:
            source | str: API identifier string (ApiSlot.source).
        """
        index = self._source_index_map.get(source)

        if index is None:
            return

        slot = self._slot_at(index)

        if index in self._removed:
            return
        
        if slot.jailed_until is not None:
            return

        slot.strikes += 1

        if slot.strikes < self._strike_limit:
            return

        if slot.was_jailed:
            self._set_weight(slot, 0.0)
            self._removed.add(index)

            # slot.strikes = 0
            # slot.was_jailed = False
            # slot.jailed_until = None

            self._console.event(
                ConsoleTag.NOTICE,
                EventTag.PURGED,
                message=f"API '{source}' permanently removed after second jail.",
            )

        else:
            self._set_weight(slot, 0.0)

            slot.jailed_until = self._get_time() + self._jail_seconds
            slot.strikes = 0
            slot.was_jailed = True

            self._console.event(
                ConsoleTag.NOTICE,
                EventTag.JAILED,
                message=f"API '{source}' jailed for {self._jail_seconds}s.",
            )

    async def _release_expired(self) -> None:
        """
        Releases APIs whose jail period has expired.

        Behavior:
            - Iterates over active slots
            - Restores weight if jail timeout passed
            - Emits FREED event via console

        Notes:
            - Complexity is O(n), but expected runtime is low
                due to sparse jail distribution.
        """
        now = self._get_time()

        for slot in self._slots:
            if slot.index in self._removed:
                continue

            if slot.jailed_until is not None and now >= slot.jailed_until:
                slot.jailed_until = None

                if slot.capacity > 0:
                    self._set_weight(slot, float(slot.capacity * slot.ticket))

                    self._console.event(
                        ConsoleTag.NOTICE,
                        EventTag.FREED,
                        message=f"API '{slot.call.source}' freed from jail.",
                    )

    async def _judge(self, source: str, verdict: bool) -> None:
        """
        Applies a success/failure verdict to an API.

        Args:
            source | str: Api identifier string (ApiSlot.source).

            verdict | bool: True = success, False = failure.
        """
        if verdict:
            await self._acquit_api(source)

        else:
            await self._strike_api(source)

    def is_jailed_api(self, source: str) -> bool:
        """
        Checks whether a given API is currently jailed.

        Returns:
            True if API is in jail state, otherwise False.

        Notes:
            - In unbounded mode always returns False.
        """
        if not self._bounded:
            return False

        index = self._source_index_map.get(source)

        if index is None:
            return False

        return self._slot_at(index).jailed_until is not None

    async def next_call(
        self,
        last_source: str | None = None,
        last_verdict: bool | None = None,
    ) -> ApiCall | None:
        """
        Main public API dispatcher entry point.

        Workflow:
            1. Apply verdict of previous API call (if provided)
            2. Release expired jailed APIs
            3. Select next ApiCall via weighted sampling

        Args:
            last_source | str: source of previously executed API.

            last_verdict | bool: Result of previous API execution.

        Returns:
            Next ApiCall or None if no valid API exists.

        Thread-safety:
            - Fully protected by asyncio lock in bounded mode

        """
        if not self._bounded:
            return self._pick()

        async with self._lock:
            if last_source is not None and last_verdict is not None:
                await self._judge(last_source, last_verdict)

            await self._release_expired()

            return self._pick()
