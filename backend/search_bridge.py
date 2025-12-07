import subprocess
from pathlib import Path
from typing import List

BASE_DIR = Path(__file__).resolve().parent.parent
AGENT_SCRIPT = BASE_DIR / "agent" / "main.py"


def run_search(query: str) -> str:
    if not AGENT_SCRIPT.exists():
        return "Search agent missing."
    result = subprocess.run(
        ["python", str(AGENT_SCRIPT), query], capture_output=True, text=True, check=False
    )
    return result.stdout.strip() or result.stderr.strip()


def parse_tool_commands(text: str) -> List[str]:
    commands = []
    start_tag = "<web.search>"
    end_tag = "</web.search>"
    remaining = text
    while start_tag in remaining and end_tag in remaining:
        start = remaining.index(start_tag) + len(start_tag)
        end = remaining.index(end_tag)
        commands.append(remaining[start:end].strip())
        remaining = remaining[end + len(end_tag) :]
    return commands
