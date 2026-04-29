from __future__ import annotations

import json
from typing import Any, Dict, List


def format_as_json(rows: List[Dict[str, Any]], indent: int = 2) -> str:
    return json.dumps(rows, ensure_ascii=False, indent=indent)


def format_as_table(rows: List[Dict[str, Any]]) -> str:
    if not rows:
        return "（无结果）"

    try:
        from tabulate import tabulate

        headers = list(rows[0].keys())
        table_data = [[row.get(h, "") for h in headers] for row in rows]
        return tabulate(table_data, headers=headers, tablefmt="simple")
    except ImportError:
        headers = list(rows[0].keys())
        lines = ["\t".join(str(h) for h in headers)]
        lines.append("\t".join("-" * min(len(str(h)), 12) for h in headers))
        for row in rows:
            lines.append("\t".join(str(row.get(h, "")) for h in headers))
        return "\n".join(lines)
