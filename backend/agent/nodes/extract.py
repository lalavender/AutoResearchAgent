import asyncio
import json
from backend.agent.llm import get_flash_llm
from backend.agent.prompts.templates import EXTRACT_PROMPT
from backend.agent.progress import push

_llm_semaphore = asyncio.Semaphore(8)


async def _extract_one_question(
    question: str,
    results: list,
    llm,
    task_id: str,
    idx: int,
    total: int,
) -> tuple[str, list[str]]:
    short_q = question[:80]
    await push(task_id, "extract", f"[{idx + 1}/{total}] 提取发现: {short_q}",
               f"从 {len(results)} 个来源提取")

    if not results:
        await push(task_id, "extract", f"[{idx + 1}/{total}] 无信息: {short_q}", "跳过")
        return question, ["未找到相关信息"]

    content_parts = []
    for r in results:
        snippet = r.get("snippet", "") or r.get("content", "") or ""
        if len(snippet) > 50000:
            snippet = snippet[:25000] + "\n...\n" + snippet[-25000:]
        content_parts.append(f"来源: {r.get('title', '未知')}\n{snippet}")

    combined = "\n\n---\n\n".join(content_parts[:10])
    prompt = EXTRACT_PROMPT.format(question=question, content=combined[:80000])

    async with _llm_semaphore:
        response = await llm.ainvoke(prompt)
    content = response.content.strip()

    if content.startswith("```"):
        lines = content.split("\n")
        content = "\n".join(lines[1:-1])

    try:
        extracted = json.loads(content)
    except json.JSONDecodeError:
        extracted = [line.strip("- ").strip() for line in content.split("\n") if line.strip()]

    result = extracted if extracted else ["提取失败"]
    await push(task_id, "extract", f"[{idx + 1}/{total}] 提取完成: {short_q}",
               f"获得 {len(result)} 条发现")
    return question, result


async def extract_node(state: dict) -> dict:
    llm = get_flash_llm()
    task_id = state.get("task_id", "")
    search_results = state.get("search_results", {})
    findings = dict(state.get("findings", {}))
    completed = list(state.get("completed_questions", []))
    messages = list(state.get("messages", []))

    pending = [q for q in search_results if q not in findings]
    total = len(pending)

    if not pending:
        return {"findings": findings, "completed_questions": completed, "messages": messages}

    # 所有问题并发提取
    tasks = [
        _extract_one_question(q, search_results.get(q, []), llm, task_id, i, total)
        for i, q in enumerate(pending)
    ]
    batch_results = await asyncio.gather(*tasks)

    for question, extracted in batch_results:
        findings[question] = extracted
        completed.append(question)
        messages.append({
            "role": "system", "phase": "extract",
            "content": f"从「{question[:40]}」提取到 {len(extracted)} 条发现",
            "metadata": {"question": question, "count": len(extracted)},
        })

    return {
        "findings": findings,
        "completed_questions": completed,
        "messages": messages,
    }
