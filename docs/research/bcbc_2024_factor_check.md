# BCBC 2024 check of the app's code factors and rulings

Checked 2026-10-20 against the official text: `bcbc_2024_web_version_revision2.pdf` (the official PDF, not in the repo), BC Building Code 2024, Book I, Revision 2. Page numbers below are **PDF pages** with the printed page in brackets, e.g. "p. 329 [3-236]". "Div B" = Division B, Part 3 unless it says otherwise.

What was compared: `capacity_egress_app/config/*.csv`, `exit_calc.py`, `egress.py`, `README.md`. Nothing in the code, CSVs, README or database was changed.

## Summary (plain English)

1. **The numbers are right.** Every m² per person we use (classroom 1.85, lab 4.6, office 9.3, 0.95) and every mm per person (6.1 / 8 / 9.2) matches the BCBC 2024 tables word for word.
2. **The minimum widths are right** (doorway 850, stairs 900 / 1100). When this check was written, the app README "Method" step 9 said doorways fail "under 800 mm" (the old 2018 number). The CSV and the code already used 850, and the README has since been fixed to 850.
3. **The 50% rule formula is right.** `min(total, 2 × (total − largest))` gives exactly the biggest load the code allows. I brute-force checked 4,000 random exit sets against the literal wording: 0 mismatches.
4. **Open stairs not counted as exits is right.** An exit must be fire separated (3.4.4.1.(1)). None of the exceptions fit an open interior stair. Mark still has to confirm it for Turpin S5.
5. **Rounding (up for load, down for persons) is fine.** The code says nothing about rounding. Rounding persons down is just the maths of "width ≥ load × mm per person".
6. **Measuring only the stair door is a problem.** The code gives the door 6.1 mm per person and the stair 8.0 or 9.2. The exit can't carry more people than its narrowest part. An 88 cm door holds 144 people. A 110 cm stair behind it holds only 137. **Measure both and use the smaller.**
7. **Link doors between wings have no direct code basis.** If there's no firewall, the two wings are one floor area and the link door isn't an exit at all. If there is a firewall, it's a horizontal exit, and that has its own rules. Our "even split" is a supervisor assumption. It isn't code.
8. **The "needs justification" label has the code backwards.** The code lets a room be designed for **more** people than the table. It's a **lower** number than the table that needs proof ("unless it can be shown..."). Both cases need a posted sign (3.1.17.1.(2)).
9. **A few mappings aren't the closest table row.** Study space, dining and bookstore use 0.95. That's safe because it counts more people. Lounges (1.85) and kitchens (9.30) are left out, but the table gives them a load, so leaving them out undercounts. It's small.
10. **For Mark:** open stairs (S5), whether wings with a link door are one floor area, posted signs for site counts, and whether any floor is an interconnected floor space (an atrium-type opening through floors), where the stair widths *would* have to add up.

## Table

