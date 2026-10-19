"""Stand-in for the external "transformer" service.

Every call is treated as expensive (network round trip, possibly billed), which is why
the rest of the service goes out of its way to call it as rarely as possible.
"""

import time
from collections.abc import Callable

Transformer = Callable[[str], str]


def make_transformer(delay_seconds: float = 0.0) -> Transformer:
    """Build the transformer; ``delay_seconds`` simulates the external call's latency."""

    def transform(value: str) -> str:
        if delay_seconds:
            time.sleep(delay_seconds)
        return value.upper()

    return transform
