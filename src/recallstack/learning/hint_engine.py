"""Progressive hint engine derived from source_references."""

from __future__ import annotations

from pathlib import Path
from typing import Any


class HintEngine:
    """Levels 0-5; no skipping without recording intermediate usage."""

    MAX_LEVEL = 5

    def next_hint(
        self,
        *,
        current_level: int,
        source_references: list[dict[str, Any]],
        expected_answer_outline: str = "",
        code_lookup: dict[str, str] | None = None,
        reveal_answer: bool = False,
    ) -> dict[str, Any]:
        if reveal_answer:
            content = expected_answer_outline.strip() or "No outline available."
            return {
                "level": self.MAX_LEVEL,
                "content": f"Full explanation outline:\n{content}",
                "revealed_answer": True,
            }

        level = max(0, min(int(current_level), self.MAX_LEVEL - 1)) + 1
        refs = source_references or []
        modules = sorted({self._module(r.get("path", "")) for r in refs if r.get("path")})
        files = sorted({str(r.get("path")) for r in refs if r.get("path")})
        symbols = sorted({str(r.get("symbol")) for r in refs if r.get("symbol")})

        if level == 1:
            content = (
                "Related modules: " + ", ".join(modules)
                if modules
                else "Think about the top-level package boundaries involved."
            )
        elif level == 2:
            content = (
                "Related files: " + ", ".join(files)
                if files
                else "Open the files that implement this concept's responsibility."
            )
        elif level == 3:
            content = (
                "Key symbols: " + ", ".join(symbols)
                if symbols
                else "Identify the main functions/classes on the call path."
            )
        elif level == 4:
            content = self._partial_chain(refs, code_lookup or {})
        else:
            outline = expected_answer_outline.strip() or "Cover responsibilities, key calls, and tradeoffs."
            content = f"Answer outline (not a full write-up):\n{outline}"

        return {"level": level, "content": content, "revealed_answer": False}

    def validate_progression(self, hints_used: list[dict[str, Any]]) -> bool:
        """Hints must be non-decreasing by level without skips greater than +1 from previous max."""
        if not hints_used:
            return True
        levels = []
        for h in hints_used:
            try:
                levels.append(int(h.get("level", 0)))
            except (TypeError, ValueError):
                return False
        prev = 0
        for lv in levels:
            if lv < 1 or lv > self.MAX_LEVEL:
                return False
            if lv > prev + 1:
                return False
            prev = max(prev, lv)
        return True

    def _module(self, path: str) -> str:
        parts = Path(str(path).replace("\\", "/")).parts
        return parts[0] if parts else "root"

    def _partial_chain(self, refs: list[dict[str, Any]], code_lookup: dict[str, str]) -> str:
        lines: list[str] = ["Partial call chain / key ranges:"]
        for ref in refs[:4]:
            path = str(ref.get("path", ""))
            start = ref.get("start_line")
            end = ref.get("end_line")
            symbol = ref.get("symbol") or ""
            snippet = ""
            if path in code_lookup and start:
                text = code_lookup[path].splitlines()
                s = max(1, int(start)) - 1
                e = min(len(text), int(end or start) )
                # only show a short window
                e = min(e, s + 8)
                snippet = "\n".join(text[s:e])
            loc = f"{path}"
            if start:
                loc += f":{start}"
                if end:
                    loc += f"-{end}"
            if symbol:
                loc += f" ({symbol})"
            lines.append(f"- {loc}")
            if snippet:
                lines.append("```")
                lines.append(snippet)
                lines.append("```")
        if len(lines) == 1:
            lines.append("- Inspect imports and entrypoints connected to this concept.")
        return "\n".join(lines)
