from __future__ import annotations

import re
from typing import List, Tuple

from sqlalchemy.orm import Session

from . import memory
from .search_bridge import run_search

TOOL_PATTERN = re.compile(r"<(web\.search|memory\.write|memory\.search|memory\.delete)>(.*?)</\\1>", re.DOTALL)


def extract_tools(text: str) -> List[Tuple[str, str]]:
    return [(match.group(1), match.group(2).strip()) for match in TOOL_PATTERN.finditer(text)]


def strip_tools(text: str) -> str:
    return TOOL_PATTERN.sub("", text).strip()


def process_tools(db: Session, text: str, allow_search: bool = True) -> str:
    blocks = extract_tools(text)
    outputs: List[str] = []
    for tool, content in blocks:
        if tool == "web.search":
            if not allow_search:
                continue
            result = run_search(content)
            memory.save_search_cache(db, content, result)
            outputs.append(f"Search for '{content}':\n{result}")
        elif tool == "memory.write":
            mem = memory.write_memory(db, content)
            outputs.append(f"Stored memory at {mem.timestamp}: {content}")
        elif tool == "memory.search":
            matches = memory.search_memory(db, content)
            if matches:
                joined = "\n".join([f"{m.timestamp}: {m.text}" for m in matches])
                outputs.append(f"Memory search results for '{content}':\n{joined}")
            else:
                outputs.append(f"Memory search results for '{content}': none found")
        elif tool == "memory.delete":
            memory.delete_memory(db, content)
            outputs.append(f"Deleted memories matching '{content}'")

    cleaned = strip_tools(text)
    if outputs:
        if cleaned:
            return "\n\n".join(outputs) + "\n\n" + cleaned
        return "\n\n".join(outputs)
    return cleaned
