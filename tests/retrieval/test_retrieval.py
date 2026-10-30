"""Chunking and BM25 on a small hand-made tree."""

import pytest

from retrieval.chunker import chunk_markup, chunk_python, chunk_tree
from retrieval.index import RepoIndex, format_hit, format_starting_material, load_or_build, tokenize

SOURCE = '''"""Module doc about colours."""
LIMIT = 100
NAME = "x"

def top(a):
    """Top function doc."""
    return a

class Thing:
    """Thing doc."""
    size = 1

    def method(self):
        return self.size
'''


def test_tokenizer():
    assert tokenize("is_eager") == ["is", "eager", "is_eager"]
    assert tokenize("MultiCommand") == ["multi", "command", "multicommand"]
    assert tokenize("HTTPServer x2") == ["http", "server", "httpserver", "x", "2", "x2"]


def test_python_chunks_have_exact_line_ranges():
    code, docs = chunk_python(SOURCE, "p/a.py")
    got = {c.symbol: (c.line_start, c.line_end) for c in code}
    assert got == {"<module>": (2, 3), "top": (5, 7), "Thing": (9, 12), "Thing.method": (13, 14)}
    assert {d.symbol for d in docs} == {"p/a.py", "top", "Thing"}
    assert chunk_python("def f(:", "x.py") == ([], [])


def test_markup_sections():
    rst = "Title\n=====\n\nintro\n\nPart\n----\ntext\n"
    assert [(c.symbol, c.line_start) for c in chunk_markup(rst, "d.rst")] == [("Title", 1), ("Part", 6)]
    assert [c.symbol for c in chunk_markup("# A\nx\n## B\ny\n", "d.md")] == ["# A", "## B"]


@pytest.fixture
def tree(tmp_path):
    pkg = tmp_path / "src" / "p"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text(SOURCE)
    (pkg / "other.py").write_text("def unrelated():\n    return 'zebra'\n")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "guide.rst").write_text("Colours\n=======\nThe strict default is documented here.\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_a.py").write_text("def test_secret_word():\n    pass\n")
    return tmp_path


def test_code_and_docs_are_separate_and_tests_excluded(tree):
    index = RepoIndex(chunk_tree(tree, "p", "src"))
    assert all(c.kind == "code" for c in index.code.chunks) and all(c.kind == "doc" for c in index.docs.chunks)
    assert not any("secret_word" in c.text for c in index.code.chunks + index.docs.chunks), "tests are not in the search index"
    hit = index.code.search("zebra", 3)[0]
    assert hit.chunk.symbol == "unrelated" and hit.chunk.path == "src/p/other.py"
    assert index.docs.search("strict default", 3)[0].chunk.path == "docs/guide.rst"


def test_starting_material_is_deterministic(tree):
    index = RepoIndex(chunk_tree(tree, "p", "src"))
    a = format_starting_material(*index.starting_material("zebra strict", 5, 3))
    b = format_starting_material(*RepoIndex(chunk_tree(tree, "p", "src")).starting_material("zebra strict", 5, 3))
    assert a == b and "## Code" in a and "## Documentation" in a


def test_format_hit_shows_real_line_numbers(tree):
    index = RepoIndex(chunk_tree(tree, "p", "src"))
    text = format_hit(index.code.search("zebra")[0])
    assert "src/p/other.py:1-2" in text and "    1  def unrelated" in text


def test_index_cache(tree, tmp_path):
    cache = tmp_path / "cache" / "i.pkl"
    first = load_or_build(tree, "p", "src", cache)
    assert cache.exists() and len(first.code.chunks) > 0
    (tree / "src" / "p" / "other.py").write_text("def changed():\n    pass\n")
    again = load_or_build(tree, "p", "src", cache)
    assert any(c.symbol == "unrelated" for c in again.code.chunks), "a frozen tree's index is reused from the cache"
