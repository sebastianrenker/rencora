"""Harmloser readline-Ersatz. Das installierte pyreadline nutzt das unter
Python 3.10+ entfernte collections.Callable und laesst sonst pytest scheitern.
Nur fuer Tests: PYTHONPATH=tests/_shim voranstellen."""

def parse_and_bind(*a, **k): pass
def get_line_buffer(): return ""
def set_completer(*a, **k): pass
def get_completer(): return None
def read_history_file(*a, **k): pass
def write_history_file(*a, **k): pass
def set_history_length(*a, **k): pass
def get_history_length(): return 0
def clear_history(): pass
def add_history(*a, **k): pass
