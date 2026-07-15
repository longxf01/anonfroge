from __future__ import annotations

from dataclasses import dataclass
import re


REEL_PATTERN = re.compile(r"^第[\d一二三四五六七八九十百千万零〇两]+[卷部集册].*$")
CHAPTER_PATTERN = re.compile(r"^(第[\d一二三四五六七八九十百千万零〇两]+[章节回].*|Chapter\s+\d+.*)$", re.IGNORECASE)


@dataclass(frozen=True)
class ParsedNovelChapter:
    """从原始小说文本中解析出的章节。"""

    chapter_index: int
    reel: str
    chapter: str
    chapter_data: str


def parse_novel_chapters(raw_text: str) -> list[ParsedNovelChapter]:
    """按常见中文卷、章节标题拆分小说正文。"""
    lines = [_normalize_line(line) for line in raw_text.splitlines()]
    lines = [line for line in lines if line]
    if not lines:
        return []

    chapters: list[ParsedNovelChapter] = []
    current_reel = ""
    current_chapter = ""
    current_lines: list[str] = []

    def flush_current() -> None:
        nonlocal current_chapter, current_lines
        if not current_chapter:
            return
        chapter_data = "\n".join(current_lines).strip()
        chapters.append(
            ParsedNovelChapter(
                chapter_index=len(chapters) + 1,
                reel=current_reel,
                chapter=current_chapter,
                chapter_data=chapter_data,
            )
        )
        current_chapter = ""
        current_lines = []

    preface_lines: list[str] = []
    for line in lines:
        if _looks_like_reel(line):
            flush_current()
            current_reel = line
            continue
        if _looks_like_chapter(line):
            flush_current()
            current_chapter = line
            current_lines = []
            continue
        if current_chapter:
            current_lines.append(line)
        else:
            preface_lines.append(line)

    flush_current()
    if chapters:
        return chapters

    return [
        ParsedNovelChapter(
            chapter_index=1,
            reel="",
            chapter="正文",
            chapter_data="\n".join(preface_lines).strip(),
        )
    ]


def _normalize_line(line: str) -> str:
    """压缩标题和正文行两侧空白。"""
    return re.sub(r"\s+", " ", line.strip())


def _looks_like_reel(line: str) -> bool:
    """判断是否为卷次标题。"""
    return len(line) <= 80 and REEL_PATTERN.match(line) is not None


def _looks_like_chapter(line: str) -> bool:
    """判断是否为章节标题。"""
    return len(line) <= 120 and CHAPTER_PATTERN.match(line) is not None