| Item | Ours | Code says | Verdict | Source |
|---|---|---|---|---|
| classroom | 1.85 m²/p | classrooms 1.85 | AGREE | Table 3.1.17.1., p. 198 [3-105] |
| lab | 4.6 | laboratories in schools 4.60 | AGREE | same |
| office | 9.3 | offices 9.30 | AGREE | same |
| non-fixed | 0.95 | space with non-fixed seats **and tables** 0.95 (non-fixed seats only = 0.75) | AGREE (number), the name is loose | same |
| class labs 2.1/2.2 → classroom | 1.85 | laboratories in schools 4.60 | Safe (more people), not the closest row | same |
| study 5.2 / 14.4 → non-fixed | 0.95 | reading or writing rooms or lounges 1.85 | Safe, not the closest row | same |
| food 7.1 → non-fixed | 0.95 | dining, beverage and cafeteria 1.20 | Safe, not the closest row | same |
| bookstore 8.1 → non-fixed | 0.95 | mercantile 3.70 / 5.60 | Safe, not the closest row | same |
| lounges 14.3 excluded | 0 | lounges 1.85 | DISAGREE (undercounts) | same |
| kitchens 7.2 excluded | 0 | kitchens 9.30 | DISAGREE (undercounts, small) | same |
| doorway | 6.1 mm/p | 6.1 doorways, corridors, ramps ≤ 1 in 8 | AGREE | 3.4.3.2.(1)(a), p. 328 [3-235] |
| stairs | 8.0 (rise ≤ 180, run ≥ 280) | 8 mm, same test | AGREE | 3.4.3.2.(1)(b) |
| stairs_steep | 9.2 | 9.2 other stairs, ramps > 1 in 8 | AGREE | 3.4.3.2.(1)(c) |
| ramp | not in CSV | 6.1 (≤ 1 in 8) / 9.2 (> 1 in 8) | AGREE with README plan | 3.4.3.2.(1)(a),(c) |
| min doorway | 850 | 850 | AGREE (README step 9 said 800 then; fixed since) | Table 3.4.3.2.-A, p. 329 [3-236] |
| min stairs | 900 / 1100 | 900 (≤ 2 storeys above / 1 below exit level), else 1100 | AGREE | same, Notes (1)(2) |
| min ramp / exit corridor | 1100 (README) | 1 100 / 1 100 | AGREE (not checked by app) | same |
| 50% rule | min(total, 2(total − largest)) | each exit counts for at most half the required width | AGREE | 3.4.3.2.(7), p. 329 [3-236] |
| one exit → capacity 0 | 0 | 50% rule only "if more than one exit is required" | Safe; wrong only for small floors that may have 1 exit | 3.4.3.2.(7), 3.4.2.1.(2) |
| stairs not cumulative | per floor | need not be cumulative, except (5) balconies, (6) interconnected floor space | AGREE, exception (6) not checked | 3.4.3.2.(4)–(6), p. 328–329 |
| open stairs not exits | not counted | every exit fire separated ≥ 45 min | AGREE | 3.4.4.1.(1), p. 330 [3-237]; Div A 1.4.1.2. |
| door vs stair | door only | each part of the exit has its own factor | DISAGREE (can overstate) | 3.4.3.2.(1), (8) |
| link doors | ceil(load/exits), capped | no rule for doors between wings of one floor area | CAN'T CONFIRM (assumption) | 3.4.3.1.(2), 3.4.1.6., 3.4.6.10., Div A "horizontal exit" |
| rounding | ceil load, floor persons | silent | AGREE (our choice, safe) | 3.1.17.1., 3.4.3.2.(1) |
| min exits | 2, flag fewer | 2, or 1 for small floors (≤ 2 storeys, ≤ 60 people, area/travel limits) | AGREE | 3.4.2.1.(1)–(3), p. 324–325 |
| site counts | used when present | "unless it can be shown ... fewer persons" + posted sign | AGREE with conditions; "needs justification" label is backwards | 3.1.17.1.(1)(c), (2), p. 197 [3-104] |

---

## a) m² per person (Table 3.1.17.1.)

Code (Table 3.1.17.1., p. 198 [3-105]), the rows that matter:

> space with non-fixed seats 0.75 · space with non-fixed seats and tables 0.95 · classrooms 1.85 · reading or writing rooms or lounges 1.85 · dining, beverage and cafeteria space 1.20 · laboratories in schools 4.60 · offices 9.30 · mercantile ... 3.70 / other storeys 5.60 · kitchens 9.30 · storage 46.00

