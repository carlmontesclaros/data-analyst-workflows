"""Claude Code PreToolUse hook: refuse edits that make the tests weaker.

A failing test means the app is wrong (or the test is), not that the test should go quiet. This hook runs before every
Edit, Write and MultiEdit (.claude/settings.json) and compares the file as it is now with the file as it would be after the
edit. It blocks (exit 2, reason on stderr for the agent) when the edit would, in a test file (test_*.py, *_test.py,
conftest.py):
  - add a skip / skipif / xfail mark (pytest.mark.*, or unittest's skip decorators)
  - add a skip call: pytest.skip/xfail/importorskip(...), the same names imported from pytest and called bare,
    self.skipTest(...), raise unittest.SkipTest, raise pytest.skip.Exception / pytest.xfail.Exception
  - add entries to collect_ignore / collect_ignore_glob
  - leave fewer test functions, fewer assert statements, or fewer @pytest.mark.parametrize cases
  - add an assert that is always true (assert True, assert 1, assert not False, assert 1 == 1, assert (x, 'why'))
or, in pytest's own settings (pyproject.toml, pytest.ini, setup.cfg, tox.ini) or a CI workflow (.github/workflows/*.yml),
add an option that deselects tests (-k, --deselect, --ignore, --ignore-glob, -m "not ...") to addopts or a pytest command.

The no-display guard the screen tests use (except tk.TclError -> if 'display' not in str(e): raise -> pytest.skip(f"no
display: {e}")) is the one skip that is allowed: it only skips on a machine with no screen at all.

Everything else (other files, new tests, extra asserts, unreadable hook input) is let through. A human who really means to
remove or skip a test edits the file by hand, or turns the hook off for a while (see the root README).

Standard library only; run with python3 -I so nothing in the working folder can be imported in its place.
"""

import ast
import io
import json
import operator
import os
import re
import sys
import tokenize

TEST_FILE = re.compile(r'^(test_.*|.*_test|conftest)\.py$')
PYTEST_CONFIG = {'pyproject.toml', 'pytest.ini', 'setup.cfg', 'tox.ini'}
WORKFLOW = re.compile(r'(^|/)\.github/workflows/[^/]+\.ya?ml$')

# skip marks: @pytest.mark.skip / skipif / xfail (also via `from pytest import mark` or pytestmark = ...), and
# unittest's @unittest.skip / skipIf / skipUnless / expectedFailure
SKIP_MARK = re.compile(r'\bmark\s*\.\s*(skip|skipif|xfail)\b|\bunittest\s*\.\s*(skip|skipIf|skipUnless|expectedFailure)\b'
                       r'|^\s*@\s*(skip|skipIf|skipUnless|expectedFailure)\b', re.MULTILINE)
SKIP_CALL = re.compile(r'\bpytest\s*\.\s*(skip|xfail|importorskip)\s*\(|\.\s*skipTest\s*\(|\bSkipTest\b'
                       r'|\b(skip|xfail)\s*\.\s*Exception\b')
SKIP_NAMES = {'skip', 'xfail', 'importorskip'}
FROM_PYTEST = re.compile(r'^\s*from\s+pytest\s+import\s+(?:\(([^)]*)\)|([^\n(]+))', re.MULTILINE)
COLLECT_IGNORE = re.compile(r'\bcollect_ignore(_glob)?\b')
TEST_FUNC = re.compile(r'^\s*(async\s+)?def\s+test\w*\s*\(', re.MULTILINE)
ASSERT = re.compile(r'^\s*assert\b', re.MULTILINE)

# the allowed no-display guard: the skip says "no display" and the lines just above it catch a TclError and re-raise
# anything that isn't about the display. The catch and the re-raise are judged on code (comments can't fake them); only
# the 'display' word is read from the raw text, since it is a string.
DISPLAY_SKIP = re.compile(r'''\bpytest\s*\.\s*skip\s*\(\s*f?["']no display''')
DISPLAY_CHECK = re.compile(r'''["']display["']\s+not\s+in\s+str\(''')
CODE_CHECK = re.compile(r'\bexcept\b[^\n]*\bTclError\b[\s\S]*\bnot\s+in\s+str\([\s\S]*^\s*raise\b', re.MULTILINE)
LOOK_BACK = 4   # lines

