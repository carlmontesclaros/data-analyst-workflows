# the Claude Code hook that refuses edits weakening a test file (../.claude/hooks/guard_tests.py, wired up in
# ../.claude/settings.json): run the way Claude Code runs it, JSON event on stdin -> exit 2 + reason on stderr = blocked
import importlib.util
import json
import os
import re
import shutil
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
    assert len([1, 2]) == 2
    assert abs(-4) == 4

def test_two():
    assert min('ab') == 'a'

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
    code, err = run_hook(edit(test_file, "    assert min('ab') == 'a'", f"    {call}\n    assert min('ab') == 'a'"))
    assert code == 2
    assert 'adds 1 skip/xfail calls (0 -> 1)' in err


def test_blocks_a_no_display_skip_without_the_display_check(test_file):
    # same message as the allowed guard, but it would skip on any error, not only a missing screen
    code, _ = run_hook(edit(test_file, "    assert min('ab') == 'a'",
                            "    try:\n        tk.Tk()\n    except Exception as e:\n        pytest.skip(f\"no display: {e}\")"))
    assert code == 2


def test_blocks_removing_a_test_function(test_file):
    code, err = run_hook(edit(test_file, "def test_two():\n    assert min('ab') == 'a'\n\n", ''))
    assert code == 2
    assert 'removes 1 test functions (3 -> 2)' in err


def test_blocks_removing_an_assert(test_file):
    code, err = run_hook(edit(test_file, '    assert abs(-4) == 4\n', ''))
    assert code == 2
    assert 'removes 1 asserts (3 -> 2)' in err


def test_blocks_commenting_out_an_assert(test_file):
    code, _ = run_hook(edit(test_file, '    assert abs(-4) == 4', '    # assert abs(-4) == 4'))
    assert code == 2


def test_blocks_turning_a_test_into_a_string(test_file):
    code, _ = run_hook(edit(test_file, "def test_two():\n    assert min('ab') == 'a'\n", "'''\ndef test_two():\n    assert min('ab') == 'a'\n'''\n"))
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
    code, _ = run_hook(multi(test_file, ("    assert min('ab') == 'a'", "    assert min('ab') == 'a'\n    assert max('bc') == 'c'"),
                             ('    assert len([1, 2]) == 2\n    assert abs(-4) == 4\n', '    pass\n')))
    assert code == 2


def test_blocks_swapping_a_real_test_for_an_empty_one(test_file):
    code, _ = run_hook(edit(test_file, "def test_two():\n    assert min('ab') == 'a'", 'def test_two_renamed():\n    pass'))
    assert code == 2


def test_blocks_a_half_finished_edit_that_drops_an_assert(test_file):
    # the new text doesn't tokenize (unclosed bracket) -> both sides are counted raw, still one assert short
    code, _ = run_hook(edit(test_file, '    assert abs(-4) == 4\n', '    total = (2 * 2\n'))
    assert code == 2


@pytest.mark.parametrize('name', ['test_x.py', 'x_test.py', 'conftest.py'])
def test_every_test_file_name_is_guarded(tmp_path, name):
    p = tmp_path / name
    p.write_text(BASE, encoding='utf-8')
    code, _ = run_hook(edit(p, '    assert abs(-4) == 4\n', ''))
    assert code == 2


@pytest.mark.parametrize('imports, call', [('from pytest import skip', 'skip("x")'),
                                           ('from pytest import xfail as xf', 'xf("x")'),
                                           ('from pytest import (\n    importorskip,\n    raises,\n)', 'importorskip("openpyxl")')])
def test_blocks_skip_calls_imported_from_pytest(test_file, imports, call):
    code, _ = run_hook(edit(test_file, "    assert min('ab') == 'a'", f"    {call}\n    assert min('ab') == 'a'"))
    assert code == 0   # skip() alone could be anything; it's pytest's once imported from pytest
    test_file.write_text(BASE.replace('import pytest\n', f'import pytest\n{imports}\n'), encoding='utf-8')
    code, err = run_hook(edit(test_file, "    assert min('ab') == 'a'", f"    {call}\n    assert min('ab') == 'a'"))
    assert code == 2
    assert 'adds 1 skip/xfail calls (0 -> 1)' in err


@pytest.mark.parametrize('line', ['self.skipTest("later")', 'raise unittest.SkipTest("later")',
                                  'raise SkipTest("later")', 'raise pytest.skip.Exception("later")',
                                  'raise pytest.xfail.Exception("later")'])
