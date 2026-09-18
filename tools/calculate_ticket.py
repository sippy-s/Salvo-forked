import math


def calculate_score(sent: int, requested: int, capacity: int, max_capacity: int) -> int:
    """
    Compute a ticket score (0-100) for an API based on success rate and relative capacity.

    The score is a weighted geometric mean of:
        - success_rate = sent / requested (weight 0.6)
        - capacity_weight = log(capacity + 1, max_capacity + 1) (weight 0.4)

    If 'requested' or 'max_capacity' is less than 1, the score is 0.

    Args:
        sent | int: number of successful requests sent to this API.
        requested | int: total number of requests sent to this API.
        capacity | int: configured capacity of this API.
        max_capacity | int: maximum capacity across all APIs.

    Returns:
        int | Computed score clamped to [0, 100].
    """
    if requested < 1 or max_capacity < 1:
        return 0

    success_rate = min(sent / requested, 1.0)
    capacity_weight = math.log(capacity + 1, max_capacity + 1)
    score = 100 * (success_rate**0.6) * (capacity_weight**0.4)

    return max(0, min(round(score), 100))