# options that stop pytest collecting or running some tests
DESELECT = re.compile(r'''(?<![\w-])(--ignore-glob|--ignore|--deselect|-k|-m\s*=?\s*["']?\s*not\b)(?=[\s=\"']|$)''')


# token types whose text is not code: strings (incl. f-string pieces, 3.12+) and comments
_NOT_CODE = {tokenize.STRING, tokenize.COMMENT} | {getattr(tokenize, n) for n in ('FSTRING_START', 'FSTRING_MIDDLE',
                                                                                   'FSTRING_END') if hasattr(tokenize, n)}


def code_only(text):
    """text with every string and comment blanked out (newlines kept, so line numbers still match), or None when it
    doesn't tokenize (a half-finished edit)."""
    out = [list(line) for line in io.StringIO(text).readlines()]   # the same lines tokenize reads (split on \n only)
    try:
        for tok in tokenize.generate_tokens(io.StringIO(text).readline):
            if tok.type not in _NOT_CODE:
                continue
            (r1, c1), (r2, c2) = tok.start, tok.end
            for r in range(r1, r2 + 1):
                row = out[r - 1]
                for c in range(c1 if r == r1 else 0, c2 if r == r2 else len(row)):
                    if row[c] != '\n':
                        row[c] = ' '
    except (tokenize.TokenError, SyntaxError):
        return None
    return ''.join(''.join(row) for row in out)


def file_kind(path):
    """'test', 'config' (pytest settings or a CI workflow) or None (not guarded)."""
    path = (path or '').replace('\\', '/')
    name = os.path.basename(path)
    if TEST_FILE.match(name):
        return 'test'
    if name in PYTEST_CONFIG or WORKFLOW.search(path):
        return 'config'
    return None


def is_test_file(path):
    return file_kind(path) == 'test'


# --- test files ----------------------------------------------------------------------------------------------------

def _is_display_guard(lines, code_lines, i):
    if not DISPLAY_SKIP.search(lines[i]):
        return False
    start = max(0, i - LOOK_BACK)
    return (bool(DISPLAY_CHECK.search('\n'.join(lines[start:i])))
            and bool(CODE_CHECK.search('\n'.join(code_lines[start:i]))))


def _pytest_aliases(code):
    """Local names bound to pytest.skip / xfail / importorskip by `from pytest import ...`."""
    names = set()
    for m in FROM_PYTEST.finditer(code):
        for part in (m.group(1) or m.group(2)).replace('\n', ' ').split(','):
            bits = part.split()
            if bits and bits[0] in SKIP_NAMES:
                names.add(bits[2] if len(bits) == 3 and bits[1] == 'as' else bits[0])
    return names


def count_skip_calls(text, code):
    """Skip calls and raises in code, not counting the allowed no-display guard (judged with text, the same lines with
    their strings and comments still in)."""
    lines, code_lines = text.split('\n'), code.split('\n')
    aliases = _pytest_aliases(code)
    bare = re.compile(r'(?<![\w.])(' + '|'.join(sorted(map(re.escape, aliases))) + r')\s*\(') if aliases else None
    total = 0
    for i, line in enumerate(code_lines):
        if _is_display_guard(lines, code_lines, i):
            continue
        total += len(SKIP_CALL.findall(line)) + (len(bare.findall(line)) if bare else 0)
    return total


_COMPARE = {ast.Eq: operator.eq, ast.NotEq: operator.ne, ast.Lt: operator.lt, ast.LtE: operator.le, ast.Gt: operator.gt,
            ast.GtE: operator.ge, ast.Is: operator.is_, ast.IsNot: operator.is_not, ast.In: lambda a, b: a in b,
            ast.NotIn: lambda a, b: a not in b}


class _NotConstant(Exception):
    pass


