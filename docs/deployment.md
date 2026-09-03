# Deployment

This document describes how to build and distribute HeiCrit. Deployment targets:

- **Desktop app** (Windows / macOS / Linux) — via Electron. Documented below.
- **Public download page** — a static site pointing non-technical end users at the latest published installers. Documented below.
- **Website** (self-hosted, single-tenant) — via Docker. **Not implemented yet** — see [Website deployment (planned)](#3-website-deployment-planned) for the intended design.

---

## 1. Desktop app

HeiCrit's desktop build wraps the Flask backend and static frontend in an [Electron](https://www.electronjs.org/) shell (`electron/main.js`). Packaging is handled by [electron-builder](https://www.electron.build/), configured in the `build` section of `package.json`.

### 1.1 Prerequisites

- Node.js 24+ and npm
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

### 1.3 Build & packaging scripts

All four `package.json` scripts below wrap `electron-builder` with different flags:

| Script | Command | What it produces |
|---|---|---|
| `npm run build` | `electron-builder` | No `--publish` flag — falls back to electron-builder's own default publish policy (roughly: publish only if it detects a CI + tagged-release context). Ambiguous; not used anywhere in this project. |
| `npm run pack` | `electron-builder --dir` | The packaged app as a plain **unpacked** directory (e.g. `dist/linux-unpacked/`) — no installer file, no compression. Fastest option; see below. |
| `npm run dist` | `electron-builder --publish=never` | The real installer artifacts (`.exe`/`.dmg`/`.AppImage`/`.deb`/`.tar.xz`) under `dist/`, never uploaded anywhere. |
| `npm run dist:publish` | `electron-builder --publish=always` | Same installer artifacts, and always uploads them to GitHub Releases per `package.json`'s `build.publish` config (§1.4). |

#### Quick local packaging (`npm run pack`)

```bash
npm run pack
```

This runs the *same* packaging step as `npm run dist` — bundling `electron/`, `frontend/`, and the `extraResources` (`backend/`, `heipy/`, `requirements.txt`, the whole `venv/`) — but stops before the slower step of compressing that into a platform installer. The result is a runnable app folder, e.g. on Linux: `dist/linux-unpacked/heicrit` (the binary name is the lowercased `productName`); on Windows: `dist\win-unpacked\HeiCrit.exe`; on macOS: `dist/mac/HeiCrit.app`. Run that binary directly to launch it.

**How this differs from `npm run dev` (§1.2):** `dev` runs Electron straight from the source tree — no bundling step at all — and spawns the backend from your own local `venv/`. `pack` actually exercises the packaging logic: it copies the backend/heipy/venv into the resources folder the way the final installer would, applies the same `asarUnpack` rules, and runs from that copy rather than your source tree. Use `pack` when you want to verify the packaging itself works (paths resolve, the bundled Python/venv starts correctly) without waiting for `dist`'s installer-compression step.

#### Building an installer (`npm run dist`)

```bash
npm run dist
```

This runs `electron-builder`, which bundles `electron/`, `frontend/`, and — as `extraResources` — the `backend/`, `heipy/`, `requirements.txt`, and the entire `venv/` directory into a platform installer under `dist/`.

**Important — builds are not cross-platform.** Because a full `venv/` (including compiled Python extensions such as `lxml`) is bundled as-is, a build produced on one OS will not run on another: a `venv/` built on Linux contains Linux-compiled binaries and a `bin/python` layout, which cannot run on Windows or macOS, and vice versa. Running `npm run dist` once on your laptop only ever produces a working installer for that laptop's OS.

To produce installers for **all three platforms**, either:
- run `npm run dist` natively on a Windows, macOS, and Linux machine each, or
- use the CI pipeline (see below), which already does this correctly.

### 1.4 Releasing a new version to end users

There are two ways to get a new installer for all three platforms in front of users. Both end up in the same place — assets attached to a GitHub Release matching a `vX.Y.Z` tag — so they're freely mixable (e.g. let CI handle Windows/Linux and build macOS locally if CI can't reach a dependency, as in Option B below).

Either way, start by bumping the version:

