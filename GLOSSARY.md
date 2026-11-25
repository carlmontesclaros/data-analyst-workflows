# UVic Facilities Space and Exiting Capacity

Room capacities and floor exiting capacity for UVic buildings, checked against the BC Building Code 2024 to answer: "if a room's capacity goes up, can the floor's exits still carry everyone?"

## Capacity

**Registrar capacity**:
The number of students OREM (Office of the Registrar) schedules into a room. OREM's number, not Facilities'.
_Avoid_: capacity (unqualified), OREM count

**Room capacity**:
The current accepted number of people for a room. It is never final: a site count sets it, a PM can change it, and it falls back to the per code load until the room is visited.
_Avoid_: counted capacity, Capacity (Occupants), occupancy

**Capacity source**:
Where a room capacity came from: `site count` (counted on a site visit), `PM change`, or `per code` (not visited yet).
_Avoid_: load source, basis

**FMIS capacity**:
The number FMIS holds for a room. It's kept for comparison and flagged when it disagrees, but it's never used as a room capacity.
_Avoid_: FMIS count, official capacity

**Visited room**:
A room whose capacity has been counted on a site visit. A 0 on a visited room means nobody fits; a 0 on any other room means nothing, because FMIS shows 0 by default. A room stays visited after a PM change: visited says it was counted at some point, the capacity source says where today's number came from.
_Avoid_: counted room, surveyed room, verified room

**Capacity change**:
One recorded change to a room capacity: old value, new value, who, when, and why. The changes together make up the room's history.
_Avoid_: edit, override, update

**Per code load**:
The number of people the building code assigns a room from its area and room type (area ÷ m² per person, rounded up).
_Avoid_: code capacity, area-based capacity, Capacity (per code)

**Occupant load**:
The number of people counted toward a zone when checking its exits: each in-scope room's capacity, plus any people sent in through a link door.
_Avoid_: headroom, demand, population

**Exit capacity**:
The number of people a zone's exits can carry under the code's width and 50% rules.
_Avoid_: egress capacity, exiting width, headroom

**Missing room**:
A room that has a room capacity or history in the app but is no longer in the latest space report (renamed or demolished). It is kept and flagged, never dropped.
_Avoid_: orphan, deleted room

**Capacity check**:
A what-if on a room capacity: the proposed number compared with the room's per code load, and the zone's occupant load with that number compared with its exit capacity. Nothing is saved; the result goes to an editor as a summary.
_Avoid_: simulation, preview, request

**Needs justification**:
A room capacity above the room's per code load. Not refused: the code allows it when the higher number can be shown (fixed seats, a posted sign), so an editor has to look into it.
_Avoid_: over capacity, not allowed, fail

## People

**Editor**:
A person allowed to change room capacities, exits and code factors. Editors are named by other editors; everyone else is a viewer.
_Avoid_: admin, admin rights, supervisor

**Viewer**:
Anyone who can open the app but not change it. A viewer can look up rooms and floors and run capacity checks.
_Avoid_: normal user, guest, read-only user

## Code

**Code factor**:
A number taken from the building code that the calculation depends on: m² per person by room type, mm per person and minimum width by exit type, or a rule setting. When the code changes, these change.
_Avoid_: config, settings, constants

## Sources

**FMIS**:
UVic's facilities management system and the official record of every room. Most rooms in it show a capacity of 0 because nobody had counted them.

**Space report**:
An export of rooms from FMIS: property, floor, space, area and sub-category. It supplies the list of rooms.
_Avoid_: master, database, FMIS export (when the room list is meant)

**FMIS upload**:
The file of room counts Carl sends to FMIS's system admin (the app's Export for FMIS button). The count goes in `OccupantsTotal` only, and only rooms counted on site are included. The admin loads it into FMIS (the FMIS capacity import) so the official record holds real counts.
_Avoid_: FMIS capacity import (for the file Carl sends)

## Places

**Zone**:
The area whose occupant load is checked against its own exits: a whole floor, one wing of a floor, or a group of wings (for example A+C+D) when those wings' exits are recorded separately. A room zone makes a zone the same way a wing does.
_Avoid_: egress zone, section

**Wing**:
A lettered part of a building (A, B, ...), taken from the leading letters of the room number. It places a room in a zone unless the room has a room zone.
_Avoid_: block, side

**Room zone**:
A name (WEST) an editor gives a room whose part of the floor its wing doesn't describe. It wins over the wing, and exits name it as they name a wing. Most rooms have none.
_Avoid_: zone override, sub-wing
