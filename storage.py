"""按本地日期保存和读取两类 Markdown 记录。"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent / "records"
FILES = {"今日学习": "今日学习.md", "待补齐": "待补齐.md"}
ENTRY = re.compile(r"(?m)^## (\d{4}-\d{2}-\d{2}) (\d{2}:\d{2})(?: \[([^\]\n]+)\])?[^\n]*\n")
TOPICS = ("Java", "雅思", "云架构", "未分类")


def save(category: str, content: str, topic: str = "未分类") -> Path:
    now = datetime.now()
    folder = ROOT / now.date().isoformat()
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / FILES[category]
    with path.open("a", encoding="utf-8", newline="\n") as file:
        file.write(f"## {now:%Y-%m-%d %H:%M} [{topic}]\n{content}\n\n")
    return path


def parse_entries(text: str) -> list[tuple[str, str, str]]:
    matches = list(ENTRY.finditer(text))
    return [(f"{match[1]} {match[2]}", text[match.end():
             matches[index + 1].start() if index + 1 < len(matches) else len(text)].strip(),
             match[3] if match[3] in TOPICS else "未分类")
            for index, match in enumerate(matches)]


def set_topic(category: str, day: str, index: int, topic: str) -> bool:
    if topic not in TOPICS:
        return False
    path = ROOT / day / FILES[category]
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8")
    matches = list(ENTRY.finditer(text))
    if index < 0 or index >= len(matches):
        return False
    match = matches[index]
    header = f"## {match[1]} {match[2]} [{topic}]\n"
    path.write_text(text[:match.start()] + header + text[match.end():],
                    encoding="utf-8", newline="\n")
    return True


def delete_entry(category: str, day: str, index: int) -> bool:
    """按日期和卡片顺序删除一条记录，避免时间相同的卡片删错。"""
    path = ROOT / day / FILES[category]
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8")
    matches = list(ENTRY.finditer(text))
    if index < 0 or index >= len(matches):
        return False
    start = matches[index].start()
    end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
    updated = text[:start] + text[end:]
    if not updated.strip():
        path.unlink()
        try:
            path.parent.rmdir()
        except OSError:
            pass
    else:
        path.write_text(updated, encoding="utf-8", newline="\n")
    return True


def load_days() -> dict[str, dict[str, list[tuple[str, str, str]]]]:
    result = {}
    if not ROOT.exists():
        return result
    for folder in ROOT.iterdir():
        if not folder.is_dir() or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", folder.name):
            continue
        categories = {}
        for category, filename in FILES.items():
            path = folder / filename
            categories[category] = parse_entries(path.read_text(encoding="utf-8")) if path.exists() else []
        if any(categories.values()):
            result[folder.name] = categories
    return dict(sorted(result.items(), reverse=True))
