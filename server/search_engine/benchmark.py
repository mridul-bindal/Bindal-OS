# Measures how long a search function takes to execute.
import time
from collections.abc import Callable
from typing import Any


def measure_time(func: Callable[..., Any], *args: Any) -> tuple[Any, float]:
    start = time.perf_counter()
    result = func(*args)
    end = time.perf_counter()
    return result, end - start
