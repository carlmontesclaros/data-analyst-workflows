---
status: accepted
date: 2026-10-13
amends: ADR 0001 ("every user can edit everything")
---

# Editors are named by Windows login; everyone else is a viewer

ADR 0001 let everyone who had the app edit everything. Mark's answers to the NFR questions (Mark's written answers to the NFR questions, 2026-10-13) changed that: only trusted people edit, but the planning team (Carolyn and Karine included) and later OREM should be able to open it "for quick review". Carl settled the details on 2026-10-13. There are two roles, **editor** and **viewer** (see `GLOSSARY.md`). The app reads the person's Windows login (their own UVic account, on any PC) and looks it up in an editor list kept in the database. Editors can change room capacities, exits and code factors. Everyone else gets the capacity check screen, which never saves. Editors add and remove other editors on an Editors screen inside the app. Every add and remove goes in the change log, and the last editor can't be removed. The first editors are Mark, Carl, Carolyn and Karine; Mark confirmed this in person on 2026-10-13, replacing his written "only Mark".

## Considered options

- **A shared editor password on a start screen.** Rejected: one password gets passed around, someone has to reset it when it leaks, and nobody on the team should have to manage passwords.
- **A start screen where people pick "editor" or "viewer".** Rejected: it's an honour system.
- **An "owner" role above editors (only Mark manages the list).** Rejected: a third role for four people. The change log shows who added whom.
- **Typing Windows logins into a file or code.** Rejected: nobody maintaining it after the co-op writes code. People who have opened the app once show up on the Editors screen to be ticked.

## Consequences

- **The lock is inside the app only.** The database is one file on the S: drive. Anyone with write access to that folder could open it with another SQLite tool and change it. To-do: ask UVic IT to make the folder read-only for everyone except the editors. Viewers only read, so the app works either way.
- **Hardened 2026-10-14 (security review):** the login comes from Windows (`GetUserNameW`), not the `USERNAME` variable that `getpass.getuser()` reads first, so one `set USERNAME=` command no longer passes as an editor. Every save function in `capacity_db.py` checks the editor list itself (`require_editor`), not only the screens. The folder permissions above are still the only real lock.
- A shared or generic Windows account must never be made an editor, because everyone using it would be one. The Editors screen says so. (Each PM has their own workstation login today.)
- If the editor list is ever empty (a new database, or the first open after this change), the first person to open the app is asked to become the first editor. Carl opens it first after installing.
- The database stays on the S: drive. A SharePoint/OneDrive-synced folder can copy the file mid-save and corrupt it, so the `.db` doesn't move to SharePoint. Exports and the guide can go there.
- Viewer access by a plain web link (OREM included) is future work that starts with asking IT and Mark. Mark's comment on the NFR doc says there will be no outside hosting.