def test_blocks_skip_raises_and_skiptest(test_file, line):
    code, _ = run_hook(edit(test_file, "    assert min('ab') == 'a'", f"    {line}\n    assert min('ab') == 'a'"))
    assert code == 2


@pytest.mark.parametrize('old, new', [
    ('', 'collect_ignore = ["test_screens.py"]\n'),
    ('collect_ignore = []\n', 'collect_ignore = ["test_screens.py"]\n'),
    ('collect_ignore = ["a.py"]\n', 'collect_ignore = ["a.py", "test_screens.py"]\n'),
    ('collect_ignore = []\n', 'collect_ignore = []\ncollect_ignore.append("test_screens.py")\n'),
    ('', 'collect_ignore_glob = ["test_s*.py"]\n'),
])
def test_blocks_adding_collect_ignore_entries_in_conftest(tmp_path, old, new):
    p = tmp_path / 'conftest.py'
    p.write_text('import pytest\n' + old, encoding='utf-8')
    code, err = run_hook(write(p, 'import pytest\n' + new))
    assert code == 2
    assert 'collect_ignore entries' in err


def test_allows_removing_a_collect_ignore_entry(tmp_path):
    p = tmp_path / 'conftest.py'
    p.write_text('collect_ignore = ["a.py", "b.py"]\n', encoding='utf-8')
    assert run_hook(write(p, 'collect_ignore = ["a.py"]\n'))[0] == 0


PARAMETRIZED = '''import pytest

@pytest.mark.parametrize('n', [1, 2, 3])
def test_n(n):
    assert n > 0
'''


@pytest.mark.parametrize('new', ["@pytest.mark.parametrize('n', [3])", "@pytest.mark.parametrize('n', (1, 2))",
                                 "@pytest.mark.parametrize(argnames='n', argvalues=[1])"])
def test_blocks_fewer_parametrize_cases(test_file, new):
    test_file.write_text(PARAMETRIZED, encoding='utf-8')
    code, err = run_hook(edit(test_file, "@pytest.mark.parametrize('n', [1, 2, 3])", new))
    assert code == 2
    assert 'parametrize cases' in err


def test_allows_more_parametrize_cases(test_file):
    test_file.write_text(PARAMETRIZED, encoding='utf-8')
    assert run_hook(edit(test_file, '[1, 2, 3]', '[1, 2, 3, 4]'))[0] == 0


@pytest.mark.parametrize('trivial', ['assert True', 'assert 1', 'assert not False', 'assert 1 == 1',
                                     "assert 'x'", 'assert True, "kept for now"', "assert (letters, 'why')",
                                     'assert 2 > 1 and not None'])
def test_blocks_an_always_true_assert(test_file, trivial):
    # swapping a real assert for one that can't fail keeps every count the same, so it is caught on its own
    code, err = run_hook(edit(test_file, "    assert min('ab') == 'a'", f'    {trivial}'))
    assert code == 2
    assert 'always-true asserts' in err


@pytest.mark.parametrize('real', ['assert False', 'assert x', 'assert 1 == len(x)', 'assert not items'])
def test_allows_asserts_that_can_fail(test_file, real):
    assert run_hook(edit(test_file, "    assert min('ab') == 'a'\n", f"    assert min('ab') == 'a'\n    {real}\n"))[0] == 0


# --- pytest settings and CI workflows ------------------------------------------------------------------------------

PYPROJECT = '''[tool.pytest.ini_options]
addopts = "--capture=sys"
filterwarnings = ["error::ResourceWarning"]

[tool.ruff.lint]
ignore = ["E501"]
'''

WORKFLOW = '''name: tests
jobs:
  test:
    steps:
      - run: python -m pip install -r requirements-dev.txt
      - run: python -m pytest -q --cov=. --cov-report=term-missing:skip-covered
'''


