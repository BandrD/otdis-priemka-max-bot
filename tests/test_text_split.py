from app.llm.text_split import split_text


def test_short():
    assert split_text("привет") == ["привет"]


def test_long():
    text = ("слово " * 900).strip()
    parts = split_text(text, limit=100)
    assert all(len(p) <= 100 for p in parts)
