"""Deterministic graders for non-invoice tasks."""
import hashlib
import json
import re
from pathlib import Path

from llm import call_llm, parse_json, _require_env

CAT_DIRS = ("docs", "data", "archive")
CONTENT_CAP = 2048

T4_CRITERIA = [
    "six_chapters_exist",
    "chapters_have_content",
    "chapters_cite_sources",
    "index_exists",
    "index_links_chapters",
]

T4_GRADER = (
    "Grade a research dossier task. For each criterion return satisfied (bool) and note (str).\n"
    "CRITERIA:\n{criteria}\n\nFILE CONTENTS:\n{contents}\n\n"
    'Return JSON {{"criteria": {{"name": {{"satisfied": bool, "note": str}}, ...}}}}.'
)

EXPLORATORY_GRADER = (
    "Assess whether this work directory satisfies the goal.\nGOAL: {spec}\n\nFILE CONTENTS:\n{contents}\n\n"
    'Return JSON {{"criteria": {{"goal_satisfied": {{"satisfied": bool, "note": str}}}}}}.'
)


def _hash(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _read_bounded(work: Path, cap: int = CONTENT_CAP) -> dict:
    out = {}
    total = 0
    for p in sorted(work.rglob("*")):
        if not p.is_file() or p.name.startswith("."):
            continue
        rel = str(p.relative_to(work))
        if total >= cap * 20:
            out[rel] = "[truncated listing]"
            continue
        try:
            text = p.read_text()[:cap]
        except (OSError, UnicodeDecodeError):
            text = "[unreadable]"
        out[rel] = text
        total += len(text)
    return out


def _score_from_criteria(criteria: dict, keys: list[str]) -> tuple[int, list[str]]:
    if not keys:
        return 0, ["no criteria"]
    met = sum(1 for k in keys if criteria.get(k, {}).get("satisfied"))
    viol = [f"{k}: {criteria.get(k, {}).get('note', 'fail')}" for k in keys if not criteria.get(k, {}).get("satisfied")]
    return int(100 * met / len(keys)), viol


def grade_t3(work: Path) -> tuple[int, list[str]]:
    """Score T3 messy-drive cleanup 0-100 (pure Python)."""
    v, score = [], 0
    w = Path(work)

    junk = list(w.glob("junk/*.tmp"))
    if not junk:
        score += 25
    else:
        v.append(f"junk/*.tmp present: {[p.name for p in junk]}")

    manifest_p = w / ".t3_manifest.json"
    if not manifest_p.exists():
        v.append(".t3_manifest.json missing")
        return score, v
    manifest = json.loads(manifest_p.read_text())
    originals = manifest.get("originals", [])

    placed = []
    for d in CAT_DIRS:
        dp = w / d
        if dp.is_dir():
            placed.extend(p for p in dp.rglob("*") if p.is_file())

    hashes = [_hash(p) for p in placed]
    if len(hashes) == len(set(hashes)):
        score += 25
    else:
        v.append("duplicate content hashes in organized files")

    orig_names = {o["name"] for o in originals}
    orig_hashes = {o["name"]: o["sha256"] for o in originals}
    found = {}
    for p in placed:
        h = _hash(p)
        for name, oh in orig_hashes.items():
            if h == oh and name not in found:
                found[name] = str(p.relative_to(w))
                break

    if set(found) == orig_names and len(found) == len(orig_names):
        score += 25
    else:
        missing = sorted(orig_names - set(found))
        if missing:
            v.append(f"originals not placed once: {missing}")
        dupes = [n for n in found if list(found.values()).count(found[n]) > 1]
        if dupes:
            v.append(f"duplicate placements: {dupes}")

    md = w / "MANIFEST.md"
    if md.exists():
        text = md.read_text()
        listed = all(name in text for name in orig_names)
        if listed and len(orig_names) > 0:
            score += 25
        else:
            v.append("MANIFEST.md missing some originals")
    else:
        v.append("MANIFEST.md missing")

    return score, v


def grade_t4(work: Path) -> tuple[int, list[str]]:
    """Score T4 research dossier 0-100 from file contents (pure Python)."""
    w = Path(work)
    v, score = [], 0
    chapters = sorted(w.glob("chapter_*.md"))
    if len(chapters) >= 6:
        score += 20
    else:
        v.append(f"expected 6 chapters, found {len(chapters)}")

    nonempty = [c for c in chapters if c.stat().st_size >= 80]
    if len(nonempty) >= 6:
        score += 20
    else:
        v.append(f"short/empty chapters: {[c.name for c in chapters if c.stat().st_size < 80]}")

    sources = list((w / "sources").glob("*.md")) if (w / "sources").is_dir() else []
    cited = 0
    for ch in chapters:
        text = ch.read_text() if ch.exists() else ""
        if any(s.stem.split("_", 2)[-1] in text or s.name in text for s in sources):
            cited += 1
    if cited >= 4:
        score += 20
    else:
        v.append(f"only {cited} chapters cite a source")

    index = w / "INDEX.md"
    if index.exists() and index.stat().st_size >= 40:
        score += 20
    else:
        v.append("INDEX.md missing or too short")

    if index.exists():
        idx = index.read_text()
        linked = sum(1 for c in chapters if c.name in idx)
        if linked >= 6:
            score += 20
        else:
            v.append(f"INDEX links {linked}/6 chapters")
    else:
        v.append("INDEX.md missing for link check")

    return score, v


def grade_exploratory(work: Path, spec: str) -> tuple[int, list[str]]:
    contents = _read_bounded(Path(work))
    prompt = EXPLORATORY_GRADER.format(spec=spec, contents=json.dumps(contents, indent=2)[:12000])
    result = parse_json(call_llm([{"role": "user", "content": prompt}], model=_require_env("JUDGE_MODEL")))
    criteria = result.get("criteria", {})
    return _score_from_criteria(criteria, ["goal_satisfied"])
