"""Deterministic graders for non-invoice tasks."""
import hashlib
import json
import re
from pathlib import Path

CAT_DIRS = ("docs", "data", "archive")


def _hash(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


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
