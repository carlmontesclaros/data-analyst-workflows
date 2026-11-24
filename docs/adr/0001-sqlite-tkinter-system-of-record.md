---
status: accepted
date: 2026-10-02
supersedes: "Excel for exit capture, no SharePoint List/Power Apps" (2026-09-25)
---

# An SQLite + Tkinter desktop app replaces Excel as the system of record

After Carl showed Mark the exiting capacity script, Mark asked to change a room's capacity (e.g. 30 → 36 for an OREM request) without opening the Excel input. Editing the Excel files from a GUI doesn't work: saving the space report through pandas/openpyxl destroys its slicers, a file open in Excel blocks or loses other people's saves, and Carl was keeping a side workbook by hand, so counts could drift between copies. We decided that one SQLite file on the S: drive holds room capacities, exits, code factors and an audit log of every change (old value, new value, who, when, why, and a clause reference for code factors). A Tkinter desktop app installed on each user's Windows machine edits it. The FMIS space report is read-only input for the room list, and Excel files are only produced as exports (a capacity export in the space report layout, and the results workbook).

## Considered options

- **Keep Excel and write PM edits into the master.** Rejected: it loses slicers, fails when the file is open, and has no history.
- **Power Apps + SharePoint List / Dataverse.** Carl has access, but rejected for now as too much setup, and the Python calculation can't run inside Power Apps.
- **Supabase / Netlify or another hosted web app.** Rejected 2026-09-29: UVic data would sit outside UVic systems, and nobody would maintain it after the co-op ends.
- **Microsoft Access.** Rejected: Python only reaches it on Windows, and Carl develops on a Mac.
- **UVic SQL Server.** Rejected for now because it needs IT approval and ownership. Moving the SQLite tables to it later is straightforward.

## Consequences

- SQLite on a network share is safe for a few occasional editors (Carl, Mark, one or two PMs), not for many writing at once. Revisit if usage grows.
- The `.db` file is a single point of failure, so the app keeps a daily backup (last 30).
- `exit_capacity.py` must move from a top-to-bottom script into functions the GUI and terminal both call.
- FMIS's default 0 capacity is not a count. The first import marks visited rooms explicitly, and after that a saved site count marks a room visited.
- Power BI reads SQLite only through an ODBC driver, so the results workbook stays as the Power BI feed for now.
- Open for the December handover: after Carl leaves, whether FMIS or the app is the source of truth for room capacity, and who runs the exports.
