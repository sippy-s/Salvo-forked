import asyncio
from unittest.mock import MagicMock

import pytest

from kernel.core.api_pool import ApiPool
from kernel.console.console import Console
from kernel.models.api import ApiCall, ApiSlot
from kernel.console.tags import ConsoleTag, EventTag


def make_call(source: str = "example.com") -> ApiCall:
    return ApiCall(source=source, url=f"https://{source}/sms", method="GET")


def make_slot(
    index: int, source: str | None = None, ticket: int = 10, capacity: int = 5
) -> ApiSlot:
    source = source or f"api{index}.com"
    return ApiSlot(
        index=index, call=make_call(source), ticket=ticket, capacity=capacity
    )


def make_console() -> MagicMock:
    console = MagicMock(spec=Console)
    console.event = MagicMock()
    return console


def make_pool(
    slots: list[ApiSlot] | None = None,
    bounded: bool = True,
    console: MagicMock | None = None,
) -> ApiPool:
    if slots is None:
        slots = [make_slot(i) for i in range(1, 4)]

    if console is None:
        console = make_console()

    return ApiPool(tuple(slots), console, bounded)


def get_time() -> float:
    return asyncio.run(_async_time())


async def _async_time() -> float:
    return asyncio.get_event_loop().time()


def _extract_call_args(mock: MagicMock) -> tuple:
    args, kwargs = mock.call_args
    return args + tuple(kwargs.values())


class TestApiPoolInit:

    def test_slots_are_stored_by_index(self) -> None:
        slots = [make_slot(3), make_slot(1), make_slot(2)]
        pool = make_pool(slots)
        assert [s.index for s in pool._slots] == [1, 2, 3]

    def test_source_index_map_populated(self) -> None:
        slots = [make_slot(1, "a.com"), make_slot(2, "b.com")]
        pool = make_pool(slots)
        assert pool._source_index_map == {"a.com": 1, "b.com": 2}

    def test_removed_starts_empty(self) -> None:
        pool = make_pool()
        assert pool._removed == set()

    def test_bounded_strike_limit(self) -> None:
        pool = make_pool(bounded=True)
        assert pool.strike_limit == 3

    def test_unbounded_strike_limit(self) -> None:
        pool = make_pool(bounded=False)
        assert pool.strike_limit == 0

    def test_bounded_jail_seconds(self) -> None:
        pool = make_pool(bounded=True)
        assert pool.jail_seconds == 20.0

    def test_unbounded_jail_seconds(self) -> None:
        pool = make_pool(bounded=False)
        assert pool.jail_seconds == 0.0

    def test_lock_created(self) -> None:
        pool = make_pool()
        assert isinstance(pool._lock, asyncio.Lock)


class TestInitialWeights:

    def test_bounded_weight_is_capapcity_times_ticket(self) -> None:
        slot = make_slot(1, ticket=5, capacity=4)
        pool = make_pool([slot], bounded=True)
        assert pool._weight_of(slot) == pytest.approx(20.0)

    def test_unbounded_weight_is_ticket_only(self) -> None:
        slot = make_slot(1, ticket=7, capacity=100)
        pool = make_pool([slot], bounded=False)
        assert pool._weight_of(slot) == pytest.approx(7.0)


class TestWeightHelpers:

    def test_weight_of_matches_initial(self) -> None:
        slot = make_slot(1, ticket=3, capacity=4)
        pool = make_pool([slot], bounded=True)
        assert pool._weight_of(slot) == pytest.approx(12.0)

    def test_set_weight_updates_tree(self) -> None:
        slot = make_slot(1, ticket=10, capacity=5)
        pool = make_pool([slot], bounded=True)
        pool._set_weight(slot, 99.0)
        assert pool._weight_of(slot) == pytest.approx(99.0)

    def test_set_weight_to_zero(self) -> None:
        slot = make_slot(1, ticket=10, capacity=5)
        pool = make_pool([slot], bounded=True)
        pool._set_weight(slot, 0.0)
        assert pool._weight_of(slot) == pytest.approx(0.0)

    def test_set_weight_no_op_on_same_value(self) -> None:
        slot = make_slot(1, ticket=10, capacity=2)
        pool = make_pool([slot], bounded=True)
        before = pool._fwt.total()
        pool._set_weight(slot, pool._weight_of(slot))
        assert pool._fwt.total() == pytest.approx(before)


class TestSlotAt:

    def test_first_slot(self) -> None:
        slots = [make_slot(1, "a.com"), make_slot(2, "b.com")]
        pool = make_pool(slots)
        assert pool._slot_at(1).call.source == "a.com"

    def test_second_slot(self) -> None:
        slots = [make_slot(1, "a.com"), make_slot(2, "b.com")]
        pool = make_pool(slots)
        assert pool._slot_at(2).call.source == "b.com"


