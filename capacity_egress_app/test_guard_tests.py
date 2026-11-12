# the Claude Code hook that refuses edits weakening a test file (../.claude/hooks/guard_tests.py, wired up in
# ../.claude/settings.json): run the way Claude Code runs it, JSON event on stdin -> exit 2 + reason on stderr = blocked
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
GUARD = REPO / '.claude' / 'hooks' / 'guard_tests.py'

spec = importlib.util.spec_from_file_location('guard_tests', GUARD)
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)

BASE = '''import pytest
import tkinter as tk

def test_one():
    assert 1 + 1 == 2
    assert 2 * 2 == 4

def test_two():
    assert 'a' < 'b'

def test_needs_a_screen():
    try:
        r = tk.Tk()
    except tk.TclError as e:
        if 'display' not in str(e):       # only a missing screen is a reason to skip, any other Tk error fails
            raise
        pytest.skip(f"no display: {e}")
    r.destroy()
'''


def run_hook(event):
    return run_hook_raw(json.dumps(event))


def run_hook_raw(stdin):
    proc = subprocess.run([sys.executable, '-I', str(GUARD)], input=stdin,  # noqa: S603
                          capture_output=True, text=True, timeout=30)
    return proc.returncode, proc.stderr


@pytest.fixture
def test_file(tmp_path):
    p = tmp_path / 'test_sample.py'
    p.write_text(BASE, encoding='utf-8')
    return p


def edit(path, old, new, replace_all=False):
    return {'tool_name': 'Edit', 'cwd': str(path.parent),
            'tool_input': {'file_path': str(path), 'old_string': old, 'new_string': new, 'replace_all': replace_all}}


def write(path, content):
    return {'tool_name': 'Write', 'cwd': str(path.parent), 'tool_input': {'file_path': str(path), 'content': content}}


def multi(path, *pairs):
    return {'tool_name': 'MultiEdit', 'cwd': str(path.parent),
            'tool_input': {'file_path': str(path), 'edits': [{'old_string': o, 'new_string': n} for o, n in pairs]}}


# --- blocked -------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize('mark', ['@pytest.mark.skip(reason="flaky on Windows")', '@pytest.mark.skip',
                                  '@pytest.mark.skipif(sys.platform == "win32", reason="x")',
                                  '@pytest.mark.xfail(strict=False)', '@mark.xfail', '@unittest.skip("later")',
                                  '@unittest.expectedFailure'])
def test_blocks_a_new_skip_mark(test_file, mark):
    code, err = run_hook(edit(test_file, 'def test_two():', f'{mark}\ndef test_two():'))
    assert code == 2
    assert 'adds 1 skip marks (0 -> 1)' in err
    assert 'fix the app code' in err


def test_blocks_a_module_wide_skip_mark(test_file):
    code, _ = run_hook(edit(test_file, 'import pytest\n', 'import pytest\npytestmark = pytest.mark.skip\n'))
    assert code == 2


@pytest.mark.parametrize('call', ['pytest.skip("too slow on CI")', 'pytest.xfail("layout differs on Windows")',
                                  'pytest.importorskip("openpyxl")'])
def test_blocks_a_new_skip_call(test_file, call):
    code, err = run_hook(edit(test_file, "    assert 'a' < 'b'", f"    {call}\n    assert 'a' < 'b'"))
    assert code == 2
    assert 'adds 1 skip/xfail calls (0 -> 1)' in err


def test_blocks_a_no_display_skip_without_the_display_check(test_file):
    # same message as the allowed guard, but it would skip on any error, not only a missing screen
    code, _ = run_hook(edit(test_file, "    assert 'a' < 'b'",
                            "    try:\n        tk.Tk()\n    except Exception as e:\n        pytest.skip(f\"no display: {e}\")"))
    assert code == 2


def test_blocks_removing_a_test_function(test_file):
    code, err = run_hook(edit(test_file, "def test_two():\n    assert 'a' < 'b'\n\n", ''))
    assert code == 2
    assert 'removes 1 test functions (3 -> 2)' in err


def test_blocks_removing_an_assert(test_file):
    code, err = run_hook(edit(test_file, '    assert 2 * 2 == 4\n', ''))
    assert code == 2
    assert 'removes 1 asserts (3 -> 2)' in err


def test_blocks_commenting_out_an_assert(test_file):
    code, _ = run_hook(edit(test_file, '    assert 2 * 2 == 4', '    # assert 2 * 2 == 4'))
    assert code == 2


def test_blocks_turning_a_test_into_a_string(test_file):
    code, _ = run_hook(edit(test_file, "def test_two():\n    assert 'a' < 'b'\n", "'''\ndef test_two():\n    assert 'a' < 'b'\n'''\n"))
    assert code == 2


def test_blocks_write_that_drops_tests(test_file):
    code, _ = run_hook(write(test_file, 'import pytest\n\ndef test_one():\n    assert True\n'))
    assert code == 2


def test_blocks_emptying_the_file(test_file):
    code, _ = run_hook(write(test_file, ''))
    assert code == 2


def test_blocks_replace_all_that_removes_every_assert(test_file):
    code, _ = run_hook(edit(test_file, '    assert ', '    print(', replace_all=True))
    assert code == 2


