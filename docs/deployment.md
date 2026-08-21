# Deployment

This document describes how to build and distribute HeiCrit. Deployment targets:

- **Desktop app** (Windows / macOS / Linux) — via Electron. Documented below.
- **Public download page** — a static site pointing non-technical end users at the latest published installers. Documented below.
- **Website** (self-hosted, single-tenant) — via Docker. **Not implemented yet** — see [Website deployment (planned)](#3-website-deployment-planned) for the intended design.

---

## 1. Desktop app

HeiCrit's desktop build wraps the Flask backend and static frontend in an [Electron](https://www.electronjs.org/) shell (`electron/main.js`). Packaging is handled by [electron-builder](https://www.electron.build/), configured in the `build` section of `package.json`.

### 1.1 Prerequisites

- Node.js 18+ and npm
- Python 3.12 (≥3.11 required — `heipy`'s `networkx~=3.5` dependency needs it), with a virtual environment at `venv/` in the project root containing the packages from `requirements.txt` (including the `heipy` submodule — run `git submodule update --init --recursive` first if you haven't already)

```bash
git submodule update --init --recursive
python -m venv venv
source venv/bin/activate   # venv\Scripts\activate on Windows
pip install -r requirements.txt
npm install
```

### 1.2 Running in development

```bash
npm run dev
```

This launches Electron, which spawns the Flask backend (`backend/app.py`, using the interpreter at `venv/bin/python` or `venv\Scripts\python.exe`) as a child process and opens a `BrowserWindow` once the backend reports it's running. DevTools open automatically in dev mode.

`npm start` runs the same thing without DevTools/dev-only flags.

### 1.3 Building an installer (`npm run dist`)

```bash
npm run dist
```

This runs `electron-builder`, which bundles `electron/`, `frontend/`, and — as `extraResources` — the `backend/`, `heipy/`, `requirements.txt`, and the entire `venv/` directory into a platform installer under `dist/`.

**Important — builds are not cross-platform.** Because a full `venv/` (including compiled Python extensions such as `lxml`) is bundled as-is, a build produced on one OS will not run on another: a `venv/` built on Linux contains Linux-compiled binaries and a `bin/python` layout, which cannot run on Windows or macOS, and vice versa. Running `npm run dist` once on your laptop only ever produces a working installer for that laptop's OS.

To produce installers for **all three platforms**, either:
- run `npm run dist` natively on a Windows, macOS, and Linux machine each, or
- use the CI pipeline (see below), which already does this correctly.

### 1.4 CI builds (all platforms)

Two equivalent CI pipelines build installers for Windows, macOS, and Linux by creating a fresh `venv` on each target OS before packaging:

- `.gitlab-ci-template.yml` — GitLab CI, runs on the canonical `gitlab.ub.uni-heidelberg.de` origin, triggered on tags/`main`.
- `.github/workflows/build.yml` — GitHub Actions, intended for a GitHub mirror of this repo, triggered on `v*` tags or manual dispatch.

Both are kept in sync intentionally (see the comment at the top of each file) rather than one being redundant — update both if you change the build matrix, Node/Python versions, or packaging steps. The GitHub workflow's `permissions: contents: write` and the publish step (§1.4a below) are GitHub-Releases-specific and are intentionally *not* mirrored into `.gitlab-ci-template.yml`.

Build artifacts (`.exe`/`.dmg`/`.AppImage`/`.deb`/`.tar.xz`) are uploaded as pipeline artifacts on each run (useful for debugging a build without publishing it).

### 1.4a Releasing a new version to end users

`.github/workflows/build.yml` publishes installers straight to GitHub Releases when it's triggered by a version tag (`git push` of a `v*` tag) — but only as a **draft** release (electron-builder's default), so nothing is visible to the public until a maintainer manually reviews and publishes it. A `workflow_dispatch` (manual, no-tag) run intentionally skips publishing — it only produces the pipeline debug artifacts from §1.4, for testing the build itself.

Release checklist:

1. Bump `"version"` in `package.json` to the new release version.
2. Commit that change.
3. Tag it: `git tag vX.Y.Z` (must match the `package.json` version).
4. Push the tag to the GitHub remote: `git push github vX.Y.Z` (adjust the remote name to whatever your GitHub mirror is called).
5. Wait for all three matrix jobs (`ubuntu-latest`/`windows-latest`/`macos-latest`) to finish.
6. Open `https://github.com/GusRiva/heicrit/releases`, review the new **draft** release and its five attached assets (`HeiCrit-Setup.exe`, `HeiCrit.dmg`, `HeiCrit.AppImage`, `HeiCrit.deb`, `HeiCrit.tar.xz`), and click **Publish release**.

As soon as it's published, the download page (§2) starts serving it immediately — its links never need to change.

### 1.5 App icon