- **classroom 1.85, lab 4.6, office 9.3: AGREE.** Exact match.
- **non-fixed 0.95: AGREE on the number.** It's the "non-fixed seats **and tables**" row. A room with chairs and no tables is 0.75 (more people). Worth renaming to `non-fixed seats and tables` so nobody uses it for a chairs-only hall.
- **Research labs (3.1, 3.2) → 4.6.** The row says "laboratories in schools". A university research lab isn't obviously a "school" lab. But "manufacturing or process rooms" is also 4.60, so the number doesn't change. AGREE on the number.
- **Class labs (2.1, 2.2) → classroom 1.85.** The table row for labs is 4.60. 1.85 counts more people, so it's on the safe side. It's a supervisor ruling, fine as is.
- **Study space (5.2, 14.4) at 0.95.** Closest row: "reading or writing rooms" 1.85. Ours is safer.
- **Food (7.1) at 0.95.** Closest row: dining 1.20. Ours is safer.
- **Bookstore (8.1) at 0.95.** Closest row: mercantile 3.70 / 5.60. Ours is much safer, possibly too strict.
- **Lounges (14.3) excluded. DISAGREE.** The table gives lounges 1.85. Excluding them undercounts. `egress.py` already says it's a project decision, not code.
- **Kitchens (7.2) excluded. DISAGREE, small.** The table gives 9.30.
- **Storage / service rooms excluded.** The table gives storage 46.00, so it's a tiny undercount. Washrooms, corridors and mechanical rooms have no row. Leaving them out is normal practice, but the code text doesn't say so (CAN'T CONFIRM).
- **Fixed seats (6.2, 15.1).** The code says to use the seat count (3.1.17.1.(1)(a)), not area. The `needs_review` note already says this.
- **Day care (19.1).** `category_map.csv` calls it a care occupancy (18.4 mm/p). **That's wrong.** Article 3.1.2.8.(1), p. 147 [3-54]: "A daycare facility for children shall be classified as a Group A, Division 2 assembly occupancy." So the normal 6.1 / 8 / 9.2 factors apply. Health services (13.1) could still be care or treatment. That needs checking.
- **More than one use:** 3.1.17.1.(4) says a room used for different things at different times takes the factor that gives the **most** people.

## b) mm per person

3.4.3.2.(1), p. 328 [3-235]:

> a) 6.1 mm per person for ramps with a slope of not more than 1 in 8, doorways, corridors and passageways,
> b) 8 mm per person for a stair consisting of steps whose rise is not more than 180 mm and whose run is not less than 280 mm, or
> c) 9.2 mm per person for i) ramps with a slope of more than 1 in 8, or ii) stairs, other than stairs conforming to Clause (b).

- doorway 6.1, stairs 8.0, stairs_steep 9.2: **AGREE.**
- ramp: **AGREE** with the README plan: 6.1 up to 1 in 8, 9.2 if steeper. Add it as a `width_factors` row. The dropdown value `ramp (accesibility)` doesn't match anything yet.
- These factors cover assembly, residential, business, mercantile and industrial occupancies. Care / treatment / detention use 18.4 (3.4.3.2.(2)). Group A Division 4 (stadiums) uses 1.8 / 2.4 (3.4.3.2.(3)).
- Side note: 3.4.6.8.(1)–(2), p. 336 [3-243], requires every new stair to have run ≥ 280 and rise 125–180. So `stairs_steep` should only turn up in older stairs that don't meet today's rules.

## c) Minimum widths (Table 3.4.3.2.-A, p. 329 [3-236])

For Group A, B-1, C, D, E, F: exit corridors and passageways **1 100**, ramps **1 100**, stairs **900** (Note 1: serving ≤ 2 storeys above or ≤ 1 storey below the lowest exit level) / **1 100** (Note 2: more than that), doorways **850**.

- doorway 850, stairs 900 / 1100, ramp 1100, corridors 1100: **AGREE.**
- **Was a stale doc (fixed):** app README "Method" step 9 said "doorway under 800 mm fails". The CSV and database use 850, and the README now says 850 too.
- The app checks the stair minimum only when the stair itself is measured. Where it measures the door instead (see g), the stair's own 900 / 1100 minimum is never checked.

## d) 50% rule (3.4.3.2.(7))

