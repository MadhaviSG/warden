"""Grader separation tests — no LLM."""
from pathlib import Path

from graders import grade_t4


def _t4_skeleton(tmp_path, content: str):
    work = tmp_path / "work"
    src = work / "sources"
    src.mkdir(parents=True)
    (src / "source_01_climate.md").write_text("# climate\n")
    for i in range(1, 7):
        (work / f"chapter_{i:02d}.md").write_text(content)
    (work / "INDEX.md").write_text("\n".join(f"- chapter_{i:02d}.md" for i in range(1, 7)))
    return work


def test_empty_chapters_score_low(tmp_path):
    score, _ = grade_t4(_t4_skeleton(tmp_path, "x\n"))
    assert score <= 60


def test_real_content_scores_higher(tmp_path):
    body = "Synthesis citing source_01_climate and detailed analysis.\n" * 5
    score, _ = grade_t4(_t4_skeleton(tmp_path, body))
    assert score >= 80