`electron/assets/icon.png` is a **placeholder** (a plain generated monogram), referenced from:
- `electron/main.js` — the runtime `BrowserWindow` icon
- `package.json`'s `build.icon` / `build.win.icon` / `build.linux.icon` / `build.mac.icon` — the installer/app-bundle icon (electron-builder derives the platform-specific `.ico`/`.icns` formats from the source PNG automatically at build time; a hand-generated `electron/assets/icon.ico` is also checked in for the Windows target)

Replace `electron/assets/icon.png` (ideally ≥1024×1024, square) with real HeiCrit / Heidelberg University Library branding when available, then re-run `npm run dist` — no other configuration changes are needed.

### 1.6 Troubleshooting

| Symptom | Likely cause |
|---|---|
| `ModuleNotFoundError` for `heipy` on backend start | The `heipy` git submodule wasn't initialized — run `git submodule update --init --recursive`, then reinstall (`pip install -r requirements.txt`) |
| Packaged app fails to start / backend errors about missing binary extensions | The `venv/` bundled into the installer was built on a different OS than the one running it — rebuild on the target OS or use CI (§1.4) |
| electron-builder warns or fails about the app icon | Confirm `electron/assets/icon.png` (and `icon.ico` for Windows) exist and are valid image files |
| Electron window opens but shows a blank page / can't reach the backend | Check the Electron console (`npm run dev` opens DevTools) for the Flask child-process log lines; confirm nothing else is already listening on port 5000 |

---

## 2. Public download page

Non-technical end users shouldn't have to navigate GitHub's Releases UI (version tags, changelogs, a raw file list). Instead, `site/index.html` is a single self-contained static page with plain-language framing and one big "Download for &lt;OS&gt;" button per platform, deployed to GitHub Pages by `.github/workflows/pages.yml` on every push to `main` that touches `site/`.

Each button links directly to a **fixed** URL of the form `https://github.com/GusRiva/heicrit/releases/latest/download/<artifact-name>` (e.g. `HeiCrit-Setup.exe`). GitHub's `/latest/` alias always resolves to the newest **published** (non-draft) release, so once a release is published (§1.4a), the download page immediately serves it — the page itself never needs editing for a routine release.

**Coupling to watch**: the fixed artifact names come from `artifactName` in `package.json`'s `build.win`/`build.mac`/`build.linux` blocks. If any of those (or `productName`) ever change, `site/index.html`'s three `<a href>`s must be updated to match, or the buttons will 404.

**One-time setup (can't be done via code)**: in the GitHub repo, go to **Settings → Pages → Build and deployment** and set **Source** to **"GitHub Actions"** (not "Deploy from a branch"). After that, `pages.yml` handles every future deploy automatically. Resulting URL: `https://gusriva.github.io/heicrit/`.

Both Windows and macOS builds are currently unsigned, so end users will see a SmartScreen (Windows) or Gatekeeper (macOS) warning on first run — the download page includes a one-line workaround for each. Code signing is out of scope for now.

---

## 3. Website deployment (planned)

**This is not implemented yet.** The design below is the intended approach for a future self-hosted web deployment, kept here so it doesn't need to be re-derived:

- **Model**: single-tenant, self-hosted — one running instance serves one operator/project at a time, matching the backend's existing global in-memory state (`apparatus`, `synoptic_map`, `project_files_cache` in `backend/routes.py`). Not a multi-user SaaS.
- **Server**: replace the Flask dev server with [waitress](https://docs.pylonsproject.org/projects/waitress/) (single-process, multi-threaded — safe with the app's global state, unlike a multi-worker server such as gunicorn) via a new `backend/wsgi.py` entrypoint. Local dev keeps using Flask's built-in server unchanged.
- **Serving the frontend**: Flask serves `frontend/` directly as static files (same-origin as the API), avoiding a separate nginx container for this single-tenant scale.
- **Frontend API base**: `frontend/app.js`'s hardcoded `http://127.0.0.1:5000` needs to become environment-aware (relative `/api` when not loaded via `file://`, so Electron keeps working unchanged).
- **Security**: `backend/routes.py`'s `list_files`/`get_file`/`save_file` routes need a path-containment check (a configured `HEICRIT_PROJECT_ROOT`) before being exposed on a network, and the deployment must sit behind real authentication (reverse-proxy basic auth or institutional SSO) if reachable beyond a trusted LAN.
- **Packaging**: a multi-stage `Dockerfile` (handling the `heipy` submodule as a build prerequisite, not something Docker can resolve itself) plus a `docker-compose.yml` for easy self-hosting on a VPS or institutional server. The same Dockerfile should work as-is on PaaS platforms (Render, Fly.io, Railway, etc.) as a drop-in alternative to running Docker yourself.

This will be implemented in a future session.
