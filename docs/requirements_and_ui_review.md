# Capacity & Egress App: requirements questions and UI review plan

Prepared for: supervisor meeting + app demonstration
Author: Carl (co-op student, Facilities)
Date: 2026-10-05
Status: draft, answers to be filled in during the meeting

---

## Part 1: Non-functional requirements

Functional requirements say **what** the app does (change a capacity, add an exit). Non-functional requirements say **how well** it has to do it: who can maintain it, who can edit, how much data loss is acceptable, how easy it must be to learn. "Make it maintainable for people without coding knowledge" is a goal; the questions below turn it into requirements I can build and check against.

### Already settled (confirm, don't re-discuss)

| Area | Requirement | Source |
|---|---|---|
| Hosting | Data stays inside UVic systems; no outside hosting | Decision 2026-09-29 |
| Platform | Windows desktop app; one database file on the S: drive | ADR 0001 |
| Users | A few occasional editors: Carl, Mark, 1–2 PMs | ADR 0001 |
| Audit | Every capacity, exit and code factor change logged: old, new, who, when, why | Decision 2026-10-02 |
| Code factors | Changes need a building code clause reference | Decision 2026-10-02 |
| Backup | Copy made each day the app opens; last 30 kept | ADR 0001 |
| Scope | Screening only; results say "review", never "approved" | Project rule |

### Questions

Ranked by how much the answer changes the app. **Bold** = must answer before handover.

**Maintainability and handover**
1. **After December 24, who owns the app?** A name or a role.
2. **What must that person be able to do without editing code?** Tick: load a new space report · add a building's exits · change a code factor · restore a backup · install it on a new computer · fix a broken install. Anything ticked must be a button in the app or a written step.
3. **After December, is the app or FMIS the source of truth for room capacity?** Who runs the capacity export into FMIS, and how often?
4. Is a written guide (one page, screenshots) enough, or do you want a recorded walkthrough too?

**Access and security**
5. **Should everyone with the app be able to edit everything**, including code factors, or only some people (e.g. only Mark changes code factors)?
6. Should the S: drive folder be restricted to the app's users?
7. Is the Windows login + a nickname enough to identify who made a change?

**Install and IT**
8. **Is installing Python on PMs' computers allowed, or does UVic IT need to approve or do it?**

**Reliability**
9. If the database file gets corrupted, is losing up to a day of changes acceptable (the current daily backup)? Who restores it?

**Usability**
10. How long should a new PM need to learn the app: no training, a one-page guide, or a short session?
11. Is a desktop window acceptable, or will people expect something in a browser?

**Audit and scale**
12. How long must the change log be kept, and does anyone outside Facilities (Registrar, auditors) need to see it?
13. How many buildings do you expect in it by the end of term, and will two people ever edit at the same time?

### Answers

Answered by Carl, 2026-10-05 (the rest went to the supervisor in the NFR questions document, reply due Friday, October 9):

| Topic | Answer | Change to the app |
|---|---|---|
| Source of truth | **The app.** FMIS has no real occupancy data. Carl's site counts go into the app, and with the systems admin they're uploaded to FMIS one way. After that, changes are made in the app and exported again, never edited in FMIS directly | None; the capacity export already serves the upload. Open question closed |
| Python install / IT | Carl has admin rights and installs Python on the workstations himself | None |
| S: drive access | Everyone can open the app; the folder isn't restricted | None |
| Change log retention | Keep it forever (a few thousand rows a year) unless a UVic records policy says otherwise | None |
| Scale | Small, but several people must be able to use it at once | Built 2026-10-05: wait when busy, refuse stale saves, auto-refresh, Refresh button (7 tests) |

