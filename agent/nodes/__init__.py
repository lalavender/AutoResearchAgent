import asyncio
from functools import wraps

NODE_TIMEOUT = 120


def with_timeout(func):
    @wraps(func)
    async def wrapper(state, **kwargs):
        try:
            return await asyncio.wait_for(func(state, **kwargs), timeout=NODE_TIMEOUT)
        except asyncio.TimeoutError:
            return {
                "error": f"节点超时（{NODE_TIMEOUT}s）",
                "messages": [{"role": "system", "phase": "error", "content": "节点执行超时，已跳过当前阶段"}],
            }
    return wrapper
