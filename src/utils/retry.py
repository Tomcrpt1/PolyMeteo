from __future__ import annotations

from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential


def network_retry(func):
    return retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
        retry=retry_if_exception_type(Exception),
    )(func)
