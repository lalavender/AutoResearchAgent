import asyncio
from typing import Dict

_queues: Dict[str, asyncio.Queue] = {}


def register(task_id: str) -> asyncio.Queue:
    q = asyncio.Queue()
    _queues[task_id] = q
    return q


def unregister(task_id: str):
    _queues.pop(task_id, None)


async def push(task_id: str, phase: str, message: str, detail: str = "", metadata: dict | None = None):
    if task_id in _queues:
        await _queues[task_id].put({
            "phase": phase,
            "message": message,
            "detail": detail,
            "metadata": metadata or {},
        })