def _value(node):
    """The value of an expression built only from literals, else _NotConstant."""
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, (ast.Tuple, ast.List)):
        return tuple(_value(e) for e in node.elts)
    if isinstance(node, ast.UnaryOp):
        v = _value(node.operand)
        ops = {ast.Not: operator.not_, ast.USub: operator.neg, ast.UAdd: operator.pos, ast.Invert: operator.invert}
        try:
            return ops[type(node.op)](v)
        except (KeyError, TypeError) as e:
            raise _NotConstant from e
    if isinstance(node, ast.BoolOp):
        values = [_value(v) for v in node.values]
        return all(values) if isinstance(node.op, ast.And) else any(values)
    if isinstance(node, ast.Compare):
        left = _value(node.left)
        for op, right_node in zip(node.ops, node.comparators, strict=True):
            right = _value(right_node)
            try:
                if not _COMPARE[type(op)](left, right):
                    return False
            except (KeyError, TypeError) as e:
                raise _NotConstant from e
            left = right
        return True
    raise _NotConstant


def _always_true(test):
    # assert (x, 'message') is a non-empty tuple: always true, whatever x is
    if isinstance(test, ast.Tuple) and test.elts:
        return True
    try:
        return bool(_value(test))
    except _NotConstant:
        return False


def _is_parametrize(dec):
    func = dec.func if isinstance(dec, ast.Call) else None
    return isinstance(func, ast.Attribute) and func.attr == 'parametrize'


def _tree_counts(text):
    """Counts that need the parsed file, or None when it doesn't parse."""
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return None
    cases = trivial = ignored = 0
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            for dec in node.decorator_list:
                if _is_parametrize(dec):
                    values = dec.args[1] if len(dec.args) > 1 else next(
                        (k.value for k in dec.keywords if k.arg == 'argvalues'), None)
                    if isinstance(values, (ast.List, ast.Tuple, ast.Set)):
                        cases += len(values.elts)
        elif isinstance(node, ast.Assert) and _always_true(node.test):
            trivial += 1
        elif isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(t, ast.Name) and COLLECT_IGNORE.fullmatch(t.id) for t in targets):
                ignored += len(node.value.elts) if isinstance(node.value, (ast.List, ast.Tuple)) else 1
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and isinstance(node.func.value, ast.Name) and COLLECT_IGNORE.fullmatch(node.func.value.id):
            arg = node.args[0] if node.args else None
            ignored += len(arg.elts) if isinstance(arg, (ast.List, ast.Tuple)) and node.func.attr == 'extend' else 1
    return {'parametrize cases': cases, 'always-true asserts': trivial, 'collect_ignore entries': ignored}


def measure(text, code=None):
    """Counts for one version of a test file. code = text with strings and comments blanked (code_only); without it the
    raw text is counted."""
    code = text if code is None else code
    return {
        'skip marks': len(SKIP_MARK.findall(code)),
        'skip/xfail calls': count_skip_calls(text, code),
        'test functions': len(TEST_FUNC.findall(code)),
        'asserts': len(ASSERT.findall(code)),
    }


MORE_IS_WEAKER = ('skip marks', 'skip/xfail calls', 'always-true asserts', 'collect_ignore entries', 'deselect options')
FEWER_IS_WEAKER = ('test functions', 'asserts', 'parametrize cases')


def _compare(before, after):
    found = []
    for key in MORE_IS_WEAKER:
        if key in before and after[key] > before[key]:
            found.append(f'adds {after[key] - before[key]} {key} ({before[key]} -> {after[key]})')
    for key in FEWER_IS_WEAKER:
        if key in before and after[key] < before[key]:
            found.append(f'removes {before[key] - after[key]} {key} ({before[key]} -> {after[key]})')
    return found


