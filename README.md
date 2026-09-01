# HeiCrit — Critical Apparatus Editor

HeiCrit is a web-based editor for creating and managing critical apparatus in scholarly digital editions. It reads TEI/XML-encoded witness manuscripts, aligns them through a synoptic map, and provides an interface for recording textual variants in classical apparatus format.

## Key Concepts

- **Base Text** — the base manuscript whose text is displayed as the main text; all apparatus entries are anchored to it.
- **Apparatus entry** — records a point of variation: a lemma (the reading in the base text) and one or more variant readings from other witnesses.
- **Synoptic map** — an alignment table that maps every location in the base text to the corresponding element in every other witness, accounting for lacunae and different pagination.

See [`docs/apparatus_editing.md`](docs/apparatus_editing.md) for a user guide to the main editing workflow, [`docs/synopse_editing.md`](docs/synopse_editing.md) for the Synoptic Map Editor, [`docs/data.md`](docs/data.md) for a full description of the data model, and [`docs/deployment.md`](docs/deployment.md) for building/packaging the app.

## How to Run

HeiCrit runs as a desktop app via Electron, which wraps the Flask backend and static frontend in one window.

Requires Node.js 24+ and npm (see `.nvmrc` / `package.json`'s `engines` field), and Python 3.12.

```bash
# 1. Fetch the heipy submodule (first time only — requirements.txt installs
#    it via `-e ./heipy`, so this must happen before step 3)
git submodule update --init --recursive

# 2. Set up the Python virtual environment (first time only)
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
deactivate

# 3. Install Node dependencies (first time only)
npm install

# 4. Run it — this launches Electron, which spawns the Flask backend from
#    venv/ automatically and opens the app window
npm run dev

# 5. Load a project
# Use File → Open Project Directory and select a folder that contains
# apparatus/, texts/, and synopses/ subdirectories.
```

## Build the desktop app

Packaging into a distributable installer (Windows/macOS/Linux) is handled by electron-builder:

```bash
npm run pack    # quick unpacked build under dist/, for testing packaging without a full installer
npm run dist    # build an installer under dist/ (for the OS you run it on — see docs/deployment.md)
```

See [`docs/deployment.md`](docs/deployment.md) for prerequisites, CI-based multi-platform builds, and troubleshooting. A website deployment (Docker-based, self-hosted) is planned but not yet implemented — see that same document for the intended design.

Non-technical users can just download a ready-made installer from **https://gusriva.github.io/heicrit/** — no build required.

## Architecture

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Backend | Flask (Python) | REST API; parses TEI/XML using the `heipy` library |
| Frontend | HTML / CSS / vanilla JS | Three-panel UI: main text, apparatus, location details |
| Desktop | Electron, packaged via electron-builder | Wraps the web app as a standalone desktop application — see [`docs/deployment.md`](docs/deployment.md) |

The backend binds to a free port on `127.0.0.1` at startup and reports it to Electron, which passes it to the frontend as the `apiPort` query parameter. The frontend communicates with it via `fetch` calls to `/api/…` endpoints.

### Key source files

```
backend/
  app.py                Flask app entry point; wires up CORS and the routes blueprint
  apparatus.py          Parses apparatus XML; produces structured entry data
  synoptic_map.py       Parses synoptic map XML; aligns witnesses
  routes.py             Flask API routes
  heicrit_pipeline.py   XSLT/Python pipeline that converts witness XML to HTML
  xslt/                 XSLT stylesheets used by heicrit_pipeline.py
  location_resolver.py  Resolves "prefix:location" pointers against witness fragments (new data model)
  load_functions.py     Relative-path resolution for project file references

frontend/
  app.js                All application logic (tabs, navigation, token selection)
  index.html            UI layout
  styles.css            Styling (classical apparatus look, token highlighting)

docs/
  apparatus_editing.md  User guide to the main apparatus editing workflow
  synopse_editing.md    User guide to the Synoptic Map Editor
  data.md               Complete data model reference
  deployment.md         Building, packaging, and releasing the app
```

## Project Directory Layout (expected)

```
my-edition/
  apparatus/
    edition_app.xml     TEI apparatus file
  texts/
    Witness_A.xml       Base text
    Witness_Ba.xml      Other witness texts
    …
  synopses/
    synoptic_map.xml    Alignment table across all witnesses
  indexes/
    IndexOfWitnesses.xml  Optional: shared witness index. Witnesses can
                           carry their editorial siglum here instead of
                           inline, referenced via <witness><ptr target=
                           "../indexes/IndexOfWitnesses.xml#<witness-id>"/>.
```
