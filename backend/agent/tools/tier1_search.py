import json
from typing import List, Dict, Any
from langchain_openai import ChatOpenAI
from backend.agent.prompts.templates import TIER1_SEARCH_PROMPT


async def tier1_search(question: str, llm: ChatOpenAI) -> List[Dict[str, Any]]:
    prompt = TIER1_SEARCH_PROMPT.format(question=question)
    response = await llm.ainvoke(prompt)
    content = response.content if hasattr(response, "content") else str(response)
    return [{
        "title": question,
        "url": "",
        "snippet": content,
        "content": content,
        "source": "tier1_llm",
    }]
