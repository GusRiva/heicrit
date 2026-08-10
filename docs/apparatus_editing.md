# Apparatus Editing

This is a user guide to the main HeiCrit workflow: opening a project and creating, editing, deleting, and reordering critical-apparatus entries. For the Synoptic Map Editor (a separate sub-feature for editing witness alignment), see [`synopse_editing.md`](synopse_editing.md). For the underlying XML data model, see [`data.md`](data.md).

---

## Opening a project

**File → Open Project** (or the folder icon in the toolbar). Pick a directory containing `apparatus/`, `texts/`, and `synopses/` subfolders (see the README for the expected layout).

- If the project has more than one apparatus file, you'll be asked which one to open.
- If the apparatus file's declared synoptic map can't be resolved and the project has more than one candidate synoptic map, you'll be asked which one to use.
- A loading overlay shows progress through each step (reading files, parsing the apparatus, loading witness mappings, processing the synoptic map, generating the main text, building the interface).

Once loaded, the project opens as a tab with three panels: **Main Text** (left), **Critical Apparatus** (right), and **Location Details** (bottom of the apparatus panel).

---

## The three panels

- **Main Text** — the Leithandschrift (base witness), continuously readable. Each location that has an entry point in the synoptic map shows a small marker: **orange** if no apparatus entry exists there yet, **blue** if one does.
- **Critical Apparatus** — the classical apparatus display: one entry per location, in order, formatted lemma] reading witness-sigla. Locations with multiple entries show them stacked as subentries.
- **Location Details** — shows the currently active location: one row per witness, in witness order, with that witness's text at this point (the "Synoptic Comparison"). This is where you click words to build lemma/reading selections.

Click any entry in the Critical Apparatus panel to make it active and load its Location Details.

---

## Navigating entries

- **← Previous / Next →** buttons step through apparatus entries in verse order; the counter shows position (e.g. `3 / 12`).
- **Go to:** type a location/verse number and press **Go** or **Enter**.
- Clicking a marker in the Main Text also jumps to that location's details.

---

## Creating a new entry

1. Click **New Entry** (it becomes **Finish**, and a reading-group dropdown appears) — or press **N** on the keyboard (ignored while typing in a note or other text field, and while editing an existing entry).
2. In the Location Details panel, click words to build your selection:
   - The **lemma** group is selected first (words from the base-text row only) — highlighted **green**.
   - Switch to a reading group via the dropdown, the **+ New reading group** option, or press **1**–**9** on the keyboard (**0** switches back to lemma). Each reading group gets its own highlight color (reading-1 orange, reading-2 purple, reading-3 blue, …).
   - Click words from any other witness row to add them to the active reading group. You can select from more than one witness in the same group if they share the same reading.
   - **Ctrl/Cmd+click** a word to fill in every word between it and the farthest already-selected word in that same row — a quick way to extend a multi-word selection without clicking each word individually.
   - To mark an addition or omission, select a **gap position** instead of a word (click between two words) on the empty side.
3. The variant type is auto-detected from the shape of your selection — no need to choose it manually:

   | Lemma selection | Reading selection | Variant type |
   |---|---|---|
   | word(s) | word(s) | Substitution |
   | gap | word(s) | Addition |
   | word(s) | gap | Omission |

   (Transposition is the exception — see below; it's chosen manually.)
4. Click **Finish** to save. If the selection is invalid (e.g. a reading group with no tokens, or a lemma spanning more than one location), an error message explains what to fix — you stay in creation mode until it's resolved.

A new entry is inserted into the file in the correct verse position automatically, even if you create it out of order (e.g. a verse-5 entry after verse 6 already exists).

### Transpositions

For a reading where witnesses reorder words rather than substitute/add/omit them:

1. Select the lemma tokens (base-text words involved), in any order.
2. Switch to a reading group and choose **Transposition** from the variant-type dropdown (only available in creation mode, for non-lemma groups).
3. Click each witness's corresponding tokens **in order** — witness token #1 pairs with lemma token #1, #2 with #2, and so on. Small numbered badges appear under tokens as you click, showing this correspondence. Every witness you select from in this group must contribute exactly as many tokens as the lemma has.
4. Witnesses that share the *same* transposition pattern can be selected together in one reading group — they'll be recorded as one shared link per position rather than duplicated per witness.

---

## Editing an entry

Select the entry (in the Critical Apparatus panel or via navigation) and click **Edit Entry**. Adjust the token selection the same way as creating an entry, then click **Finish** (the button relabels, same as creation) to save, or navigate away to cancel.

Two kinds of entries can't be edited here (yet): **transpositions**, and entries whose adopted reading was manually overridden. Clicking Edit Entry on one shows an explanation instead of entering edit mode.

---

## Deleting an entry

Select the entry and click **Delete Entry** (hidden for placeholder locations and for entries with a manually overridden adopted reading — but unlike editing, transpositions *can* be deleted). You'll be asked to confirm — this can't be undone.

---

## Reordering entries within a verse

If a location has more than one entry, drag by the **⋮⋮** handle to reorder them. This is purely about *your* editorial ordering when multiple entries share one verse.

---

## Adding editorial notes

Each reading has a small **+** area next to it. Click it and type a note; **Ctrl/Cmd+I** toggles italics within the note. A checkmark save button appears while the note is focused — click it, or simply click elsewhere, to save.

---

## Saving and files

Entry creation, editing, deletion, reordering, and notes all save directly to the apparatus XML file as you perform them — there's no separate "save project" step for apparatus data.