def weakening(old, new):
    """What changing a test file from old to new would weaken, as short phrases (empty list = fine). Strings and
    comments don't count (a test's sample data may well say pytest.skip), unless either version doesn't tokenize: then
    both are counted raw, so the two sides are always measured the same way. The counts that need a parsed file are
    only compared when both versions parse."""
    old_code, new_code = code_only(old), code_only(new)
    if old_code is None or new_code is None:
        old_code = new_code = None
    before, after = measure(old, old_code), measure(new, new_code)
    old_tree, new_tree = _tree_counts(old), _tree_counts(new)
    if old_tree is not None and new_tree is not None:
        before.update(old_tree)
        after.update(new_tree)
    return _compare(before, after)


# --- pytest settings and CI workflows ------------------------------------------------------------------------------

KEY_LINE = re.compile(r'^\s*(\[|[\w.-]+\s*[=:])')


def _pytest_runs(text):
    """The parts of a settings or workflow file that pytest reads options from: each addopts value (to the next key)
    and each line that runs pytest (with its \\ or ` continuation lines)."""
    lines, parts, i = text.split('\n'), [], 0
    while i < len(lines):
        line = lines[i]
        if re.match(r'^\s*addopts\s*[=:]', line):
            j = i + 1
            while j < len(lines) and not KEY_LINE.match(lines[j]):
                j += 1
            parts.append('\n'.join(lines[i:j]))
            i = j
            continue
        if re.search(r'\bpytest\b', line):
            j = i
            while lines[j].rstrip().endswith(('\\', '`')) and j + 1 < len(lines):
                j += 1
            parts.append('\n'.join(lines[i:j + 1]))
            i = j + 1
            continue
        i += 1
    return parts


def _deselects(text):
    return sum(len(DESELECT.findall(p)) for p in _pytest_runs(text))


def config_weakening(old, new):
    """What changing pytest's settings or a CI workflow from old to new would weaken (empty list = fine)."""
    return _compare({'deselect options': _deselects(old)}, {'deselect options': _deselects(new)})


# --- the hook ------------------------------------------------------------------------------------------------------

def _replace(text, old_string, new_string, replace_all):
    if old_string == '':
        return new_string if text == '' else None
    if old_string not in text:
        return None
    return text.replace(old_string, new_string) if replace_all else text.replace(old_string, new_string, 1)


def file_after(tool_name, tool_input, current):
    """The file text after the tool runs, or None when the edit can't apply (the tool itself will then fail)."""
    if tool_name == 'Write':
        return tool_input.get('content', '')
    if tool_name == 'Edit':
        edits = [tool_input]
    elif tool_name == 'MultiEdit':
        edits = tool_input.get('edits') or []
    else:
        return None
    text = current
    for e in edits:
        text = _replace(text, e.get('old_string', ''), e.get('new_string', ''), bool(e.get('replace_all')))
        if text is None:
            return None
    return text


def check(event):
    """The block message for a hook event, or None to let the tool run."""
    tool_input = event.get('tool_input') or {}
    path = tool_input.get('file_path') or ''
    kind = file_kind(path)
    if kind is None:
        return None
    try:
        with open(path, encoding='utf-8') as f:
            current = f.read()
    except FileNotFoundError:
        current = ''
    except (OSError, UnicodeDecodeError):
        return None
    after = file_after(event.get('tool_name', ''), tool_input, current)
    if after is None:
        return None
    found = weakening(current, after) if kind == 'test' else config_weakening(current, after)
    if not found:
        return None
    return (f'Blocked: this edit to {os.path.basename(path)} weakens the tests - it ' + '; '.join(found) + '.\n'
            'A failing test is a report about the app: fix the app code (or the real cause) so the test passes as it '
            'is, rather than skipping, xfailing, deselecting, deleting or loosening it. Adding tests and asserts is '
            'always fine.\n'
            'If a test truly is wrong or obsolete, stop and ask the human; they can change it by hand '
            '(see "Test-weakening guard" in the root README).')


def main():
    try:
        event = json.load(sys.stdin)
    except (ValueError, UnicodeDecodeError):
        return 0   # not a hook event we understand -> don't get in the way
    if not isinstance(event, dict):
        return 0
    message = check(event)
    if message:
        print(message, file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
