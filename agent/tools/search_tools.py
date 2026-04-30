import asyncio
import json
from typing import List, Dict, Any

OPENCLI_PATH = "/opt/homebrew/bin/opencli"
_search_semaphore = asyncio.Semaphore(5)


async def _run_opencli(*args: str, timeout: int = 30) -> str:
    async with _search_semaphore:
        proc = await asyncio.create_subprocess_exec(
            OPENCLI_PATH, *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            return ""
        return stdout.decode("utf-8", errors="replace")


async def google_search(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
    output = await _run_opencli("google", "search", query, timeout=30)
    if not output:
        return []
    results = []
    for line in output.strip().split("\n"):
        if len(results) >= max_results:
            break
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) >= 2:
            results.append({
                "title": parts[0].strip(),
                "url": parts[1].strip() if len(parts) > 1 else "",
                "snippet": parts[2].strip() if len(parts) > 2 else "",
                "source": "tier2_opencli",
            })
    return results


async def google_news_search(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
    output = await _run_opencli("google", "news", query, timeout=30)
    if not output:
        return []
    results = []
    for line in output.strip().split("\n"):
        if len(results) >= max_results:
            break
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) >= 2:
            results.append({
                "title": parts[0].strip(),
                "url": parts[1].strip() if len(parts) > 1 else "",
                "snippet": parts[2].strip() if len(parts) > 2 else "",
                "source": "tier2_opencli_news",
            })
    return results


async def web_fetch(url: str, timeout: int = 60) -> str:
    output = await _run_opencli("web", "read", url, timeout=timeout)
    if not output:
        return ""
    return output


async def arxiv_search(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
    output = await _run_opencli("arxiv", "search", query, timeout=30)
    if not output:
        return []
    results = []
    for line in output.strip().split("\n"):
        if len(results) >= max_results:
            break
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) >= 2:
            results.append({
                "title": parts[0].strip(),
                "url": parts[1].strip() if len(parts) > 1 else "",
                "snippet": parts[2].strip() if len(parts) > 2 else "",
                "source": "tier2_arxiv",
            })
    return results
