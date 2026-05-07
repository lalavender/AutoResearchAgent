import os
import asyncio
from typing import List, Dict, Any

from langchain_tavily import TavilySearch


def get_tavily_api_key() -> str | None:
    return os.environ.get("TAVILY_API_KEY")


async def tavily_search(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
    api_key = get_tavily_api_key()
    if not api_key:
        return []

    def _sync_call():
        tool = TavilySearch(max_results=max_results)
        return tool.invoke({"query": query})

    result = await asyncio.to_thread(_sync_call)

    results = []
    for item in result.get("results", []):
        results.append({
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "snippet": item.get("content", ""),
            "score": item.get("score", 0),
            "source": "tavily",
        })
    return results


async def tavily_search_with_content(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
    api_key = get_tavily_api_key()
    if not api_key:
        return []

    def _sync_call():
        tool = TavilySearch(max_results=max_results, include_answer=True, include_raw_content=True)
        return tool.invoke({"query": query})

    result = await asyncio.to_thread(_sync_call)

    results = []
    for item in result.get("results", []):
        results.append({
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "snippet": item.get("content", ""),
            "raw_content": item.get("raw_content", ""),
            "score": item.get("score", 0),
            "source": "tavily",
        })
    if result.get("answer"):
        results.insert(0, {
            "title": "AI Answer",
            "url": "",
            "snippet": result["answer"],
            "source": "tavily_answer",
        })
    return results


async def tavily_gap_search(queries: List[str], max_results: int = 3) -> List[Dict[str, Any]]:
    api_key = get_tavily_api_key()
    if not api_key or not queries:
        return []

    async def _search_one(q: str) -> List[Dict[str, Any]]:
        try:
            results = await tavily_search(q, max_results=max_results)
            for r in results:
                r["source"] = "tavily_gap"
            return results
        except Exception:
            return []

    tasks = [asyncio.create_task(_search_one(q)) for q in queries]
    results_list = await asyncio.gather(*tasks)

    all_results = []
    for results in results_list:
        all_results.extend(results)
    return all_results