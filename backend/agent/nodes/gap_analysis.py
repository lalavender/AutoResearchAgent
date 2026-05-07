import json
from backend.agent.llm import get_flash_llm
from backend.agent.prompts.templates import GAP_ANALYSIS_PROMPT
from backend.agent.progress import push


async def gap_analysis_node(state: dict) -> dict:
    llm = get_flash_llm()
    task_id = state.get("task_id", "")
    plan = state.get("plan", [])
    findings = state.get("findings", {})
    completed = state.get("completed_questions", [])
    iteration = state.get("iteration", 0)
    max_iterations = state.get("max_iterations", 3)
    messages = list(state.get("messages", []))

    total_findings = sum(len(v) for v in findings.values())
    await push(task_id, "gap", f"正在分析知识完整性...",
               f"第{iteration + 1}/{max_iterations}轮，已覆盖{len(completed)}/{len(plan)}个子问题，共{total_findings}条发现")

    findings_summary = json.dumps(
        {q: findings.get(q, []) for q in plan},
        ensure_ascii=False,
    )

    prompt = GAP_ANALYSIS_PROMPT.format(
        plan=json.dumps(plan, ensure_ascii=False),
        findings_summary=findings_summary[:12000],
        iteration=iteration + 1,
        max_iterations=max_iterations,
    )
    response = await llm.ainvoke(prompt)
    content = response.content.strip()

    if content.startswith("```"):
        lines = content.split("\n")
        content = "\n".join(lines[1:-1])

    try:
        result = json.loads(content)
        gaps = result.get("gaps", [])
        sufficient = result.get("sufficient", True)
    except json.JSONDecodeError:
        gaps = []
        sufficient = True

    if sufficient and gaps:
        gaps = []

    new_iteration = iteration + 1

    if gaps:
        await push(task_id, "gap", f"发现 {len(gaps)} 个知识缺口，继续深入",
                   f"缺口: {gaps[0][:60]}..." if gaps else "",
                   {"gaps": gaps, "iteration": new_iteration})
    else:
        await push(task_id, "gap", "信息已充分，准备生成报告",
                   f"完成 {len(plan)} 个子问题的研究，共 {total_findings} 条发现")

    messages.append({
        "role": "system", "phase": "gap",
        "content": f"第 {new_iteration} 轮缺口分析：{'发现 ' + str(len(gaps)) + ' 个知识缺口' if gaps else '信息已充分，准备生成报告'}",
        "metadata": {"gaps": gaps, "iteration": new_iteration, "sufficient": sufficient},
    })

    return {
        "gaps": gaps,
        "iteration": new_iteration,
        "messages": messages,
    }