> 7) If more than one exit is required, every exit shall be considered as contributing not more than one half of the required exit width. (p. 329 [3-236])

**What it means in plain words:** work out how much exit width the floor needs. When you add up the exits, no single exit can count for more than half of that. It's a cap on how much one exit gets credit for. It does **not** say every exit must be able to take half the people on its own.

**The literal check** for a load L: add up `min(exit persons, L ÷ 2)` over all exits. The total must be at least L.

**Ours** turns that around and finds the biggest L that passes: `min(total, 2 × (total − largest))`. Only the largest exit can ever hit the cap. Two exits both over L ÷ 2 would pass anyway. So the answer is either the total, or twice what the other exits add up to.

- Brute-force check (scratch script, 4,000 random sets of 2–5 exits): **0 mismatches.** Our test values also match: [151,144,144] → 439, [151,144] → 288, [400,100] → 200, [1000,100,100] → 400.
- **Verdict: AGREE.**
- One exit → 0: the 50% rule only applies "if more than one exit is required". A floor that may legally have one exit (3.4.2.1.(2), see j) would really have that exit's full capacity. Giving it 0 is safe, and the floor gets flagged anyway.
- Intent (NRC intent statement for 3.4.3.2.(7), NBC 2005 archive, wording may differ in 2020): "To limit the probability that an excessive portion of the required exiting capacity will be concentrated at one location ... if the exit becomes obstructed or inaccessible". https://codes-guides.nrc.ca/IA/05NBC/nbc05ei002614.html
- Official BC backing that it applies to exit stairs: Building Code Appeal Board decision 1715 (2012) ruled that the exits from a suite "must conform to Sentence 3.4.3.2.(7)". https://www2.gov.bc.ca/gov/content/industry/construction-industry/building-codes-standards/building-code-appeal-board/building-code-appeal-board-decisions/bcab-1715
- Related rule we don't check: 3.4.1.2.(2), p. 323 [3-230]. When exits merge, the merged exits together can't give more than 50% of the required width.

## e) Stairs not cumulative across floors

> 4) Except as required by Sentences 3.4.3.2.(5) and (6), the required exit width need not be cumulative in an exit serving 2 or more floor areas located one above the other. (p. 328 [3-235])

- **AGREE.** Each floor is checked on its own against the same stair. That's what (4) allows.
- **Exception (5):** an exit stair in an assembly hall or theatre serving more than one balcony. Not relevant to classrooms.
- **Exception (6):** exit stairs serving an **interconnected floor space** (floors joined by open holes with no closures, e.g. an atrium) built under 3.2.8.3.–3.2.8.8. Their widths **must add up**, unless (a) the stairs have ≥ 0.3 m² of treads and landings per occupant, or (b) there's a protected floor space with ≥ 0.5 m² per occupant on each floor. Note A-3.4.3.2.(6), p. 474 [3-381]: "ensures that egress facilities allow for the simultaneous evacuation of all portions of an interconnected floor space."
- **CAN'T CONFIRM for UVic buildings.** The app doesn't know which floors are interconnected. Turpin S5 (an open stair between floors) is the kind of opening that can make one. Small cases are exempt under 3.2.8.2.(6), p. 292 [3-199]: first storey + one storey above or below, sprinklered, Group A-1/2/3, D, E, F-2/3. **Ask Mark.**

## f) Open stairs

Code:
- Div A 1.4.1.2. definition, p. 46 [1-17]: "*Exit* means that part of a means of egress, including doorways, that leads from the floor area it serves to a separate building, an open public thoroughfare, or an exterior open space ..."
- *Floor area*, p. 47 [1-18]: "... not including exits, vertical service spaces, and their enclosing assemblies." So an exit sits **outside** the floor area.
- Note A-1.4.1.2.(1) "Exit", p. 64 [1-35]: "Exits include doors or doorways leading directly into an exit stair or directly to the outside."
- 3.4.4.1.(1), p. 330 [3-237]: "Except as permitted by Sentences (2), 3.3.5.4.(3), 3.4.4.2.(2) and 3.4.4.3.(1), every exit shall be separated from the remainder of the building by a fire separation having a fire-resistance rating ... not less than 45 min".
- 3.2.8.1.(2), p. 291 [3-198]: "The penetration of a floor assembly by an exit ... shall conform to the requirements of Sections 3.4."