class TestPick:

    def test_returns_api_call_when_weight_available(self) -> None:
        pool = make_pool(bounded=False)
        result = pool._pick()
        assert result is not None

    def test_bounded_decrements_capacity(self) -> None:
        slot = make_slot(1, ticket=10, capacity=3)
        pool = make_pool([slot], bounded=True)
        pool._pick()
        assert slot.capacity == 2

    def test_bounded_removes_slot_when_capacity_hits_zero(self) -> None:
        slot = make_slot(1, ticket=10, capacity=1)
        pool = make_pool([slot], bounded=True)
        pool._pick()
        assert 1 in pool._removed
        assert pool._weight_of(slot) == pytest.approx(0.0)

    def test_bounded_updates_weight_proportionally(self) -> None:
        slot = make_slot(1, ticket=10, capacity=3)
        pool = make_pool([slot], bounded=True)
        pool._pick()
        assert pool._weight_of(slot) == pytest.approx(2 * 10)

    def test_unbounded_does_not_change_capacity(self) -> None:
        slot = make_slot(1, ticket=10, capacity=5)
        pool = make_pool([slot], bounded=False)
        pool._pick()
        assert slot.capacity == 5

    def test_only_source_with_weight_is_selected(self) -> None:
        slots = [
            make_slot(1, "heavy.com", ticket=1000, capacity=999),
            make_slot(2, "zero.com", ticket=0, capacity=0),
        ]
        pool = make_pool(slots, bounded=False)
        picked = {pool._pick().source for _ in range(20)}
        assert picked == {"heavy.com"}

    def test_weighted_distribution_is_proportional(self) -> None:
        slots = [
            make_slot(1, "a.com", ticket=30, capacity=999),
            make_slot(2, "b.com", ticket=10, capacity=999),
        ]
        pool = make_pool(slots, bounded=False)

        draws = 2000
        counts: dict[str, int] = {"a.com": 0, "b.com": 0}

        for _ in range(draws):
            result = pool._pick()
            counts[result.source] += 1

        ratio = counts["a.com"] / draws
        assert 0.68 <= ratio <= 0.82


class TestAcquitApi:

    def test_resets_strikes(self) -> None:
        slot = make_slot(1, "a.com")
        pool = make_pool([slot])

        slot.strikes = 2

        asyncio.run(pool._acquit_api("a.com"))
        assert slot.strikes == 0

    def test_resets_was_jailed(self) -> None:
        slot = make_slot(1, "a.com")
        pool = make_pool([slot])

        slot.was_jailed = True

        asyncio.run(pool._acquit_api("a.com"))
        assert slot.was_jailed is False

    def test_resets_jailed_until(self) -> None:
        slot = make_slot(1, "a.com")
        pool = make_pool([slot])

        slot.was_jailed = True

        asyncio.run(pool._acquit_api("a.com"))
        assert slot.jailed_until is None

    def test_does_not_restore_weight(self) -> None:
        slot = make_slot(1, "a.com", ticket=10, capacity=5)
        pool = make_pool([slot])

        pool._set_weight(slot, 0.0)
        slot.was_jailed = True

        asyncio.run(pool._acquit_api("a.com"))
        assert pool._weight_of(slot) == pytest.approx(0.0)

    def test_skips_if_source_not_found(self) -> None:
        slot = make_slot(1, "a.com")
        pool = make_pool([slot])

        slot.strikes = 2

        asyncio.run(pool._acquit_api("unknown.com"))
        assert slot.strikes == 2

    def test_skips_reset_if_currently_jailed(self) -> None:
        slot = make_slot(1, "a.com")
        pool = make_pool([slot])

        slot.strikes = 2
        slot.jailed_until = get_time() + 999

        asyncio.run(pool._acquit_api("a.com"))
        assert slot.strikes == 2