@pytest.mark.parametrize('name, old, new', [
    ('pyproject.toml', 'addopts = "--capture=sys"', 'addopts = "--capture=sys -k \'not screens\'"'),
    ('pyproject.toml', 'addopts = "--capture=sys"', 'addopts = "--capture=sys --deselect test_speed.py::test_fast"'),
    ('pyproject.toml', 'addopts = "--capture=sys"', 'addopts = [\n    "--capture=sys",\n    "--ignore=test_screens.py",\n]'),
    ('pyproject.toml', 'addopts = "--capture=sys"', 'addopts = "--capture=sys --ignore-glob=test_s*.py"'),
    ('pyproject.toml', 'addopts = "--capture=sys"', 'addopts = "--capture=sys -m \'not slow\'"'),
    ('pytest.ini', 'addopts = "--capture=sys"', 'addopts = --capture=sys -k "not windows"'),
    ('tests.yml', '-q --cov=.', '-q -k "not screens" --cov=.'),
    ('tests.yml', '-q --cov=.', '-q --deselect test_screens.py --cov=.'),
    ('tests.yml', 'python -m pytest -q --cov=.', 'python -m pytest -q \\\n          --ignore=test_screens.py --cov=.'),
])
def test_blocks_adding_a_deselect_option(tmp_path, name, old, new):
    base = WORKFLOW if name == 'tests.yml' else PYPROJECT
    folder = tmp_path / '.github' / 'workflows' if name == 'tests.yml' else tmp_path
    folder.mkdir(parents=True, exist_ok=True)
    p = folder / name
    p.write_text(base, encoding='utf-8')
    code, err = run_hook(edit(p, old, new))
    assert code == 2
    assert 'deselect options' in err


@pytest.mark.parametrize('name, old, new', [
    ('pyproject.toml', 'ignore = ["E501"]', 'ignore = ["E501", "B008"]'),                     # ruff's ignore, not pytest's
    ('pyproject.toml', 'addopts = "--capture=sys"', 'addopts = "--capture=sys --strict-markers"'),
    ('pyproject.toml', 'filterwarnings = ["error::ResourceWarning"]', 'filterwarnings = []'),
    ('tests.yml', '-q --cov=.', '-q -x --cov=.'),
    ('tests.yml', 'pip install -r requirements-dev.txt', 'pip install -k -r requirements-dev.txt'),   # not a pytest line
])
def test_allows_other_settings_and_workflow_edits(tmp_path, name, old, new):
    base = WORKFLOW if name == 'tests.yml' else PYPROJECT
    folder = tmp_path / '.github' / 'workflows' if name == 'tests.yml' else tmp_path
    folder.mkdir(parents=True, exist_ok=True)
    p = folder / name
    p.write_text(base, encoding='utf-8')
    assert run_hook(edit(p, old, new)) == (0, '')


def test_allows_removing_a_deselect_option(tmp_path):
    p = tmp_path / 'pyproject.toml'
    p.write_text(PYPROJECT.replace('"--capture=sys"', '"--capture=sys -k \'not slow\'"'), encoding='utf-8')
    assert run_hook(edit(p, " -k 'not slow'", ''))[0] == 0


def test_a_yml_outside_github_workflows_is_not_guarded(tmp_path):
    p = tmp_path / 'tests.yml'
    p.write_text(WORKFLOW, encoding='utf-8')
    assert run_hook(edit(p, '-q --cov=.', '-q -k "not screens" --cov=.'))[0] == 0


# --- allowed -------------------------------------------------------------------------------------------------------

def test_allows_adding_a_test_and_asserts(test_file):
    code, err = run_hook(edit(test_file, "    assert min('ab') == 'a'\n",
                              "    assert min('ab') == 'a'\n    assert max('bc') == 'c'\n\ndef test_three():\n    assert len('abc') == 3\n"))
    assert (code, err) == (0, '')


def test_allows_an_edit_that_leaves_the_display_guard_alone(test_file):
    code, _ = run_hook(edit(test_file, '    assert len([1, 2]) == 2', '    assert len([1, 2]) == 2, "maths"'))
    assert code == 0


def test_allows_a_new_test_file_with_the_display_guard(tmp_path):
    code, _ = run_hook(write(tmp_path / 'test_new_screen.py', BASE))
    assert code == 0


def test_allows_rewriting_a_test_body_that_keeps_its_asserts(test_file):
    code, _ = run_hook(edit(test_file, "    assert min('ab') == 'a'", "    letters = 'ab'\n    assert letters[0] < letters[1]"))
    assert code == 0


def test_allows_removing_a_skip(test_file):
    test_file.write_text(BASE.replace('def test_two():', '@pytest.mark.skip\ndef test_two():'), encoding='utf-8')
    code, _ = run_hook(edit(test_file, '@pytest.mark.skip\n', ''))
    assert code == 0


def test_allows_skip_words_inside_strings_and_comments(test_file):
    # sample data or a comment that mentions a skip is not a skip (this very file is full of them)
    code, _ = run_hook(edit(test_file, "    assert min('ab') == 'a'",
                            "    note = '@pytest.mark.skip and pytest.skip(\"x\")'  # not pytest.xfail()\n    assert min('ab') == 'a'"))
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

