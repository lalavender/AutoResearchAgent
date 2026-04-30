import json
import re
from pathlib import Path
from datetime import datetime

DATA_DIR = Path("data")
REPORTS_DIR = DATA_DIR / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def _slugify(text: str) -> str:
    slug = re.sub(r"[^\w\s-]", "", text)
    slug = re.sub(r"[-\s]+", "-", slug)
    return slug[:50].strip("-").lower()


async def save_report(topic: str, content: str, state: dict) -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    slug = _slugify(topic)
    filename = f"{timestamp}_{slug}.md"
    path = REPORTS_DIR / filename
    path.write_text(content, encoding="utf-8")
    return str(path)


async def save_state(state: dict) -> str:
    topic = state.get("topic", "unknown")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    slug = _slugify(topic)
    filename = f"{timestamp}_{slug}_state.json"
    path = REPORTS_DIR / filename
    serializable = {}
    for k, v in state.items():
        if callable(v):
            continue
        try:
            json.dumps(v)
            serializable[k] = v
        except (TypeError, ValueError):
            serializable[k] = str(v)
    path.write_text(json.dumps(serializable, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def list_reports() -> list[dict]:
    reports = []
    for f in sorted(REPORTS_DIR.glob("*.md"), reverse=True):
        reports.append({
            "filename": f.name,
            "created_at": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
            "size": f.stat().st_size,
        })
    return reports


def load_report(filename: str) -> str | None:
    path = REPORTS_DIR / filename
    if path.exists():
        return path.read_text(encoding="utf-8")
    return None