def test_blocks_multiedit_whose_edits_together_weaken(test_file):
    # first edit adds an assert, second removes two: one fewer overall
    code, _ = run_hook(multi(test_file, ("    assert 'a' < 'b'", "    assert 'a' < 'b'\n    assert 'b' < 'c'"),
                             ('    assert 1 + 1 == 2\n    assert 2 * 2 == 4\n', '    pass\n')))
    assert code == 2


def test_blocks_swapping_a_real_test_for_an_empty_one(test_file):
    code, _ = run_hook(edit(test_file, "def test_two():\n    assert 'a' < 'b'", 'def test_two_renamed():\n    pass'))
    assert code == 2


def test_blocks_a_half_finished_edit_that_drops_an_assert(test_file):
    # the new text doesn't tokenize (unclosed bracket) -> both sides are counted raw, still one assert short
    code, _ = run_hook(edit(test_file, '    assert 2 * 2 == 4\n', '    total = (2 * 2\n'))
    assert code == 2


@pytest.mark.parametrize('name', ['test_x.py', 'x_test.py', 'conftest.py'])
def test_every_test_file_name_is_guarded(tmp_path, name):
    p = tmp_path / name
    p.write_text(BASE, encoding='utf-8')
    code, _ = run_hook(edit(p, '    assert 2 * 2 == 4\n', ''))
    assert code == 2


def test_blocks_a_relative_path_against_the_event_cwd(test_file):
    event = edit(test_file, '    assert 2 * 2 == 4\n', '')
    event['tool_input']['file_path'] = test_file.name
    code, _ = run_hook(event)
    assert code == 2


# --- allowed -------------------------------------------------------------------------------------------------------

def test_allows_adding_a_test_and_asserts(test_file):
    code, err = run_hook(edit(test_file, "    assert 'a' < 'b'\n",
                              "    assert 'a' < 'b'\n    assert 'b' < 'c'\n\ndef test_three():\n    assert 3 == 3\n"))
    assert (code, err) == (0, '')


def test_allows_an_edit_that_leaves_the_display_guard_alone(test_file):
    code, _ = run_hook(edit(test_file, '    assert 1 + 1 == 2', '    assert 1 + 1 == 2, "maths"'))
    assert code == 0


def test_allows_a_new_test_file_with_the_display_guard(tmp_path):
    code, _ = run_hook(write(tmp_path / 'test_new_screen.py', BASE))
    assert code == 0


def test_allows_rewriting_a_test_body_that_keeps_its_asserts(test_file):
    code, _ = run_hook(edit(test_file, "    assert 'a' < 'b'", "    letters = 'ab'\n    assert letters[0] < letters[1]"))
    assert code == 0


def test_allows_removing_a_skip(test_file):
    test_file.write_text(BASE.replace('def test_two():', '@pytest.mark.skip\ndef test_two():'), encoding='utf-8')
    code, _ = run_hook(edit(test_file, '@pytest.mark.skip\n', ''))
    assert code == 0


def test_allows_skip_words_inside_strings_and_comments(test_file):
    # sample data or a comment that mentions a skip is not a skip (this very file is full of them)
    code, _ = run_hook(edit(test_file, "    assert 'a' < 'b'",
                            "    note = '@pytest.mark.skip and pytest.skip(\"x\")'  # not pytest.xfail()\n    assert 'a' < 'b'"))
    assert code == 0


@pytest.mark.parametrize('name', ['egress.py', 'app.py', 'testing_notes.py', 'README.md'])
def test_ignores_files_that_are_not_tests(tmp_path, name):
    p = tmp_path / name
    p.write_text(BASE, encoding='utf-8')
    code, _ = run_hook(write(p, ''))
    assert code == 0


def test_lets_an_edit_that_cannot_apply_through(test_file):
    # old_string isn't in the file -> the Edit tool itself fails, nothing to judge
    code, _ = run_hook(edit(test_file, 'not in the file', ''))
    assert code == 0


@pytest.mark.parametrize('stdin', ['', 'not json', '[1, 2]'])
def test_lets_unreadable_hook_input_through(stdin):
    assert run_hook_raw(stdin)[0] == 0


def test_ignores_other_tools(test_file):
    code, _ = run_hook({'tool_name': 'NotebookEdit', 'tool_input': {'file_path': str(test_file)}})
    assert code == 0


# --- the repo's own test files -------------------------------------------------------------------------------------

def test_the_repo_test_files_pass_through_unchanged():
    # rewriting every test file exactly as it is must never be blocked, display guards and all
    files = sorted((REPO / 'capacity_egress_app').glob('test_*.py'))
    assert files
    for p in files:
        text = p.read_text(encoding='utf-8')
        assert guard.weakening(text, text) == [], p.name


@pytest.mark.parametrize('name', ['test_screens.py', 'test_editor_screen.py', 'test_speed.py'])
def test_the_screen_tests_display_guards_are_recognised(name):
    text = (REPO / 'capacity_egress_app' / name).read_text(encoding='utf-8')
    assert 'no display' in text
    assert guard.measure(text, guard.code_only(text))['skip/xfail calls'] == 0


def test_settings_wire_the_hook_to_edit_write_and_multiedit():
    settings = json.loads((REPO / '.claude' / 'settings.json').read_text(encoding='utf-8'))
    (entry,) = settings['hooks']['PreToolUse']
    assert set(entry['matcher'].split('|')) == {'Edit', 'Write', 'MultiEdit'}
    assert entry['hooks'][0]['command'] == 'python3 -I "$CLAUDE_PROJECT_DIR/.claude/hooks/guard_tests.py"'
