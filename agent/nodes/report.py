import json
from agent.llm import get_pro_llm
from agent.prompts.templates import REPORT_PROMPT
from agent.progress import push
from storage.file_store import save_report, save_state


async def report_node(state: dict) -> dict:
    llm = get_pro_llm()
    task_id = state.get("task_id", "")
    topic = state["topic"]
    plan = state.get("plan", [])
    findings = state.get("findings", {})
    messages = list(state.get("messages", []))

    total_findings = sum(len(v) for v in findings.values())
    await push(task_id, "report", "正在生成研究报告...",
               f"综合 {len(plan)} 个子问题、{total_findings} 条发现，使用 Pro 模型深度推理")

    findings_text = json.dumps(findings, ensure_ascii=False, indent=2)

    prompt = REPORT_PROMPT.format(
        topic=topic,
        plan=json.dumps(plan, ensure_ascii=False),
        findings=findings_text[:24000],
    )
    response = await llm.ainvoke(prompt)
    report = response.content.strip()

    await push(task_id, "report", "正在保存研究报告...", "")
    report_path = await save_report(topic, report, state)
    await save_state(state)

    await push(task_id, "report", f"研究报告已保存", f"文件: {report_path}")

    messages.append({
        "role": "system", "phase": "report",
        "content": f"研究报告已生成: {report_path}",
        "metadata": {"report_path": report_path},
    })

    return {
        "report": report,
        "report_path": report_path,
        "status": "completed",
        "messages": messages,
    }