The exceptions to 3.4.4.1.(1):
- (2) caps the rating at 2 h.
- 3.3.5.4.(3) is mechanical storage garages.
- 3.4.4.2.(2) is one exit through a lobby.
- 3.4.4.3.(1) is exterior exit passageways.

**None of them is an open interior stair.** The heritage-building table (Div A Table 1.1.1.1.(5), item 24, p. 34 [1-5]) relaxes the *rating* in older heritage buildings, but it still requires a separation. The open-stair relaxations in that table (item 14) are about 3.2.8 (interconnected floor space), not about making the stair an exit.

**Verdict: AGREE.** An unenclosed stair is access to exit (the route to an exit), not an exit. The `open_stairs_count = no` default was right on the code text. Mark should still confirm S5, because only a site review can tell whether a stair is really enclosed. (Later the same day Carl decided open stairs count as exits for screening, so the app now ships with `open_stairs_count = yes`; see the app README's Decisions.)

If S5 ever were counted, 3.4.6.9.(2), p. 337 [3-244], has extra rules for **curved** exit flights: a handrail on each side, minimum run 240 mm, and an inside radius at least 2 × the stair width.

## g) Door vs stair width

There's **no single sentence** that says "the narrower part governs". But it follows from the text. 3.4.3.2.(1) sets the required width by type ("doorways" 6.1, "stair" 8 or 9.2). An exit made of a door plus a stair has to meet both. 3.4.3.2.(8) and Table -A set a separate minimum for each part. So the exit's capacity is the **smaller of** door persons and stair persons.

- **Our practice (door only): DISAGREE.** It can overstate. Example: an 88 cm door = 144 people. A 110 cm stair behind it = 1100 ÷ 8 = 137 people, so the stair governs. A 121 cm stair (151) wouldn't.
- Fix in the field: measure the door **and** the narrowest stair width (between handrails). Record both, and the app uses the smaller. Also check the stair against 900 / 1100.
- Handrails: 3.4.3.3.(4), p. 330 [3-237], lets handrails project up to 100 mm into the required width. Note A-3.4.3.4., p. 474 [3-381]: "Clear width is intended to be measured from a line tangent to horizontal protrusions such as handrails." Measuring at the handrail (what Carl does) is the safe reading. **AGREE.**
- Door swing: 3.4.3.3.(2) says a swinging door can't cut the width of a stair or landing below 750 mm. 3.4.3.3.(3) says an open door can't reduce the required exit width.

## h) Link doors between wings

What the code has:
- 3.4.3.1.(2), p. 328 [3-235]: "the required exit width shall be cumulative if 2 or more exits converge." That's about exits **merging** (e.g. two stairs into one passageway). It isn't about a door between two parts of a floor.
- *Horizontal exit*, p. 49 [1-20]: "an exit from one building to another by means of a doorway, vestibule, walkway, bridge or balcony." A *firewall* "subdivides a building or separates adjoining buildings" (p. 47 [1-18]). So a door is a horizontal exit only if the wings are split by a firewall.
- Horizontal exits: no more than half the required exits (3.4.1.6.(1), p. 323 [3-230]). The floor on **each side** must hold both floors' occupants at 0.5 m² per person (3.4.6.10.(1), p. 337 [3-244]). No stairs in a horizontal exit (3.4.6.10.(4)).

What that means for us:
- **No firewall between the wings (likely at Turpin floor 1).** The wings are one floor area. The link door is just a door inside it, not an exit. The code check is the **whole floor**: all rooms against all real exits, with the 50% rule over all of them. Right now the app counts the link door as an exit for the sending wing and pushes people into the receiving wing. The code doesn't do either.
- **Firewall between the wings.** The door is a horizontal exit. The code doesn't add incoming people to the receiving wing's exit width. It checks refuge space (0.5 m² per person) and the "≤ half the exits" limit.
- **Verdict: CAN'T CONFIRM.** The even split is an assumption (a supervisor decision). It may be a reasonable screening model, but it isn't code text.
- **Suggestion:** for connected floors with no firewall, also run the floor as one zone (link door left out) and show both. Ask Mark whether Turpin A/B on floor 1 are split by a firewall.

## i) Rounding

The code says nothing about rounding in 3.1.17. or 3.4.3.

- **Occupant load rounded up: AGREE.** "Not less than that determined from Table 3.1.17.1." (3.1.17.1.(1)(c)) points to rounding up, and you can't have part of a person. Summing each room rounded up gives a slightly higher floor total than rounding the floor sum once. That's safe.
- **Persons per exit rounded down: AGREE.** This is plain maths, not just a cautious choice. 3.4.3.2.(1) needs width ≥ load × mm per person, so the largest whole load is floor(width ÷ mm per person).

## j) Minimum number of exits

3.4.2.1., p. 324–325 [3-231–232]:

> 1) Except as permitted by Sentences (2) to (4), every floor area intended for occupancy shall be served by at least 2 exits.
> 2) A floor area in a building not more than 2 storeys in building height, is permitted to be served by one exit provided the total occupant load served by the exit is not more than 60, and a) [not sprinklered] the floor area and the travel distance are not more than the values in Table 3.4.2.1.-A, or b) [sprinklered] the travel distance is not more than 25 m, and the floor area is not more than the value in Table 3.4.2.1.-B.

