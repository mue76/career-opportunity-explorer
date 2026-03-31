"""데이터 저장/로드/중복 제거 유틸리티."""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def load_json(path: Path) -> list[dict]:
    """JSON 파일 로드. 파일이 없으면 빈 리스트 반환."""
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("[io] load failed (%s): %s", path, exc)
        return []


def save_json(data: list[dict], path: Path) -> None:
    """JSON 파일 저장. 상위 디렉터리가 없으면 자동 생성."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("[io] saved %d items → %s", len(data), path)


def dedup_by_link(items: list[dict]) -> list[dict]:
    """link 필드 기준 중복 제거. 순서 유지, 빈 link는 모두 유지."""
    seen: set[str] = set()
    result: list[dict] = []
    for item in items:
        link = item.get("link", "")
        if not link:
            result.append(item)  # link 없는 항목은 그대로 포함
            continue
        if link not in seen:
            seen.add(link)
            result.append(item)
    return result


def merge_and_save(new_items: list[dict], path: Path) -> list[dict]:
    """기존 파일 로드 → 신규 데이터 병합 → 중복 제거 → 저장."""
    existing = load_json(path)
    before = len(existing)
    merged = dedup_by_link(existing + new_items)
    after = len(merged)
    added = after - before
    logger.info("[io] merge: existing=%d + new=%d → dedup → total=%d (added %d)", before, len(new_items), after, added)
    save_json(merged, path)
    return merged
