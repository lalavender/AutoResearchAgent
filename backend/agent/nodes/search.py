import asyncio
from backend.agent.llm import get_flash_llm
from backend.agent.tools import tier1_search, tavily_search, tavily_search_with_content, tavily_gap_search
from backend.agent.progress import push

_llm_semaphore = asyncio.Semaphore(8)
MAX_QUESTIONS_PER_ROUND = 10


def _truncate(text: str, max_chars: int = 200000) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars]


async def _tier2_search(question: str, max_results: int = 5) -> list:
    try:
        results = await tavily_search_with_content(question, max_results=max_results)
    except Exception:
        return []

    for r in results:
        if r.get("raw_content"):
            r["content"] = _truncate(r["raw_content"])

    return results


async def _search_one_question(
    question: str,
    llm,
    task_id: str,
    q_num: int,
    total_batch: int,
    iteration: int,
) -> tuple[str, list]:
    short_q = question[:80]

    async def _tier1():
        async with _llm_semaphore:
            return await tier1_search(question, llm)

    await push(task_id, "search", f"[{q_num}/{total_batch}] 并发搜索: {short_q}",
               f"第{iteration + 1}轮，Tier1 + Tier2 并行")

    tier1_task = asyncio.create_task(_tier1())
    tier2_task = asyncio.create_task(_tier2_search(question, max_results=5))

    tier1_results, tavily_results = await asyncio.gather(tier1_task, tier2_task)

    results = []
    if tier1_results:
        results.extend(tier1_results)
        await push(task_id, "search", f"[{q_num}/{total_batch}] Tier1 完成: {short_q}",
                   f"LLM 知识回答 {len(tier1_results)} 条")

    if tavily_results:
        results = results[:1] + tavily_results + results[1:] if len(results) > 1 else results + tavily_results
        await push(task_id, "search", f"[{q_num}/{total_batch}] Tier2 完成: {short_q}",
                   f"Tavily {len(tavily_results)} 个结果")
    else:
        await push(task_id, "search", f"[{q_num}/{total_batch}] Tier2 跳过: {short_q}", "Tavily 不可用")

    await push(task_id, "search", f"[{q_num}/{total_batch}] 搜索完成: {short_q}",
               f"共 {len(results)} 个结果")

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

    batch = open_questions[:MAX_QUESTIONS_PER_ROUND]
    total_batch = len(batch)

    tasks = [
        _search_one_question(q, llm, task_id, i + 1, total_batch, iteration)
        for i, q in enumerate(batch)
    ]
    batch_results = await asyncio.gather(*tasks)

    for question, results in batch_results:
        search_results[question] = results

    # Gap 批处理（所有问题完成后统一搜索）
    gaps = state.get("gaps", [])
    if gaps and iteration > 0:
        await push(task_id, "search", f"Gap 补充搜索: {len(gaps)} 个缺口", "")
        gap_results = await tavily_gap_search(gaps[:5], max_results=3)
        if gap_results:
            await push(task_id, "search", "Gap 搜索完成", f"获取 {len(gap_results)} 个结果")

    for question, results in batch_results:
        short_q = question[:80]
        messages.append({
            "role": "tool", "phase": "search",
            "content": f"搜索完成: {short_q} → {len(results)} 个结果",
            "metadata": {"question": question, "count": len(results)},
        })

    return {
        "search_results": search_results,
        "messages": messages,
        "completed_questions": completed + batch,
    }