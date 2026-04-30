import asyncio
from agent.llm import get_flash_llm
from agent.tools import tier1_search, google_search, web_fetch
from agent.progress import push

_llm_semaphore = asyncio.Semaphore(4)


def _truncate(text: str, max_words: int = 8000) -> str:
    words = text.split()
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words])


async def _tier2_search_with_fetch(question: str, max_results: int = 5) -> list:
    """Tier2 搜索 + 并发抓取所有网页"""
    try:
        results = await google_search(question, max_results=max_results)
    except Exception:
        return []

    if not results:
        return []

    # 并发抓取所有网页
    urls = [(i, r) for i, r in enumerate(results[:max_results]) if r.get("url")]
    if urls:
        async def _fetch_one(idx, r):
            try:
                content = await web_fetch(r["url"])
                if content:
                    r["content"] = _truncate(content)
            except Exception:
                pass

        await asyncio.gather(*(_fetch_one(i, r) for i, r in urls))

    return results


async def _search_one_question(
    question: str,
    llm,
    task_id: str,
    q_num: int,
    total_batch: int,
    iteration: int,
    gap_query: str | None,
) -> tuple[str, list]:
    short_q = question[:80]
    results = []

    # Tier1 和 Tier2 并发执行
    await push(task_id, "search", f"[{q_num}/{total_batch}] 并发搜索: {short_q}",
               f"第{iteration + 1}轮，Tier1 LLM + Tier2 opencli 同时进行")

    async def _tier1():
        async with _llm_semaphore:
            return await tier1_search(question, llm)

    tier1_task = asyncio.create_task(_tier1())
    tier2_task = asyncio.create_task(_tier2_search_with_fetch(question, max_results=5))

    tier1_results, google_results = await asyncio.gather(tier1_task, tier2_task)

    if tier1_results:
        results.extend(tier1_results)
        await push(task_id, "search", f"[{q_num}/{total_batch}] Tier1 完成: {short_q}",
                   f"LLM 知识回答获取 {len(tier1_results)} 条")

    if google_results:
        results = results[:1] + google_results + results[1:] if len(results) > 1 else results + google_results
        await push(task_id, "search", f"[{q_num}/{total_batch}] Tier2 完成: {short_q}",
                   f"opencli 搜索 + 并发抓取 {len(google_results)} 个网页")
    else:
        await push(task_id, "search", f"[{q_num}/{total_batch}] Tier2 跳过: {short_q}",
                   "opencli 不可用或无法连接浏览器")

    # Gap 补充搜索
    if gap_query and iteration > 0:
        await push(task_id, "search", f"[{q_num}/{total_batch}] 缺口补充搜索: {gap_query[:60]}", "")
        try:
            gap_results = await google_search(gap_query, max_results=3)
            if gap_results:
                urls = [(i, r) for i, r in enumerate(gap_results) if r.get("url")]
                if urls:

                    async def _fetch_gap(idx, r):
                        try:
                            content = await web_fetch(r["url"])
                            if content:
                                r["content"] = _truncate(content)
                                r["source"] = "tier2_gap"
                        except Exception:
                            pass

                    await asyncio.gather(*(_fetch_gap(i, r) for i, r in urls))
                results.extend(gap_results)
        except Exception:
            pass

    await push(task_id, "search", f"[{q_num}/{total_batch}] 搜索完成: {short_q}",
               f"共获取 {len(results)} 个结果（Tier1 + Tier2 + Gap）")

    return question, results


async def search_node(state: dict) -> dict:
    llm = get_flash_llm()
    task_id = state.get("task_id", "")
    plan = state.get("plan", [])
    completed = state.get("completed_questions", [])
    search_results = dict(state.get("search_results", {}))
    messages = list(state.get("messages", []))
    iteration = state.get("iteration", 0)

    open_questions = [q for q in plan if q not in completed]
    if not open_questions:
        return {"messages": messages}

    batch = open_questions[:3]
    total_batch = len(batch)

    gaps = state.get("gaps", [])
    gap_query = gaps[0] if gaps and iteration > 0 else None

    # 所有问题并发搜索
    tasks = [
        _search_one_question(q, llm, task_id, i + 1, total_batch, iteration, gap_query)
        for i, q in enumerate(batch)
    ]
    batch_results = await asyncio.gather(*tasks)

    for question, results in batch_results:
        short_q = question[:80]
        search_results[question] = results
        messages.append({
            "role": "tool", "phase": "search",
            "content": f"搜索完成: {short_q} → {len(results)} 个结果",
            "metadata": {"question": question, "count": len(results)},
        })

    return {
        "search_results": search_results,
        "messages": messages,
    }
