# Deployment

This document describes how to build and distribute HeiCrit. Two deployment targets are planned:

- **Desktop app** (Windows / macOS / Linux) — via Electron. Documented below.
- **Website** (self-hosted, single-tenant) — via Docker. **Not implemented yet** — see [Website deployment (planned)](#website-deployment-planned) for the intended design.

---

## 1. Desktop app

HeiCrit's desktop build wraps the Flask backend and static frontend in an [Electron](https://www.electronjs.org/) shell (`electron/main.js`). Packaging is handled by [electron-builder](https://www.electron.build/), configured in the `build` section of `package.json`.

### 1.1 Prerequisites

- Node.js 18+ and npm
- Python 3.9, with a virtual environment at `venv/` in the project root containing the packages from `requirements.txt` (including the `heipy` submodule — run `git submodule update --init --recursive` first if you haven't already)

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

Both are kept in sync intentionally (see the comment at the top of each file) rather than one being redundant — update both if you change the build matrix, Node/Python versions, or packaging steps.

Build artifacts (`.exe`/`.dmg`/`.AppImage`/`.deb`/`.tar.xz`) are uploaded as pipeline artifacts on each run.

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

## 2. Website deployment (planned)

**This is not implemented yet.** The design below is the intended approach for a future self-hosted web deployment, kept here so it doesn't need to be re-derived:

- **Model**: single-tenant, self-hosted — one running instance serves one operator/project at a time, matching the backend's existing global in-memory state (`apparatus`, `synoptic_map`, `project_files_cache` in `backend/routes.py`). Not a multi-user SaaS.
- **Server**: replace the Flask dev server with [waitress](https://docs.pylonsproject.org/projects/waitress/) (single-process, multi-threaded — safe with the app's global state, unlike a multi-worker server such as gunicorn) via a new `backend/wsgi.py` entrypoint. Local dev keeps using Flask's built-in server unchanged.
- **Serving the frontend**: Flask serves `frontend/` directly as static files (same-origin as the API), avoiding a separate nginx container for this single-tenant scale.
- **Frontend API base**: `frontend/app.js`'s hardcoded `http://127.0.0.1:5000` needs to become environment-aware (relative `/api` when not loaded via `file://`, so Electron keeps working unchanged).
- **Security**: `backend/routes.py`'s `list_files`/`get_file`/`save_file` routes need a path-containment check (a configured `HEICRIT_PROJECT_ROOT`) before being exposed on a network, and the deployment must sit behind real authentication (reverse-proxy basic auth or institutional SSO) if reachable beyond a trusted LAN.
- **Packaging**: a multi-stage `Dockerfile` (handling the `heipy` submodule as a build prerequisite, not something Docker can resolve itself) plus a `docker-compose.yml` for easy self-hosting on a VPS or institutional server. The same Dockerfile should work as-is on PaaS platforms (Render, Fly.io, Railway, etc.) as a drop-in alternative to running Docker yourself.

This will be implemented in a future session.