class TestStrikeApi:

    def test_increments_strike(self) -> None:
        slot = make_slot(1, "a.com")
        pool = make_pool([slot])

        asyncio.run(pool._strike_api("a.com"))
        assert slot.strikes == 1

    def test_no_jail_below_strike_limit(self) -> None:
        slot = make_slot(1, "a.com")
        pool = make_pool([slot])

        slot.strikes = 1

        asyncio.run(pool._strike_api("a.com"))
        assert slot.jailed_until is None

    def test_jail_on_reaching_strike_limit(self) -> None:
        slot = make_slot(1, "a.com")
        pool = make_pool([slot])

        slot.strikes = pool.strike_limit - 1

        asyncio.run(pool._strike_api("a.com"))
        assert slot.jailed_until is not None

    def test_jail_zeroes_weight(self) -> None:
        slot = make_slot(1, "a.com", ticket=10, capacity=5)
        pool = make_pool([slot])

        slot.strikes = pool.strike_limit - 1

        asyncio.run(pool._strike_api("a.com"))
        assert pool._weight_of(slot) == pytest.approx(0.0)

    def test_jail_emits_correct_console_and_event_tag(self) -> None:
        slot = make_slot(1, "a.com")
        console = make_console()
        pool = make_pool([slot], console=console)

        slot.strikes = pool.strike_limit - 1

        asyncio.run(pool._strike_api("a.com"))
        console.event.assert_called_once()
        assert EventTag.JAILED in _extract_call_args(console.event)
        assert ConsoleTag.NOTICE in _extract_call_args(console.event)

    def test_jail_sets_was_jailed_flag(self) -> None:
        slot = make_slot(1, "a.com")
        pool = make_pool([slot])

        slot.strikes = pool.strike_limit - 1

        asyncio.run(pool._strike_api("a.com"))
        assert slot.was_jailed is True

    def test_jail_resets_strikes_to_zero(self) -> None:
        slot = make_slot(1, "a.com")
        pool = make_pool([slot])

        slot.strikes = pool.strike_limit - 1

        asyncio.run(pool._strike_api("a.com"))
        assert slot.strikes == 0

    def test_purge_after_second_jail(self) -> None:
        slot = make_slot(1, "a.com")
        pool = make_pool([slot])

        slot.strikes = pool.strike_limit - 1
        slot.was_jailed = True

        asyncio.run(pool._strike_api("a.com"))
        assert 1 in pool._removed
        assert pool._weight_of(slot) == pytest.approx(0.0)

    def test_purge_emits_correct_console_and_event_tag(self) -> None:
        slot = make_slot(1, "a.com")
        console = make_console()
        pool = make_pool([slot], console=console)

        slot.strikes = pool.strike_limit - 1
        slot.was_jailed = True

        asyncio.run(pool._strike_api("a.com"))
        assert EventTag.PURGED in _extract_call_args(console.event)
        assert ConsoleTag.NOTICE in _extract_call_args(console.event)

    def test_skips_already_jailed_slot(self) -> None:
        slot = make_slot(1, "a.com")
        pool = make_pool([slot])

        slot.jailed_until = get_time() + 999
        original_strikes = slot.strikes

        asyncio.run(pool._strike_api("a.com"))
        assert slot.strikes == original_strikes

    def test_jail_duration_is_correct(self) -> None:

        async def _run() -> None:
            slot = make_slot(1, "a.com")
            pool = make_pool([slot])

            slot.strikes = pool.strike_limit - 1
            before = asyncio.get_event_loop().time()

            await pool._strike_api("a.com")

            assert slot.jailed_until == pytest.approx(
                before + pool.jail_seconds, abs=0.1
            )

        asyncio.run(_run())


