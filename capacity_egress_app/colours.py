import tkinter as tk
from tkinter import ttk
import egress

# row colours -> same on every table, both screens and the exports (README "Colours")
ROW_BG = {egress.GREEN: '#C6EFCE', egress.AMBER: '#FFEB9C', egress.RED: '#FFC7CE', egress.GREY: '#E7E6E6'}
ROW_FG = '#1A1A1A'
CHANGED_FG = '#005FB8'                                 # a value the check changed (blue, same as the theme accent)

MUTED_FG = '#6A6A6A'                                   # secondary text, 4.5:1 or better on the theme's background
ERROR_FG = '#B00020'                                   # a message that says something went wrong, a missing room

# short on purpose: the full meaning of each colour is in the README ("Colours")
LEGEND = [(egress.GREEN, "Green", "within"),
          (egress.AMBER, "Amber", "needs a look"),
          (egress.RED, "Red", "over a hard limit"),
          (egress.GREY, "Grey", "no data yet")]

def colour_tags(tree):
    # one tag per colour on a Treeview -> insert rows with tags=(colour,)
    for colour, bg in ROW_BG.items():
        tree.tag_configure(colour, background=bg, foreground=ROW_FG)

def legend(parent):
    frame = ttk.Frame(parent)
    for colour, name, meaning in LEGEND:
        item = ttk.Frame(frame)
        item.pack(side='left', padx=(0, 18), pady=2)
        tk.Label(item, bg=ROW_BG[colour], width=2, relief='solid', borderwidth=1).pack(side='left', padx=(0, 6))
        ttk.Label(item, text=f"{name}: {meaning}").pack(side='left')
    return frame
