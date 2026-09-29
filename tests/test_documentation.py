"""Prevent navigation regressions when reorganizing the public documentation."""
from scripts.check_documentation import ROOT, anchors, check_links, markdown_files


def test_public_markdown_links_and_heading_anchors_resolve():
    assert check_links(ROOT) == []


def test_link_checker_detects_broken_targets_and_anchors_but_ignores_examples(tmp_path):
    (tmp_path / "README.md").write_text("# Guide\n[ok](docs/start.md#first-step)\n[bad](missing.md)\n[anchor](docs/start.md#absent)\n```md\n[sample](not-a-real-file.md)\n```\n")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/start.md").write_text("# First step\n[external](https://example.org/unknown)\n")
    errors = check_links(tmp_path)
    assert len(errors) == 2
    assert any("missing.md" in error for error in errors)
    assert any("#absent" in error for error in errors)


def test_inventory_excludes_private_and_independent_projects(tmp_path):
    for directory in ["docs", "storyboard", "reckonings", "career-narrative"]:
        (tmp_path / directory).mkdir()
        (tmp_path / directory / "guide.md").write_text("# Guide\n")
    assert [p.relative_to(tmp_path).as_posix() for p in markdown_files(tmp_path)] == ["docs/guide.md"]


def test_duplicate_heading_anchors_match_github_convention():
    assert anchors("# Evidence & inference\n## Same\n## Same\n") == {"evidence--inference", "same", "same-1"}


def test_json_inventory_identifies_exact_public_document_bytes(tmp_path):
    import hashlib
    import json

    from scripts.check_documentation import inventory

    guide = '# Questions\n\nKeep uncertainty visible: café.\n'
    (tmp_path / 'README.md').write_text(guide, encoding='utf-8')
    (tmp_path / 'career-narrative').mkdir()
    (tmp_path / 'career-narrative/private.md').write_text('# Separate project\n')
    receipt = json.loads(inventory(tmp_path, json_output=True))
    assert receipt['status'] == 'candidate_checkpoint'
    assert receipt['file_count'] == 1
    assert receipt['files'] == [{
        'path': 'README.md',
        'line_count': 3,
        'sha256': hashlib.sha256(guide.encode('utf-8')).hexdigest(),
    }]
    (tmp_path / 'README.md').write_text(guide + 'An edit.\n', encoding='utf-8')
    updated = json.loads(inventory(tmp_path, json_output=True))
    assert updated['files'][0]['sha256'] != receipt['files'][0]['sha256']
