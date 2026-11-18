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


def _make_invisible(window):
    try:
        window.attributes('-alpha', 0.0)
    except tk.TclError:      # a platform without window transparency: leave the window as it is
        pass


@pytest.fixture(autouse=True, scope='session')
def hidden_windows():
    if not HIDE:
        yield
        return
    originals = {cls: cls.__init__ for cls in (tk.Tk, tk.Toplevel)}

    def hiding(cls):
        def __init__(self, *args, **kwargs):
            originals[cls](self, *args, **kwargs)
            _make_invisible(self)
        return __init__

    for cls in originals:
        cls.__init__ = hiding(cls)
    yield
    for cls, init in originals.items():
        cls.__init__ = init