The one-exit limits:
- Group A: 150 m² and 15 m travel if not sprinklered; 200 m² if sprinklered.
- Group D (offices): 200 m² and 25 m if not sprinklered; 300 m² if sprinklered.
- 3.4.2.1.(3): for Group B or C, the one exit must be an exterior door no more than 1.5 m above the ground.

**Verdict: AGREE** with flagging fewer than 2 exits for review. The app can't check the one-exit exception (it doesn't know sprinklers, travel distance, or building height), so "review" is the right answer. Remember the code counts exits **per floor area**. Splitting a connected floor into wings (see h) is stricter than the code asks.

## k) Site counts instead of Table 3.1.17.1.

3.1.17.1., p. 197 [3-104]:

> 1) The occupant load of a floor area or part of a floor area shall be based on ... c) the number of persons for which the area is designed, but not less than that determined from Table 3.1.17.1. ..., **unless it can be shown that the area will be occupied by fewer persons.**
> 2) If a floor area or part thereof has been designed for an occupant load other than that determined from Table 3.1.17.1., a permanent sign indicating that occupant load shall be posted in a conspicuous location.

- **Site count lower than per code** (most visited rooms): allowed **only if it can be shown**. The count is the evidence. Then (2) needs a posted sign. **AGREE with conditions.** The app shows these rooms green ("within per code"), but they're the ones the code puts the burden of proof on.
- **Site count or PM request higher than per code:** the code simply allows it ("the number of persons for which the area is designed", with the table as the floor). Then (2) needs a sign, and the exits have to carry it (which the app checks). The amber label "needs justification" is a sensible **project policy**, but the comment in `judge_room` citing 3.1.17.1.(1)(c) for it gets the clause backwards.
- NRC intent for 3.1.17.1.(2) (NBC 2005 archive): "To exempt floor areas from the application of Sentence 3.1.17.1.(1) and allow for another occupant load if certain measures are taken to limit the probability of overcrowding." https://codes-guides.nrc.ca/IA/05NBC/nbc05ei002027.html
- Raising a room above 60 people brings in 3.3.1.5.(1)(b), p. 296 [3-203]: the room needs **2 egress doors**, at least 1/3 of the diagonal apart. The app doesn't check this, and it matters for PM increase requests.

