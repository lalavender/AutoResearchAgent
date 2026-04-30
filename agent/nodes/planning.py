import json
from agent.prompts.templates import PLANNING_PROMPT
from agent.llm import get_flash_llm
from agent.progress import push


async def planning_node(state: dict) -> dict:
    topic = state["topic"]
    task_id = state.get("task_id", "")
    llm = get_flash_llm()

    await push(task_id, "planning", "正在分解研究主题...", f"主题: {topic[:60]}")

    prompt = PLANNING_PROMPT.format(topic=topic)
    response = await llm.ainvoke(prompt)
    content = response.content.strip()

    if content.startswith("```"):
        lines = content.split("\n")
        content = "\n".join(lines[1:-1])

    try:
        plan = json.loads(content)
    except json.JSONDecodeError:
        plan = [line.strip("- ").strip() for line in content.split("\n") if line.strip().startswith(("-", "1.", "2.", "3."))]
        if not plan:
            plan = [topic]

    await push(task_id, "planning", f"研究计划已生成", f"共 {len(plan)} 个子问题", {"questions": plan})

    return {
        "plan": plan,
        "completed_questions": [],
        "messages": [{
            "role": "system",
            "phase": "planning",
            "content": f"研究计划已生成，共 {len(plan)} 个子问题",
            "metadata": {"questions": plan},
        }],
    }
