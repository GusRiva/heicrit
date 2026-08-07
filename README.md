# HeiCrit — Critical Apparatus Editor

HeiCrit is a web-based editor for creating and managing critical apparatus in scholarly digital editions. It reads TEI/XML-encoded witness manuscripts, aligns them through a synoptic map, and provides an interface for recording textual variants in classical apparatus format.

## Key Concepts

- **Leithandschrift** — the base manuscript whose text is displayed as the main text; all apparatus entries are anchored to it.
- **Apparatus entry** — records a point of variation: a lemma (the reading in the base text) and one or more variant readings from other witnesses.
- **Synoptic map** — an alignment table that maps every location in the base text to the corresponding element in every other witness, accounting for lacunae and different pagination.

See [`docs/apparatus_editing.md`](docs/apparatus_editing.md) for a user guide to the main editing workflow, [`docs/synopse_editing.md`](docs/synopse_editing.md) for the Synoptic Map Editor, and [`docs/data.md`](docs/data.md) for a full description of the data model.

## How to Run

```bash
# 1. Activate the virtual environment
source venv/bin/activate

# 2. Install Python dependencies (first time only)
pip install -r requirements.txt

# 3. Start the backend
cd backend && python app.py

# 4. Open the frontend
# Open frontend/index.html in a browser

# 5. Load a project
# Use File → Open Project Directory and select a folder that contains
# apparatus/, texts/, and synopses/ subdirectories.
```

## Architecture

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Backend | Flask (Python) | REST API; parses TEI/XML using the `heipy` library |
| Frontend | HTML / CSS / vanilla JS | Three-panel UI: main text, apparatus, location details |
| Desktop | Electron (optional) | Wraps the web app as a standalone desktop application |

The backend runs on `http://127.0.0.1:5000`. The frontend communicates with it via `fetch` calls to `/api/…` endpoints.

### Key source files

```
backend/
  apparatus.py          Parses apparatus XML; produces structured entry data
  synoptic_map.py       Parses synoptic map XML; aligns witnesses
  routes.py             Flask API routes
  heicrit_pipeline.py   XSLT/Python pipeline that converts witness XML to HTML
  load_functions.py     Relative-path resolution for project file references

frontend/
  app.js                All application logic (tabs, navigation, token selection)
  index.html            UI layout
  styles.css            Styling (classical apparatus look, token highlighting)

docs/
  CLAUDE.md             Developer guide for AI-assisted development
  apparatus_editing.md  User guide to the main apparatus editing workflow
  synopse_editing.md    User guide to the Synoptic Map Editor
  data.md               Complete data model reference
```

## Project Directory Layout (expected)

```
my-edition/
  apparatus/
    edition_app.xml     TEI apparatus file
  texts/
    Witness_A.xml       Leithandschrift text
    Witness_Ba.xml      Other witness texts
    …
  synopses/
    synoptic_map.xml    Alignment table across all witnesses
```
