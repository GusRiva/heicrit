# Synoptic Map Editor

## What is the synoptic map?

The synoptic map (`synoptic_map.xml`) is a TEI XML file that aligns corresponding passages across all witnesses of a text. It lives in the `synopses/` directory of a project. Each `<link>` element in `<standOff>` represents one row of alignment:

```xml
<link n="1" target="a:l_1 ba:l_1 bb:l_1 c:gap_leaf_1 e:left(l_29) f:left(l_199)"/>
```

- `@n` is the row identifier (usually a line number, but can be `titlePart_1`, `gap_after_5`, etc.)
- `@target` is a space-separated list of `prefix:elementId` tokens, one per witness

Each token connects the row to a specific element in that witness's TEI file. If a witness has no corresponding element for a row, it is simply absent from `@target`.

### Cell values

The cell value is the **element ID part** of the `prefix:elementId` token:

| Token in `@target` | Cell shows |
|---|---|
| `a:l_1` | `l_1` |
| `e:left(l_29)` | `left(l_29)` |
| `c:gap_leaf_1` | `gap_leaf_1` |
| absent | (empty) |

Special value forms:
- `gap_*` — marks a lacuna in that witness at this row
- `left(id)` — the alignment falls to the left boundary of element `id`
- `right(id)` — the alignment falls to the right boundary of element `id`

---

## Opening the editor

1. Load a project via the project toolbar (apparatus file).
2. Once the project is loaded, click **Edit Synoptic Map** in the apparatus toolbar.
3. A new **Synoptic Map** tab opens, showing the map as a spreadsheet.

The spreadsheet has one column per witness (ordered as they appear in the `<prefixDef>` elements of the synoptic map file) and one row per `<link>` element.

Column headers show the **editorial siglum** (e.g. A, Ba, Bb) loaded from each witness file. The internal prefix (e.g. `a`, `ba`, `bb`) appears as a tooltip on the header.

---

## Keyboard navigation

| Key | Action |
|---|---|
| **Tab** | Move to next cell (right); wraps to first cell of next row |
| **Shift+Tab** | Move to previous cell (left); wraps to last cell of previous row |
| **Enter** / **↓** | Move to same column in the row below |
| **↑** | Move to same column in the row above |
| **Home** | Jump to first cell of current row |
| **End** | Jump to last cell of current row |
| **Ctrl+D** | Fill down: copy the value from the cell directly above into the current cell |
| **Ctrl+S** | Save the current state of the table to disk |

---

## Adding rows

Click the **+ Add Row** button in the editor toolbar, or press **Tab** from the last cell of the last row. A new empty row is appended at the bottom and the `n` cell is focused automatically.

Fill in the `n` value first (the row identifier), then Tab through the witness columns.

---

## Saving

Click the **Save** button in the editor toolbar, or press **Ctrl+S** from any cell.

The save operation:
- Preserves the entire `<teiHeader>` and all `<prefixDef>` elements unchanged
- Reconstructs the `@target` attribute for each `<link>` by joining `prefix:value` for every non-empty cell, in witness order
- Removes `<link>` elements whose `@n` was deleted (rows with an empty `n` cell are skipped)
- Adds new `<link>` elements for rows whose `@n` did not exist before

A status message ("Saved." or an error) appears next to the Save button after the operation completes.

---

## Tips for editing

- **Copy-paste down a column**: click the first cell you want to fill, press Ctrl+D for each row below (or Tab down and repeat).
- **Batch fill**: paste an ID into the top cell, then hold Ctrl and press D repeatedly while pressing ↓ between each press to fill a range quickly.
- **Empty = absent**: leave a cell empty if that witness has no corresponding element at this row. The prefix will be omitted from `@target` on save.
- **Gap rows**: to mark a lacuna, enter a value like `gap_leaf_1` (must match an actual `<gap>` element ID in the witness file).
