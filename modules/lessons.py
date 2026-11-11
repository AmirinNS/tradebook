"""Lesson loader and markdown parser for Tradebook educational content."""

from pathlib import Path

import markdown
import yaml

LESSONS_DIR = Path(__file__).resolve().parent.parent / "content" / "lessons"

_LESSONS_BY_SLUG: dict[str, dict] = {}
_LESSONS_ORDERED: list[dict] = []


def _parse_lesson_file(path: Path) -> dict:
    """Parse front-matter and render markdown to HTML without raw HTML extensions."""
    raw = path.read_text(encoding="utf-8")
    if raw.startswith("---"):
        parts = raw.split("---", 2)
        if len(parts) >= 3:
            meta = yaml.safe_load(parts[1]) or {}
            body = parts[2].strip()
        else:
            meta = {}
            body = raw
    else:
        meta = {}
        body = raw

    html = markdown.markdown(body, extensions=["fenced_code", "tables"])
    return {
        "slug": str(meta.get("slug", path.stem)),
        "title": str(meta.get("title", path.stem.replace("-", " ").title())),
        "order": int(meta.get("order", 999)),
        "summary": str(meta.get("summary", "")),
        "reading_time": int(meta.get("reading_time", 5)),
        "related_filters": list(meta.get("related_filters", [])),
        "html": html,
        "raw_body": body,
    }


def load_lessons(content_dir: Path | None = None) -> list[dict]:
    """Load all markdown lessons from directory, sorted by order."""
    global _LESSONS_BY_SLUG, _LESSONS_ORDERED
    dir_path = content_dir or LESSONS_DIR
    lessons = []
    if dir_path.is_dir():
        for path in sorted(dir_path.glob("*.md")):
            lesson = _parse_lesson_file(path)
            lessons.append(lesson)
    lessons.sort(key=lambda x: (x["order"], x["title"]))
    _LESSONS_ORDERED = lessons
    _LESSONS_BY_SLUG = {lesson["slug"]: lesson for lesson in lessons}
    return _LESSONS_ORDERED


def list_lessons() -> list[dict]:
    """Return all available lessons sorted by order."""
    if not _LESSONS_ORDERED:
        load_lessons()
    return list(_LESSONS_ORDERED)


def get_lesson(slug: str) -> dict | None:
    """Return a lesson by slug, or None if not found."""
    if not _LESSONS_BY_SLUG:
        load_lessons()
    return _LESSONS_BY_SLUG.get(slug)


# Load lessons at module import
load_lessons()
