"""Keeps the test windows off the screen.

Every test that builds the app opens real Tk windows. Locally they would flash on the Mac for the whole run, so by
default each Tk root and Toplevel is made fully transparent (-alpha 0) the moment it is created. A transparent window is
still mapped and laid out, so the geometry tests (MIN_WINDOW, the -17 px font) measure the same real sizes.

CAPACITY_TEST_WINDOWS=real turns this off and shows the windows as usual; the CI workflow sets it
(.github/workflows/tests.yml).
"""
import os
import tkinter as tk

import pytest

HIDE = os.environ.get('CAPACITY_TEST_WINDOWS', 'hidden') != 'real'


@pytest.fixture(autouse=True, scope='session')
def hidden_windows():
    if not HIDE:
        yield
        return
    originals = {cls: cls.__init__ for cls in (tk.Tk, tk.Toplevel)}

    def hiding(cls):
        def __init__(self, *args, **kwargs):
            originals[cls](self, *args, **kwargs)
            self.attributes('-alpha', 0.0)
        return __init__

    for cls in originals:
        cls.__init__ = hiding(cls)
    yield
    for cls, init in originals.items():
        cls.__init__ = init


@pytest.fixture(autouse=True)
def roomy_work_area(monkeypatch):
    """The tests measure the layout, not the machine's screen: a window is limited to a 1920x1080 screen's work area,
    whatever display the run has (a CI runner's can be much smaller). A test of a smaller screen patches this itself."""
    import widgets
    monkeypatch.setattr(widgets, 'work_area', lambda window: (1920, 1040))
