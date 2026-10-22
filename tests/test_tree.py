from pathlib import Path

from app.dialog.tree import load_dialog_tree

ROOT = Path(__file__).resolve().parents[1]
TREE = load_dialog_tree(ROOT / "assets" / "dialog_tree.json")


def test_root_and_size():
    assert TREE.root_id == "Q0"
    assert len(TREE.nodes) >= 40
    view = TREE.view("Q0")
    assert view.keyboard_children
    assert not view.show_back


def test_back_chain():
    assert TREE.parent_of("rules_who") == "rules"
    assert TREE.parent_of("rules") == "Q0"


def test_docs_leaf():
    view = TREE.view("priemka_docs")
    assert "Паспорт" in view.body
    assert not view.keyboard_children


def test_link_leaf():
    view = TREE.view("exam_criteria")
    assert "otdis.ru" in view.body


def test_gigachat_leaf():
    view = TREE.view("fallback_gigachat")
    assert view.await_gigachat


def test_needs_content():
    view = TREE.view("enroll_avg_score")
    assert "faq-abitur" in view.body


def test_all_targets_exist():
    for node in TREE.nodes.values():
        for ch in node.children:
            assert ch.target in TREE.nodes, ch.target
