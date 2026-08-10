"""Tests fuer die AST-gestuetzte Sandbox-Pruefung des generierten Desktop-Codes."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from actions.desktop import _is_code_safe


def test_allows_legitimate_file_actions():
    assert _is_code_safe("p = Path.home()\nfor f in p.iterdir():\n    print(f.name)")
    assert _is_code_safe('Path("note.txt").write_text("hallo")')
    assert _is_code_safe('shutil.copy2("a.txt", "b.txt")')


def test_ast_blocks_what_substring_filter_misses():
    # Diese Konstrukte enthalten keinen Token der Substring-Denylist,
    # muessen aber strukturell (AST) blockiert werden.
    assert not _is_code_safe("sys.exit()")
    assert not _is_code_safe("x = os.getcwd()")
    assert not _is_code_safe("obj.spawn(1)")


def test_blocks_imports_and_dunder_and_exec():
    assert not _is_code_safe("import os")
    assert not _is_code_safe("from os import system")
    assert not _is_code_safe("x.__class__")
    assert not _is_code_safe('eval("1+1")')
    assert not _is_code_safe('__import__("os")')


def test_unparseable_code_is_unsafe():
    assert not _is_code_safe("def (:")
