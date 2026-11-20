import tkinter as tk
from tkinter import ttk
import egress

# status -> same on every table, both screens and the exports (README "Colours"). on the screens a status is a mark in
# the table's first column, so shape and colour both say it, plus a row tint only where someone has to act. the exports
# keep their Excel fills (exports.py)
# ROW_BG is the old whole-row fill: only the check screen's two verdict badges still use it, until they become chips
ROW_BG = {egress.GREEN: '#C6EFCE', egress.AMBER: '#FFEB9C', egress.RED: '#FFC7CE', egress.GREY: '#E7E6E6'}
ROW_FG = '#1A1A1A'
CHANGED_FG = '#005FB8'                                 # a value the check changed (blue, same as the theme accent)

GROUND = '#F3F4F6'                                     # window background: cards and tables sit on it in white
SURFACE = '#FFFFFF'                                    # cards, tables, fields, buttons
CARD_BORDER = '#E1E4E8'                                # 1 px round a card
MUTED = '#5D636B'                                      # secondary text, section titles, rows with no data: 6.1:1 on white
TEXT_FG = '#1A1A1A'
BORDER = '#E3E3E3'                                     # panels and tables
CONTROL_BORDER = '#BDBDBD'                             # buttons and fields, one step stronger
HOVER = '#E7EAEE'                                      # a flat button under the pointer: visible on the ground and on white
PRESSED = '#D9DDE3'
ACCENT = CHANGED_FG
ACCENT_HOVER = '#004C94'
ACCENT_PRESSED = '#003F7A'
SELECTED = '#CFE2F5'                                   # picked row: pale blue, the text stays readable
ERROR_FG = '#B00020'                                   # a message that says something went wrong

# status -> (ink, tint, mark colour). ink and tint are text on its chip and the row, mark is the shape's own colour; all
# text pairs are above 4.5:1, marks above 3:1 on white and on their own tint. green rows stay white (the mark is enough),
# grey has no tint: its rows are muted text on white
STATUS = {egress.GREEN: ('#1E6B3A', '#E4F4E9', '#2E8B57'),
          egress.AMBER: ('#7A4A00', '#FFF2D1', '#B87000'),
          egress.RED: ('#A31919', '#FDE3E3', '#C62828'),
          egress.GREY: (MUTED, None, '#6F767E')}
# status -> a table row's own look: a tint where action is needed, red text only for over a hard limit, muted text for no data
ROW_RULES = {egress.GREEN: {},
             egress.AMBER: {'background': STATUS[egress.AMBER][1]},
             egress.RED: {'background': STATUS[egress.RED][1], 'foreground': STATUS[egress.RED][0]},
             egress.GREY: {'foreground': MUTED}}

# short on purpose: the full meaning of each colour is in the README ("Colours")
LEGEND = [(egress.GREEN, "Green", "within"),
          (egress.AMBER, "Amber", "needs a look"),
          (egress.RED, "Red", "over a hard limit"),
          (egress.GREY, "Grey", "no data yet")]

MARK_SIZE = 12
MARK_COLUMN = 28                                        # width of a table's first column, the one that holds the mark

# a mark's shape -> the runs of pixels it fills, as (x0, y0, x1, y1) boxes for PhotoImage.put: one per line of the 12 x 12 image
def _runs(lines):
    return [(x0, y, x1, y + 1) for y, spans in enumerate(lines) for x0, x1 in spans]

# a circle, or a ring when it has a hole: a pixel is in when its centre is between the two radii
def _circle(outer, hole=0.0):
    lines = []
    for y in range(MARK_SIZE):
        xs = [x for x in range(MARK_SIZE) if hole ** 2 <= (x + .5 - MARK_SIZE / 2) ** 2 + (y + .5 - MARK_SIZE / 2) ** 2 <= outer ** 2]
        # a ring's line is two runs, a disc's one: split where the pixels stop touching
        spans = []
        for x in xs:
            if spans and spans[-1][1] == x:
                spans[-1][1] = x + 1
            else:
                spans.append([x, x + 1])
        lines.append(spans)
    return lines

# a triangle, point up: one pixel line lower, a little wider, down to the full width
TRIANGLE = [[(MARK_SIZE // 2 - (2 + (y - 1) * 10 // 9) // 2, MARK_SIZE // 2 + (2 + (y - 1) * 10 // 9) // 2)] if 0 < y < MARK_SIZE - 1 else []
            for y in range(MARK_SIZE)]
SQUARE = [[(1, MARK_SIZE - 1)] if 0 < y < MARK_SIZE - 1 else [] for y in range(MARK_SIZE)]
SHAPES = {egress.GREEN: _runs(_circle(5.8)),             # filled circle: within
          egress.AMBER: _runs(TRIANGLE),                 # triangle: needs a look
          egress.RED: _runs(SQUARE),                     # square: over a hard limit
          egress.GREY: _runs(_circle(5.8, hole=3.4))}    # ring: no data

# the four marks, drawn once per window and kept on it so they are not garbage collected. a transparent background lets
# the row's own colour (tint, or the selected blue) show round the shape
def marks(widget):
    root = widget.nametowidget('.')
    if not hasattr(root, 'status_marks'):
        root.status_marks = {}
        for colour, runs in SHAPES.items():
            image = tk.PhotoImage(master=root, width=MARK_SIZE, height=MARK_SIZE)
            for box in runs:
                image.put(STATUS[colour][2], to=box)
            root.status_marks[colour] = image
    return root.status_marks

# a table that shows statuses -> a first column for the mark, then the usual headings, and one tag per colour: insert
# rows with **row(tree, colour). a table without statuses keeps only its headings
def colour_tags(tree):
    tree.configure(show=('tree', 'headings'))
    tree.column('#0', width=MARK_COLUMN, minwidth=MARK_COLUMN, stretch=False, anchor='center')
    tree.heading('#0', text='')
    for colour, rule in ROW_RULES.items():
        tree.tag_configure(colour, **rule)
    tree.status_marks = marks(tree)                     # row() reads them from the table: one lookup per table, not per row

# the mark and tags of a row with this status (no mark and no tag for a room out of scope) + any tags of its own
def row(tree, colour, *tags):
    return {'image': tree.status_marks[colour] if colour in STATUS else '', 'tags': tuple(t for t in (colour, *tags) if t)}

def legend(parent):
    frame = ttk.Frame(parent)
    shapes = marks(parent)
    for colour, name, meaning in LEGEND:
        item = ttk.Frame(frame)
        item.pack(side='left', padx=(0, 18), pady=2)
        ttk.Label(item, image=shapes[colour]).pack(side='left', padx=(0, 6))
        ttk.Label(item, text=f"{name}: {meaning}").pack(side='left')
    return frame