Answered by Mark, 2026-10-13 (Mark's written answers, with 3 comments), with Carl's follow-up decisions the same day:

| Topic | Mark's answer | Change to the app |
|---|---|---|
| Owner after December | Mark uses it most at first; may move to others later (e.g. drafting technicians) | Guide written for a non-coder owner |
| Tasks without code | Ideally all: load a space report, add exits, change code factors, restore a backup, install, fix an install | Each one is a button or a written step in the guide |
| Guide | A written guide with screenshots at minimum; a video if there's time. A one-page guide for a new PM would be ideal | One-page guide + full guide |
| Who edits | "Only Mark should be able to edit app. However, the app should be accessible to others for quick review." Comment: anyone in the planning team should be able to access (Carolyn and Karine included) | **Editors and viewers** ([ADR 0003](adr/0003-editors-by-windows-login.md)). Editors: Mark, Carl, Carolyn, Karine (Mark confirmed in person, 2026-10-13: not only him). Everyone else gets the capacity check screen |
| Login + nickname to identify changes | Not necessary | Nobody types anything: the Windows login is read automatically and decides editor or viewer |
| Data loss | "Our sharepoint site updates on its own multiple times per hour." | The `.db` stays on the S: drive (a synced folder can corrupt SQLite). Ask IT whether the S: drive is backed up |
| Learning time | A one-page guide | Capacity check screen designed to need only that |
| Desktop or web | Either. Comments: "There will be no outside hosting"; SharePoint "might be good too" | Desktop now. Web link for viewers (OREM included) is future work, starting with IT |

---

## Part 2: UI review using the 7 design principles

**Design decision:** the app's interface is reviewed against Don Norman's seven fundamental principles of interaction design (*The Design of Everyday Things*). Each principle gets an honest check of the current app, the known gaps, and what to watch for in the demo. A principle that doesn't apply is left out rather than forced.

### Current app against each principle

| Principle | What it means | What the app does now | Known gaps |
|---|---|---|---|
| **Discoverability** | You can tell what actions are possible just by looking | All actions are visible buttons, grouped above the list they act on | The window opens **empty** until a building is picked, with no hint what to do first. Double-click on a room to change capacity is hidden. The search box doesn't say it takes a room **or** a building |
| **Feedback** | Every action gets a visible response | Live preview of the floor result while typing a capacity; status bar message after a save; error boxes say what's wrong | A save is only confirmed in the status bar (easy to miss). No busy cursor while the campus recalculates (about 1 s) |
| **Conceptual model** | The screen matches how users think about the problem | Building → floor → zones → rooms → exits, in that order, top to bottom. Terms follow the glossary (room capacity, per code load, occupant load vs exit capacity) | Column headers are raw database names (`zone_wing`, `total_load`, `load_used`, `in_scope`), which is my model, not a PM's |
| **Affordances** | What a control can do is clear from its form | Standard Windows controls: buttons, dropdowns, text boxes, lists | Fine as is; standard controls are the right choice here |
| **Signifiers** | Marks that show where and how to act | Zone rows coloured red / green / grey (same as the workbook); missing rooms in red text; "Clause (required)" label | No colour legend. Nothing signals that rows can be double-clicked. Colour alone carries status (also shown as text, which helps) |
| **Mapping** | Controls sit near and match what they affect | Room buttons above the room list, exit buttons above the exit list; clicking a zone jumps to its floor | Clicking a wing's zone doesn't narrow the rooms to that wing |
| **Constraints** | Make wrong actions hard or impossible | Building, floor and exit type are pick-lists, not typed. Width must be 50–500 cm, why and clause are required, property and floor are locked when adding an exit, the first import refuses to run twice | Capacity box accepts any text until the preview says it's not a number (acceptable). Code factors can be changed by anyone (see question 5) |

### Likely fixes after the demo (decide with the feedback, don't build yet)

1. Start screen hint: "Search a room (e.g. B303) or pick a building", instead of empty lists.
2. Plain-English column headers: `zone_wing` → Wing, `total_load` → Occupant load, `load_used` → Load used, `in_scope` → Counted?
3. A small colour legend above the zones list.
4. Save confirmation that's hard to miss (brief pop-up or highlighted row).
5. Busy cursor during recalculation.
6. Clicking a wing's zone filters the rooms to that wing.

### Demo plan

Let the supervisor drive. Give a task, say nothing, and note where they hesitate or ask "where do I...". Hesitation is the finding.

| Task | Principles it tests | What to watch |
|---|---|---|
| 1. "The Registrar wants Turpin B303 to go from 32 to 36. Can it?" | Discoverability, feedback, conceptual model | Do they find search? Do they notice the preview before saving? |
| 2. "Which Turpin floors need review?" | Signifiers, mapping | Do they understand the colours without being told? |
| 3. "Record a new exit on Turpin floor 1." | Discoverability, constraints | Do they find Add exit? Does the form stop a bad width? |
| 4. "Send me Turpin's results as Excel." | Discoverability, mapping | Do they find the export, and does it export only Turpin? |
| 5. "Who changed B303, and why?" | Discoverability, feedback | Do they find Room history? |

Run the demo on a **copy** of the database (or cancel every save), so test changes don't land in the change log.

### Feedback questions (after the tasks)

1. What was the hardest part to find?
2. Was anything on screen you didn't understand (a word, a colour, a number)?
3. Did you trust the result before saving? What would make you trust it more?
4. What would a PM who's never seen it get stuck on?
5. One thing you'd change first?

### Feedback log

| Who | Task | What happened | Principle | Fix? |
|---|---|---|---|---|
| | | | | |
