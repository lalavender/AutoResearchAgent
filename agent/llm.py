import os

from langchain_openai import ChatOpenAI

_flash_llm: ChatOpenAI | None = None
_pro_llm: ChatOpenAI | None = None


def get_flash_llm() -> ChatOpenAI:
    global _flash_llm
    if _flash_llm is None:
        _flash_llm = ChatOpenAI(
            model=os.environ.get("DEEPSEEK_FLASH_MODEL", "deepseek-v4-flash"),
            api_key=os.environ.get("DEEPSEEK_API_KEY", ""),
            base_url=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"),
            temperature=0.3,
            timeout=60,
        )
    return _flash_llm


def get_pro_llm() -> ChatOpenAI:
    global _pro_llm
    if _pro_llm is None:
        _pro_llm = ChatOpenAI(
            model=os.environ.get("DEEPSEEK_PRO_MODEL", "deepseek-v4-pro"),
            api_key=os.environ.get("DEEPSEEK_API_KEY", ""),
            base_url=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"),
            temperature=0.5,
            timeout=120,
        )
    return _pro_llm