class TestReleaseExpired:

    def test_does_not_release_active_jail(self) -> None:
        slot = make_slot(1, "a.com", ticket=10, capacity=3)
        pool = make_pool([slot])

        pool._set_weight(slot, 0.0)
        slot.jailed_until = get_time() + 999

        asyncio.run(pool._release_expired())
        assert pool._weight_of(slot) == pytest.approx(0.0)

    def test_release_expired_jail(self) -> None:
        slot = make_slot(1, "a.com", ticket=10, capacity=3)
        pool = make_pool([slot])

        pool._set_weight(slot, 0.0)
        slot.jailed_until = get_time() - 1

        asyncio.run(pool._release_expired())
        assert slot.jailed_until is None
        assert pool._weight_of(slot) == pytest.approx(
            float(slot.capacity * slot.ticket)
        )

    def test_release_emits_correct_console_and_event_tag(self) -> None:
        slot = make_slot(1, "a.com", ticket=10, capacity=3)
        console = make_console()
        pool = make_pool([slot], console=console)

        pool._set_weight(slot, 0.0)
        slot.jailed_until = get_time() - 1

        asyncio.run(pool._release_expired())
        console.event.assert_called_once()

        assert EventTag.FREED in _extract_call_args(console.event)
        assert ConsoleTag.NOTICE in _extract_call_args(console.event)

    def test_only_expired_slot_is_released_in_multi_slot_pool(self) -> None:
        slot_a = make_slot(1, "a.com", ticket=10, capacity=3)
        slot_b = make_slot(2, "b.com", ticket=10, capacity=3)
        pool = make_pool([slot_a, slot_b])

        pool._set_weight(slot_a, 0.0)
        pool._set_weight(slot_b, 0.0)
        slot_a.jailed_until = get_time() - 1
        slot_b.jailed_until = get_time() + 999

        asyncio.run(pool._release_expired())

        assert slot_a.jailed_until is None
        assert pool._weight_of(slot_a) == pytest.approx(
            float(slot_a.capacity * slot_a.ticket)
        )
        assert slot_b.jailed_until is not None
        assert pool._weight_of(slot_b) == pytest.approx(0.0)

    def test_skips_removed_slots(self) -> None:
        slot = make_slot(1, "a.com", ticket=10, capacity=3)
        console = make_console()
        pool = make_pool([slot], console=console)

        pool._removed.add(1)
        slot.jailed_until = get_time() - 1

        asyncio.run(pool._release_expired())
        console.event.assert_not_called()

    def test_skips_slots_without_jail(self) -> None:
        slot = make_slot(1, "a.com", ticket=10, capacity=3)
        pool = make_pool([slot])
        original_weight = pool._weight_of(slot)

        asyncio.run(pool._release_expired())
        assert pool._weight_of(slot) == pytest.approx(original_weight)

    def test_does_not_release_zero_capacity_slot(self) -> None:
        slot = make_slot(1, "a.com", ticket=10, capacity=0)
        console = make_console()
        pool = make_pool([slot], console=console)

        slot.jailed_until = get_time() - 1

        asyncio.run(pool._release_expired())

        assert pool._weight_of(slot) == pytest.approx(0.0)

        console.event.assert_not_called()


class TestJedge:

    def test_success_verdict_calls_acquit(self) -> None:
        slot = make_slot(1, "a.com")
        pool = make_pool([slot])

        slot.strikes = 2

        asyncio.run(pool._judge("a.com", True))
        assert slot.strikes == 0

    def test_failure_verdict_calls_strikes(self) -> None:
        slot = make_slot(1, "a.com")
        pool = make_pool([slot])

        asyncio.run(pool._judge("a.com", False))
        assert slot.strikes == 1


class TestIsJailedApi:

    def test_not_jailed_initially(self) -> None:
        pool = make_pool()
        assert pool.is_jailed_api("api1.com") is False

    def test_returns_false_in_unbounded_mode(self) -> None:
        slot = make_slot(1, "a.com")
        pool = make_pool([slot], bounded=False)

        slot.jailed_until = 9999.0
        assert pool.is_jailed_api("a.com") is False

    def test_returns_true_when_jailed(self) -> None:
        slot = make_slot(1, "a.com")
        pool = make_pool([slot], bounded=True)

        slot.jailed_until = get_time() + 999

        assert pool.is_jailed_api("a.com") is True

    def test_returns_false_after_jail_cleared(self) -> None:
        slot = make_slot(1, "a.com")
        pool = make_pool([slot], bounded=True)

        slot.jailed_until = get_time() + 999
        slot.jailed_until = None
        assert pool.is_jailed_api("a.com") is False


