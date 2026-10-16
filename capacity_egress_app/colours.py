import tkinter as tk
from tkinter import ttk
import egress

# row colours -> same on every table, both screens and the exports (README "Colours")
ROW_BG = {egress.GREEN: '#C6EFCE', egress.AMBER: '#FFEB9C', egress.RED: '#FFC7CE', egress.GREY: '#E7E6E6'}
ROW_FG = '#1A1A1A'
CHANGED_FG = '#005FB8'                                 # a value the check changed (blue, same as the theme accent)

LEGEND = [(egress.GREEN, "Green", "within: visited room at or under per code, floor within exit capacity, exit width OK"),
          (egress.AMBER, "Amber", "needs a look: room over per code (needs justification), floor flagged for review, width review"),
          (egress.RED, "Red", "over a hard limit: floor over exit capacity, exit below minimum width"),
          (egress.GREY, "Grey", "no data yet: room not visited (per code), floor exits not measured, not counted as an exit")]

def colour_tags(tree):
    # one tag per colour on a Treeview -> insert rows with tags=(colour,)
    for colour, bg in ROW_BG.items():
        tree.tag_configure(colour, background=bg, foreground=ROW_FG)

def legend(parent, compact=False):
    frame = ttk.Frame(parent)
    for colour, name, meaning in LEGEND:
        item = ttk.Frame(frame)
        item.pack(side='left', padx=(0, 18), pady=2)
        tk.Label(item, bg=ROW_BG[colour], width=2, relief='solid', borderwidth=1).pack(side='left', padx=(0, 6))
        text = name if compact else f"{name}: {meaning}"
        ttk.Label(item, text=text, wraplength=0 if compact else 300, justify='left').pack(side='left')
    return frame