1. Set `"version"` in `package.json` to the new release version (`X.Y.Z`, no `v` prefix).
2. Commit that change.
3. Tag it: `git tag vX.Y.Z` (must match the `package.json` version — electron-builder derives the release's tag from it).

#### Option A: GitHub Actions (recommended)

CI pipelines build installers for Windows, macOS, and Linux by creating a fresh `venv` on each target OS before packaging:

- `.github/workflows/build.yml` — GitHub Actions, intended for a GitHub mirror of this repo, triggered on `v*` tags or manual dispatch.

The GitHub workflow's `permissions: contents: write` and its 30-minute `timeout-minutes` are GitHub-Releases-specific.

`build.yml` publishes installers straight to GitHub Releases when triggered by a version tag — but only as a **draft** release (electron-builder's default), so nothing is visible to the public until a maintainer manually reviews and publishes it. A `workflow_dispatch` (manual, no-tag) run intentionally skips publishing; it only produces workflow-run debug artifacts (`.exe`/`.dmg`/`.AppImage`/`.deb`/`.tar.xz`), useful for testing the build itself without publishing anything.

Steps:

4. Push the tag to the GitHub remote: `git push github vX.Y.Z` (adjust the remote name to whatever your GitHub mirror is called).
5. Wait for all three matrix jobs (`ubuntu-latest`/`windows-latest`/`macos-latest`) to finish.
6. Open `https://github.com/GusRiva/heicrit/releases`, review the new **draft** release and its five attached assets (`HeiCrit-Setup.exe`, `HeiCrit.dmg`, `HeiCrit.AppImage`, `HeiCrit.deb`, `HeiCrit.tar.xz`), and click **Publish release**.

As soon as it's published, the download page (§2) starts serving it immediately — its links never need to change.

#### Option B: Build locally and publish (per OS)

Use this if you don't want to wait on CI, or need to work around an environment CI can't reach (see the network-block entry in §1.6). Builds aren't cross-platform (§1.3), so this must be repeated natively on a Windows, macOS, and Linux machine to cover all three — there's no way to produce every platform's installer from one computer.

On each machine, after tagging (steps 1–3 above):

1. Clone (or `git pull`) and check out the exact tag being released:
   ```bash
   git clone https://github.com/GusRiva/heicrit.git
   cd heicrit
   git checkout vX.Y.Z
   git submodule update --init --recursive   # uses your own GitLab credentials, not the CI deploy token
   ```
2. Set up the build environment (§1.1):
   ```bash
   python -m venv venv
   source venv/bin/activate   # venv\Scripts\activate on Windows
   pip install -r requirements.txt
   deactivate
   npm install
   ```
3. Create a GitHub personal access token scoped to `contents: write` on this repo (GitHub → Settings → Developer settings → Personal access tokens), then export it:
   ```bash
   export GH_TOKEN=<your-token>        # macOS/Linux
   $env:GH_TOKEN = "<your-token>"      # Windows PowerShell
   ```
4. Build and publish:
   ```bash
   npm run dist:publish
   ```
   electron-builder defaults to building for the host OS, so this uploads that platform's installer(s) — `HeiCrit-Setup.exe` on Windows, `HeiCrit.dmg` on macOS, `HeiCrit.AppImage`/`HeiCrit.deb`/`HeiCrit.tar.xz` on Linux — directly to the GitHub Release matching the checked-out tag. It finds the release by tag (draft or already-published) and adds the asset; if no release exists yet for that tag, it creates one as a draft, same as CI.
5. Once every platform you're covering has published to it, if the release is still a draft, go to `https://github.com/GusRiva/heicrit/releases` and click **Publish release** (same as Option A step 6). The download page then serves it immediately.

Caveat: this produces a single-architecture build matching whatever machine you build on (e.g. Apple Silicon *or* Intel, not a universal binary) — same limitation as the CI job.

### 1.5 App icon

`electron/assets/icon.png` is a **placeholder** (a plain generated monogram), referenced from:
- `electron/main.js` — the runtime `BrowserWindow` icon
- `package.json`'s `build.icon` / `build.win.icon` / `build.linux.icon` / `build.mac.icon` — the installer/app-bundle icon (electron-builder derives the platform-specific `.ico`/`.icns` formats from the source PNG automatically at build time; a hand-generated `electron/assets/icon.ico` is also checked in for the Windows target)

Replace `electron/assets/icon.png` (ideally ≥1024×1024, square) with real HeiCrit / Heidelberg University Library branding when available, then re-run `npm run dist` — no other configuration changes are needed.

### 1.6 Troubleshooting

| Symptom | Likely cause |
|---|---|
| `ModuleNotFoundError` for `heipy` on backend start | The `heipy` git submodule wasn't initialized — run `git submodule update --init --recursive`, then reinstall (`pip install -r requirements.txt`) |
| `ModuleNotFoundError: No module named 'heipy.heipipe'` (or similar) only in the **packaged** app, while `heipy` imports fine in dev | `requirements.txt` must install `heipy` as a normal package (`./heipy`), not editable (`-e ./heipy`). An editable install writes a `.pth` file with an absolute path to the build machine's checkout; that path doesn't exist once electron-builder copies `venv/` to the end user's machine, so it's silently dropped, and Python falls back to treating the bare `heipy` submodule folder (copied in without `-e`, or via a stale `extraResources` entry) as an empty namespace package. Fix: keep `./heipy` (no `-e`) in `requirements.txt` so `heipy`'s files are physically copied into `venv/site-packages` at install time — no build-time absolute path involved |
| Packaged app fails to start / backend errors about missing binary extensions | The `venv/` bundled into the installer was built on a different OS than the one running it — rebuild on the target OS or use CI (§1.4) |
| electron-builder warns or fails about the app icon | Confirm `electron/assets/icon.png` (and `icon.ico` for Windows) exist and are valid image files |
| Electron window opens but shows a blank page / can't reach the backend | Check the Electron console (`npm run dev` opens DevTools) for the Flask child-process log lines; confirm nothing else is already listening on port 5000 |
| Windows installer opens a window but nothing that needs the backend works (e.g. opening a project silently fails) | A plain `python -m venv venv` isn't relocatable on Windows — `Scripts\python.exe` looks up its stdlib/DLLs via `pyvenv.cfg`'s `home`, an absolute path back to whichever machine created the venv. `build.yml`'s Windows job instead copies a whole self-contained Python installation (`$env:pythonLocation`) directly into `venv/`; `electron/main.js`'s `resolvePythonPath` looks for `Scripts\python.exe` first (local dev venv) and falls back to `venv\python.exe` at the root (CI-vendored layout). If you hit this, check the Electron console for whether the Flask child process actually started at all |

---

## 2. Public download page

Non-technical end users shouldn't have to navigate GitHub's Releases UI (version tags, changelogs, a raw file list). Instead, `site/index.html` is a single self-contained static page with plain-language framing and one big "Download for &lt;OS&gt;" button per platform, deployed to GitHub Pages by `.github/workflows/pages.yml` on every push to `main` that touches `site/`.

Each button links directly to a **fixed** URL of the form `https://github.com/GusRiva/heicrit/releases/latest/download/<artifact-name>` (e.g. `HeiCrit-Setup.exe`). GitHub's `/latest/` alias always resolves to the newest **published** (non-draft) release, so once a release is published (§1.4), the download page immediately serves it — the page itself never needs editing for a routine release.

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