class TestNextCall:

    def test_returns_api_call(self) -> None:
        pool = make_pool(bounded=False)
        result = asyncio.run(pool.next_call())
        assert result is not None

    def test_returns_none_when_pool_exhausted(self) -> None:
        slot = make_slot(1, ticket=10, capacity=1)
        pool = make_pool([slot], bounded=True)

        asyncio.run(pool.next_call())  # exhausts the only slot
        result = asyncio.run(pool.next_call())
        assert result is None

    def test_unbounded_skips_lock_logic(slef) -> None:
        slot = make_slot(1, "a.com", ticket=10, capacity=5)
        pool = make_pool([slot], bounded=False)
        result = asyncio.run(pool.next_call(last_source="a.com", last_verdict=False))

        assert slot.strikes == 0
        assert result is not None

    def test_bounded_applies_failure_verdict(self) -> None:
        slot = make_slot(1, "a.com", ticket=10, capacity=10)
        pool = make_pool([slot], bounded=True)

        asyncio.run(pool.next_call(last_source="a.com", last_verdict=False))
        assert slot.strikes == 1

    def test_bounded_applies_success_verdict(slef) -> None:
        slot = make_slot(1, "a.com", ticket=10, capacity=10)
        pool = make_pool([slot], bounded=True)

        asyncio.run(pool.next_call(last_source="a.com", last_verdict=True))
        assert slot.strikes == 0

    def test_no_verdict_when_last_source_is_none(self) -> None:
        slot = make_slot(1, "a.com", ticket=10, capacity=10)
        pool = make_pool([slot], bounded=True)

        asyncio.run(pool.next_call(last_source=None, last_verdict=False))
        assert slot.strikes == 0

    def test_no_verdict_when_last_verdict_is_none(self) -> None:
        slot = make_slot(1, "a.com", ticket=10, capacity=10)
        pool = make_pool([slot], bounded=True)

        asyncio.run(pool.next_call(last_source="a.com", last_verdict=None))
        assert slot.strikes == 0

    def test_bounded_releases_expired_jails_before_pick(self) -> None:

        async def _run() -> None:
            slot = make_slot(1, "a.com", ticket=10, capacity=5)
            pool = make_pool([slot], bounded=True)

            pool._set_weight(slot, 0.0)
            slot.jailed_until = asyncio.get_event_loop().time() - 1
            result = await pool.next_call()

            assert slot.jailed_until is None
            assert result is not None

        asyncio.run(_run())

    def test_concurrent_calls_do_not_raise(self) -> None:

        async def _run() -> None:
            slots = [make_slot(i, ticket=10, capacity=50) for i in range(1, 6)]
            pool = make_pool(slots, bounded=True)
            results = await asyncio.gather(*[pool.next_call() for _ in range(20)])

            assert all(r is not None or r is None for r in results)

        asyncio.run(_run())

    def test_concurrent_calls_do_not_overdraw_capacity(self) -> None:

        async def _run() -> None:
            capacity = 10
            slot = make_slot(1, "a.com", ticket=10, capacity=capacity)
            pool = make_pool([slot], bounded=True)
            results = await asyncio.gather(*[pool.next_call() for _ in range(20)])
            non_none = [r for r in results if r is not None]

            assert len(non_none) == capacity

        asyncio.run(_run())


class TestFullLifecycle:

    def test_api_jailed_then_freed_after_strikes(self) -> None:

        async def _run() -> None:
            slot = make_slot(1, "a.com", ticket=10, capacity=20)
            console = make_console()
            pool = make_pool([slot], console=console, bounded=True)

            for _ in range(pool.strike_limit):
                await pool._strike_api("a.com")

            assert slot.jailed_until is not None
            assert pool._weight_of(slot) == pytest.approx(0.0)

            slot.jailed_until = asyncio.get_event_loop().time() - 1
            await pool._release_expired()

            assert slot.jailed_until is None
            assert pool._weight_of(slot) > 0

        asyncio.run(_run())

    def test_api_purged_after_two_jail_cycles(self) -> None:

        async def _run() -> None:
            slot = make_slot(1, "a.com", ticket=10, capacity=20)
            console = make_console()
            pool = make_pool([slot], console=console, bounded=True)

            slot.strikes = pool.strike_limit - 1
            await pool._strike_api("a.com")
            assert slot.was_jailed is True

            slot.jailed_until = asyncio.get_event_loop().time() - 1
            await pool._release_expired()

            slot.strikes = pool.strike_limit - 1
            await pool._strike_api("a.com")

            assert 1 in pool._removed
            assert pool._weight_of(slot) == pytest.approx(0.0)

        asyncio.run(_run())

    def test_purged_slot_does_not_affect_neighbour_weight(self) -> None:

        async def _run() -> None:
            slot_a = make_slot(1, "a.com", ticket=10, capacity=20)
            slot_b = make_slot(2, "b.com", ticket=10, capacity=20)
            pool = make_pool([slot_a, slot_b], bounded=True)

            weight_b_before = pool._weight_of(slot_b)

            slot_a.strikes = pool.strike_limit - 1
            slot_a.was_jailed = True

            await pool._strike_api("a.com")

            assert 1 in pool._removed
            assert pool._weight_of(slot_b) == pytest.approx(weight_b_before)

        asyncio.run(_run())

    def test_pool_drains_correctly_in_bounded_mode(self) -> None:

        async def _run() -> None:
            capacity = 3
            slot = make_slot(1, "a.com", ticket=10, capacity=capacity)
            pool = make_pool([slot], bounded=True)

            calls = [await pool.next_call() for _ in range(capacity)]
            assert all(c is not None for c in calls)
            assert await pool.next_call() is None

        asyncio.run(_run())

    def test_unbounded_pool_never_exhausts(self) -> None:

        async def _run() -> None:
            slot = make_slot(1, ticket=10, capacity=1)
            pool = make_pool([slot], bounded=False)

            for _ in range(50):
                result = await pool.next_call()
                assert result is not None

        asyncio.run(_run())