REPO_TESTS = sorted(p.name for p in (REPO / 'capacity_egress_app').glob('test_*.py'))
FIRST_ASSERT = re.compile(r'^[ \t]+assert [^\n]*\n', re.MULTILINE)


def first_code_assert(text):
    """The first assert statement that is code (not inside a string) and fits on one line, with its newline."""
    code = guard.code_only(text)
    for m in FIRST_ASSERT.finditer(code):
        line = code[m.start():m.end()]
        if line.count('(') == line.count(')') and line.count('[') == line.count(']'):
            return text[m.start():m.end()]
    raise AssertionError('no one-line assert found')


@pytest.mark.parametrize('name', REPO_TESTS)
def test_the_repo_test_files_are_measured_right(name):
    # on every real test file: dropping its first assert is blocked, writing it out a second time is allowed
    p = REPO / 'capacity_egress_app' / name
    line = first_code_assert(p.read_text(encoding='utf-8'))
    code, err = run_hook(edit(p, line, ''))
    assert code == 2, err
    assert 'asserts' in err
    assert run_hook(edit(p, line, line + line)) == (0, '')


@pytest.mark.parametrize('name', ['test_screens.py', 'test_editor_screen.py', 'test_speed.py'])
def test_the_screen_tests_keep_their_display_guards(name):
    # rewriting a screen test as it is, no-display skip included, is allowed; deleting the whole file is not
    p = REPO / 'capacity_egress_app' / name
    text = p.read_text(encoding='utf-8')
    assert run_hook(write(p, text)) == (0, '')
    assert run_hook(write(p, ''))[0] == 2


def test_blocks_a_display_guard_faked_in_a_comment(test_file):
    # the TclError check and the re-raise have to be code; a comment saying so is not enough
    code, _ = run_hook(edit(test_file, "    assert min('ab') == 'a'",
                            "    try:\n        tk.Tk()\n    except Exception as e:  # TclError: 'display' not in str(e) -> raise\n"
                            "        pytest.skip(f\"no display: {e}\")"))
    assert code == 2


def test_blocks_a_display_guard_that_never_re_raises(test_file):
    code, _ = run_hook(edit(test_file, "    assert min('ab') == 'a'",
                            "    try:\n        tk.Tk()\n    except tk.TclError as e:\n        if 'display' not in str(e):\n"
                            "            print(e)\n        pytest.skip(f\"no display: {e}\")"))
    assert code == 2


def _shell():
    if sys.platform == 'win32':   # Claude Code runs hooks through Git Bash on Windows
        git_bash = Path(os.environ.get('ProgramFiles', r'C:\Program Files')) / 'Git' / 'bin' / 'bash.exe'
        return str(git_bash) if git_bash.exists() else shutil.which('bash')
    return shutil.which('sh')


def test_the_settings_command_runs_the_guard(tmp_path, test_file):
    # run the hook exactly as .claude/settings.json tells Claude Code to, for each tool it is wired to
    settings = json.loads((REPO / '.claude' / 'settings.json').read_text(encoding='utf-8'))
    (entry,) = settings['hooks']['PreToolUse']
    (hook,) = entry['hooks']
    assert hook['type'] == 'command'
    # a python3 on the PATH that is this interpreter (CI's Windows Python has no python3.exe)
    shim = tmp_path / 'bin'
    shim.mkdir()
    (shim / 'python3').write_text(f'#!/bin/sh\nexec "{Path(sys.executable).as_posix()}" "$@"\n', encoding='utf-8')
    (shim / 'python3').chmod(0o755)
    env = {**os.environ, 'CLAUDE_PROJECT_DIR': str(REPO),
           'PATH': str(shim) + os.pathsep + os.environ.get('PATH', '')}
    weakening_events = {'Edit': edit(test_file, '    assert abs(-4) == 4\n', ''),
                        'Write': write(test_file, ''),
                        'MultiEdit': multi(test_file, ('    assert abs(-4) == 4\n', ''))}
    assert set(entry['matcher'].split('|')) == set(weakening_events)
    for tool, event in weakening_events.items():
        proc = subprocess.run([_shell(), '-c', hook['command']], input=json.dumps(event), env=env,  # noqa: S603
                              capture_output=True, text=True, timeout=30)
        assert proc.returncode == 2, (tool, proc.stderr)
        assert 'fix the app code' in proc.stderr
