"""按本地日期保存和读取两类 Markdown 记录。"""
from __future__ import annotations

import re
import json
import uuid
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent / "records"
FILES = {"今日学习": "今日学习.md", "待补齐": "待补齐.md"}
ENTRY = re.compile(r"(?m)^## (\d{4}-\d{2}-\d{2}) (\d{2}:\d{2})(?: \[([^\]\n]+)\])?[^\n]*\n")
DEFAULT_TOPICS = ("Java", "雅思", "云架构", "未分类")
TOPICS_FILE = ROOT / "分类.json"


def get_topics() -> tuple[str, ...]:
    if not TOPICS_FILE.exists():
        return DEFAULT_TOPICS
    names = json.loads(TOPICS_FILE.read_text(encoding="utf-8"))
    return tuple(dict.fromkeys(name for name in names if isinstance(name, str)
                               and name and name != "未分类")) + ("未分类",)


def add_topic(name: str) -> bool:
    name = name.strip()
    if (not name or name == "全部分类" or len(name) > 30
            or any(char in name for char in "[]\r\n") or name in get_topics()):
        return False
    ROOT.mkdir(parents=True, exist_ok=True)
    TOPICS_FILE.write_text(json.dumps([*get_topics()[:-1], name, "未分类"], ensure_ascii=False,
                                     indent=2) + "\n", encoding="utf-8")
    return True


def delete_topic(name: str) -> bool:
    topics = get_topics()
    if name == "未分类" or name not in topics:
        return False
    for path in ROOT.glob("????-??-??/*.md"):
        text = path.read_text(encoding="utf-8")
        updated = ENTRY.sub(lambda match: f"## {match[1]} {match[2]} [未分类]\n"
                            if match[3] == name else match[0], text)
        if updated != text:
            path.write_text(updated, encoding="utf-8", newline="\n")
    TOPICS_FILE.write_text(json.dumps([topic for topic in topics if topic != name],
                                     ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return True


def save(category: str, content: str, topic: str = "未分类", day: str | None = None) -> Path:
    if topic not in get_topics():
        topic = "未分类"
    now = datetime.now()
    day = day or now.date().isoformat()
    folder = ROOT / day
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / FILES[category]
    with path.open("a", encoding="utf-8", newline="\n") as file:
        stamp = now.strftime("%Y-%m-%d %H:%M") if day == now.date().isoformat() else f"{day} 12:00"
        file.write(f"## {stamp} [{topic}]\n{content}\n\n")
    return path


def save_image(category: str, image: tuple[str, bytes], topic: str = "未分类",
               day: str | None = None) -> Path:
    day = day or datetime.now().date().isoformat()
    path = save_image_file(image, day)
    try:
        return save(category, f"![截图](assets/{path.name})", topic, day)
    except Exception:
        path.unlink(missing_ok=True)
        raise


def save_image_file(image: tuple[str, bytes], day: str) -> Path:
    """只保存图片文件并返回路径，不额外创建一条知识记录。"""
    extension, data = image
    if extension not in (".png", ".bmp") or not data:
        raise ValueError("图片格式无效")
    folder = ROOT / day / "assets"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (uuid.uuid4().hex + extension)
    path.write_bytes(data)
    return path


def parse_entries(text: str) -> list[tuple[str, str, str]]:
    matches = list(ENTRY.finditer(text))
    topics = get_topics()
    return [(f"{match[1]} {match[2]}", text[match.end():
             matches[index + 1].start() if index + 1 < len(matches) else len(text)].strip(),
             match[3] if match[3] in topics else "未分类")
            for index, match in enumerate(matches)]


def set_topic(category: str, day: str, index: int, topic: str) -> bool:
    if topic not in get_topics():
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


def update_entry(category: str, day: str, index: int, content: str, original: str) -> bool:
    """修改正文，保留时间和分类，并拒绝覆盖已经变更的记录。"""
    if not isinstance(content, str) or not content.strip() or not isinstance(original, str):
        raise ValueError("记录内容不能为空")
    content = content.replace("\r\n", "\n").replace("\r", "\n").strip()
    if ENTRY.search(content):
        raise ValueError("正文不能包含记录标题格式（## 日期 时间），请调整该行")
    path = ROOT / day / FILES[category]
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8")
    matches = list(ENTRY.finditer(text))
    if index < 0 or index >= len(matches):
        return False
    match = matches[index]
    end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
    if text[match.end():end].strip() != original:
        raise ValueError("记录已发生变化，请刷新后重新编辑")
    path.write_text(text[:match.end()] + content + "\n\n" + text[end:],
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
