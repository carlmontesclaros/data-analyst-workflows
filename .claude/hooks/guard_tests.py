"""Claude Code PreToolUse hook: refuse edits that make a test file weaker.

A failing test means the app is wrong (or the test is), not that the test should go quiet. This hook runs before every
Edit, Write and MultiEdit (.claude/settings.json) and, for a test file (test_*.py, *_test.py, conftest.py), compares the
file as it is now with the file as it would be after the edit. It blocks (exit 2, reason on stderr for the agent) when the
edit would:
  - add a skip / skipif / xfail mark (pytest.mark.*, or unittest's skip decorators)
  - add a pytest.skip(...) / pytest.xfail(...) / pytest.importorskip(...) call
  - leave fewer test functions
  - leave fewer assert statements
The no-display guard the screen tests use (except tk.TclError -> if 'display' not in str(e): raise -> pytest.skip(f"no
display: {e}")) is the one skip that is allowed: it only skips on a machine with no screen at all.

Everything else (non-test files, new tests, extra asserts, unreadable hook input) is let through. A human who really means
to remove or skip a test edits the file by hand, or turns the hook off for a while (see the root README).

Standard library only; run with python3 -I so nothing in the working folder can be imported in its place.
"""

import io
import json
import os
import re
import sys
import tokenize

TEST_FILE = re.compile(r'^(test_.*|.*_test|conftest)\.py$')

# skip marks: @pytest.mark.skip / skipif / xfail (also via `from pytest import mark` or pytestmark = ...), and
# unittest's @unittest.skip / skipIf / skipUnless / expectedFailure
SKIP_MARK = re.compile(r'\bmark\s*\.\s*(skip|skipif|xfail)\b|\bunittest\s*\.\s*(skip|skipIf|skipUnless|expectedFailure)\b'
                       r'|^\s*@\s*(skip|skipIf|skipUnless|expectedFailure)\b', re.MULTILINE)
SKIP_CALL = re.compile(r'\bpytest\s*\.\s*(skip|xfail|importorskip)\s*\(')
TEST_FUNC = re.compile(r'^\s*(async\s+)?def\s+test\w*\s*\(', re.MULTILINE)
ASSERT = re.compile(r'^\s*assert\b', re.MULTILINE)

# the allowed no-display guard: the skip says "no display" and the lines just above it catch a TclError and re-raise
# anything that isn't about the display
DISPLAY_SKIP = re.compile(r'''\bpytest\s*\.\s*skip\s*\(\s*f?["']no display''')
DISPLAY_CHECK = re.compile(r'''["']display["']\s+not\s+in\s+str\(''')
LOOK_BACK = 4   # lines


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


def is_test_file(path):
    return bool(TEST_FILE.match(os.path.basename(path or '')))


def _is_display_guard(lines, i):
    if not DISPLAY_SKIP.search(lines[i]):
        return False
    above = '\n'.join(lines[max(0, i - LOOK_BACK):i])
    return 'TclError' in above and bool(DISPLAY_CHECK.search(above))


def count_skip_calls(text, code):
    """pytest.skip/xfail/importorskip calls in code, not counting the allowed no-display guard (judged on text, the
    same lines with their strings and comments still in)."""
    lines, code_lines = text.split('\n'), code.split('\n')
    return sum(len(SKIP_CALL.findall(line)) for i, line in enumerate(code_lines) if not _is_display_guard(lines, i))


def measure(text, code=None):
    """Counts for one version of a file. code = text with strings and comments blanked (code_only); without it the raw
    text is counted."""
    code = text if code is None else code
    return {
        'skip marks': len(SKIP_MARK.findall(code)),
        'skip/xfail calls': count_skip_calls(text, code),
        'test functions': len(TEST_FUNC.findall(code)),
        'asserts': len(ASSERT.findall(code)),
    }


def weakening(old, new):
    """What the change from old to new would weaken, as short phrases (empty list = fine). Strings and comments don't
    count (a test's sample data may well say pytest.skip), unless either version doesn't tokenize: then both are
    counted raw, so the two sides are always measured the same way."""
    old_code, new_code = code_only(old), code_only(new)
    if old_code is None or new_code is None:
        old_code = new_code = None
    before, after = measure(old, old_code), measure(new, new_code)
    found = []
    for key in ('skip marks', 'skip/xfail calls'):
        if after[key] > before[key]:
            found.append(f'adds {after[key] - before[key]} {key} ({before[key]} -> {after[key]})')
    for key in ('test functions', 'asserts'):
        if after[key] < before[key]:
            found.append(f'removes {before[key] - after[key]} {key} ({before[key]} -> {after[key]})')
    return found


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
    if not is_test_file(path):
        return None
    if not os.path.isabs(path):
        path = os.path.join(event.get('cwd') or os.getcwd(), path)
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
    found = weakening(current, after)
    if not found:
        return None
    return (f'Blocked: this edit to {os.path.basename(path)} weakens the tests - it ' + '; '.join(found) + '.\n'
            'A failing test is a report about the app: fix the app code (or the real cause) so the test passes as it '
            'is, rather than skipping, xfailing, deleting or loosening it. Adding tests and asserts is always fine.\n'
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
