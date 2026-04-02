from __future__ import annotations

import re
from dataclasses import dataclass

from .constants import ULTRAPLAN_KEYWORD


@dataclass(frozen=True, slots=True)
class TriggerPosition:
    word: str
    start: int
    end: int


class UltraplanTrigger:
    _open_to_close = {
        "`": "`",
        '"': '"',
        "<": ">",
        "{": "}",
        "[": "]",
        "(": ")",
        "'": "'",
    }

    def find_positions(self, text: str) -> list[TriggerPosition]:
        if not re.search(ULTRAPLAN_KEYWORD, text, re.IGNORECASE):
            return []
        if text.startswith("/"):
            return []

        quoted_ranges: list[tuple[int, int]] = []
        open_quote: str | None = None
        open_at = 0

        def is_word(ch: str | None) -> bool:
            return bool(ch) and bool(re.match(r"[\w]", ch))

        for idx, ch in enumerate(text):
            if open_quote:
                if ch != self._open_to_close[open_quote]:
                    continue
                if open_quote == "'" and idx + 1 < len(text) and is_word(text[idx + 1]):
                    continue
                quoted_ranges.append((open_at, idx + 1))
                open_quote = None
                continue

            if ch == "<" and idx + 1 < len(text) and re.match(r"[a-zA-Z/]", text[idx + 1]):
                open_quote = ch
                open_at = idx
            elif ch == "'" and not is_word(text[idx - 1] if idx > 0 else None):
                open_quote = ch
                open_at = idx
            elif ch in self._open_to_close and ch not in {"<", "'"}:
                open_quote = ch
                open_at = idx

        positions: list[TriggerPosition] = []
        for match in re.finditer(rf"\b{ULTRAPLAN_KEYWORD}\b", text, re.IGNORECASE):
            start, end = match.span()
            if any(start >= left and start < right for left, right in quoted_ranges):
                continue
            before = text[start - 1] if start > 0 else None
            after = text[end] if end < len(text) else None
            after2 = text[end + 1] if end + 1 < len(text) else None
            if before in {"/", "\\", "-"}:
                continue
            if after in {"/", "\\", "-", "?"}:
                continue
            if after == "." and after2 and re.match(r"[\w]", after2):
                continue
            positions.append(TriggerPosition(match.group(0), start, end))
        return positions

    def has_keyword(self, text: str) -> bool:
        return bool(self.find_positions(text))

    def replace_keyword(self, text: str) -> str:
        positions = self.find_positions(text)
        if not positions:
            return text
        first = positions[0]
        before = text[: first.start]
        after = text[first.end :]
        if not (before + after).strip():
            return ""
        return before + first.word[len("ultra") :] + after