## Things in Section 3.4 (and nearby) that change results and the app doesn't check

- 3.3.1.5.: rooms over 60 people (or over the area / travel limits) need 2 egress doors. Matters for capacity increases.
- 3.4.1.2.(2): merging exits can't give more than 50% of the required width.
- 3.4.1.6.: horizontal exits can be no more than half the required exits.
- 3.4.2.1.(2)–(3): one-exit floors (≤ 2 storeys, ≤ 60 people, area and travel limits).
- 3.4.2.3.: two exits at least half the floor's diagonal apart (9 m rules).
- 3.4.2.4.–3.4.2.5.: travel distance to an exit (30 m; 40 m business; 45 m sprinklered).
- 3.4.3.2.(2): care / treatment / detention at 18.4 mm/p (health services 13.1 unresolved; day care is A-2, not care).
- 3.4.3.2.(6): interconnected floor space, where stair widths add up.
- 3.4.3.3.: width cuts from fixtures, door swing (≥ 750 mm on stairs and landings), handrails (≤ 100 mm).
- 3.4.3.4.: headroom 2 050 mm (doorways 2 030; closers 1 980).
- 3.4.4.1.: the exit's actual fire-separation rating (≥ 45 min, linked to the floor assembly).
- 3.4.4.2.: exits through lobbies (one at most, ≤ 15 m path, ≤ 4.5 m above grade).
- 3.4.4.4.: integrity of exits (openings into exit enclosures).
- 3.4.5.: exit signs.
- 3.4.6.4.: landings at least as wide as the stair.
- 3.4.6.5.: handrails (both sides at ≥ 1 100 mm or on curved flights; within 750 mm of all of the required width).
- 3.4.6.7.–3.4.6.8.: ramp slope; stair rise and run, uniform within 5 / 10 mm.
- 3.4.6.9.: curved exit flights (relevant if S5 ever counts).
- 3.4.6.10.: horizontal-exit refuge area 0.5 m² per person; no steps.
- 3.4.6.11.–3.4.6.16.: door rules (300 mm from a riser, thresholds, swing direction, closers, hardware).
- 3.4.7.: fire escapes.
- 3.7.4. (outside 3.4): washroom fixture counts depend on occupant load, so a capacity increase can change them.

## Sources

- BC Building Code 2024, Book I, Revision 2 (official PDF): https://www2.gov.bc.ca/assets/gov/farming-natural-resources-and-industry/construction-industry/building-codes-and-standards/revisions-and-mo/bcbc_2024_web_version_revision2.pdf (not kept in the repo)
- BC government, BC Building Code 2024 page (BCBC 2024 is based on NBC 2020 with BC changes): https://www2.gov.bc.ca/gov/content/industry/construction-industry/building-codes-standards/bc-codes/2024-bc-codes
- BC Building Code Appeal Board decision 1715 (2012, 50% rule applies to exit stairs): https://www2.gov.bc.ca/gov/content/industry/construction-industry/building-codes-standards/building-code-appeal-board/building-code-appeal-board-decisions/bcab-1715
- NRC intent statements, NBC 2005 (archived; explanatory only, not part of the code): 3.4.3.2.(7) https://codes-guides.nrc.ca/IA/05NBC/nbc05ei002614.html · 3.4.4.1.(1) https://codes-guides.nrc.ca/IA/05NBC/nbc05ei002624.html · 3.4.3.1.(2) https://codes-guides.nrc.ca/IA/05NBC/nbc05ei002617.html · 3.1.17.1.(2) https://codes-guides.nrc.ca/IA/05NBC/nbc05ei002027.html
- No secondary sources (blogs, forums) were relied on.
