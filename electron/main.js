const { app, BrowserWindow, dialog, Menu, ipcMain } = require('electron');
const path = require('path');
const fs = require('fs');
const { spawn } = require('child_process');

// Kept in sync by hand with the relevantFolders filter in
// frontend/app.js's readFilesIntoProjectFiles() - only these top-level
// project subfolders are walked/read when opening a project directory
// via the native dialog (see the dialog:open-project-directory handler).
const RELEVANT_PROJECT_FOLDERS = ['apparatus', 'synopses', 'texts', 'indexes'];

let mainWindow;
let flaskProcess;
let backendPort = null;

// Enable live reload for development
const isDev = process.argv.includes('--dev');

function createWindow() {
    // Create the browser window
    mainWindow = new BrowserWindow({
        width: 1200,
        height: 800,
        webPreferences: {
            nodeIntegration: false,
            contextIsolation: true,
            enableRemoteModule: false,
            webSecurity: true,
            preload: path.join(__dirname, 'preload.js')
        },
        icon: path.join(__dirname, 'assets', 'icon.png'), // Add an icon if you have one
        titleBarStyle: 'default'
    });

    // Load the frontend, telling it which port the backend actually bound
    // (see startFlaskBackend - the backend picks a free port at startup
    // rather than a fixed one, to avoid clashing with anything else already
    // using it, e.g. macOS's AirPlay Receiver on port 5000).
    mainWindow.loadFile(path.join(__dirname, '..', 'frontend', 'index.html'), {
        query: { apiPort: String(backendPort) }
    });

    // Open DevTools in development
    if (isDev) {
        mainWindow.webContents.openDevTools();
    }

    // Handle window closed
    mainWindow.on('closed', () => {
        mainWindow = null;
    });
}

function sendMenuAction(action) {
    if (mainWindow) {
        mainWindow.webContents.send('menu-action', action);
    }
}

// Replaces Electron's generic default menu with the app's own File/Edit
// actions, routed to frontend/app.js via preload.js's menu-action IPC
// channel. frontend/index.html's HTML File/Edit dropdown is hidden at
// runtime when it detects it's running under this native menu (see
// app.js's setupElectronMenu) - the HTML version stays for the plain-browser
// web deployment, which has no native menu bar to move it into.
function createMenu() {
    const isMac = process.platform === 'darwin';

    const template = [
        ...(isMac ? [{
            label: app.name,
            submenu: [
                { role: 'about' },
                { type: 'separator' },
                { role: 'services' },
                { type: 'separator' },
                { role: 'hide' },
                { role: 'hideOthers' },
                { role: 'unhide' },
                { type: 'separator' },
                { role: 'quit' }
            ]
        }] : []),
        {
            label: 'File',
            submenu: [
                { label: 'Open Project', click: () => sendMenuAction('open-project-directory') },
                { label: 'Switch Apparatus File', click: () => sendMenuAction('switch-apparatus-file') },
                { type: 'separator' },
                { label: 'Open File', click: () => sendMenuAction('open-file') },
                { label: 'Save File As', click: () => sendMenuAction('save-as-file') },
                { label: 'Save File', accelerator: 'CmdOrCtrl+S', click: () => sendMenuAction('save-file') },
                { type: 'separator' },
                isMac ? { role: 'close' } : { role: 'quit' }
            ]
        },
        {
            label: 'Edit',
            submenu: [
                { role: 'undo' },
                { role: 'redo' },
                { type: 'separator' },
                { role: 'cut' },
                { role: 'copy' },
                { role: 'paste' },
                { role: 'selectAll' }
            ]
        },
        {
            label: 'View',
            submenu: [
                { role: 'reload' },
                { role: 'forceReload' },
                { role: 'toggleDevTools' },
                { type: 'separator' },
                { role: 'resetZoom' },
                { role: 'zoomIn' },
                { role: 'zoomOut' },
                { type: 'separator' },
                { role: 'togglefullscreen' }
            ]
        },
        { role: 'windowMenu' }
    ];

    Menu.setApplicationMenu(Menu.buildFromTemplate(template));
}

function walkProjectFiles(relativePrefix, dir, results) {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
        const fullPath = path.join(dir, entry.name);
        const relativePath = `${relativePrefix}/${entry.name}`;
        if (entry.isDirectory()) {
            walkProjectFiles(relativePath, fullPath, results);
        } else if (entry.isFile()) {
            try {
                results.push({ relativePath, content: fs.readFileSync(fullPath, 'utf-8') });
            } catch (error) {
                console.warn(`Skipping unreadable project file ${fullPath}:`, error.message);
            }
        }
    }
}

// Native replacements for the browser-only pickers frontend/app.js normally
// uses (input[webkitdirectory].click(), input[type=file].click(),
// showSaveFilePicker()). Those require a genuine user-gesture in Chromium,
// which a click relayed through the native menu -> IPC -> renderer chain
// doesn't provide, so triggering them from a menu action silently no-ops.
// dialog.showOpenDialog/showSaveDialog run in the main process and aren't
// gesture-gated, so the menu wires up these IPC handlers instead - see
// electron/preload.js and frontend/app.js's openProjectDirectory/openFile/
// saveAsFile for the renderer side.
ipcMain.handle('dialog:open-project-directory', async () => {
    const result = await dialog.showOpenDialog(mainWindow, { properties: ['openDirectory'] });
    if (result.canceled || result.filePaths.length === 0) return null;

    const selectedDir = result.filePaths[0];
    const dirName = path.basename(selectedDir);
    const files = [];
    for (const folder of RELEVANT_PROJECT_FOLDERS) {
        const folderPath = path.join(selectedDir, folder);
        if (fs.existsSync(folderPath) && fs.statSync(folderPath).isDirectory()) {
            walkProjectFiles(`${dirName}/${folder}`, folderPath, files);
        }
    }
    // directoryPath (absolute) lets the backend resolve save/write requests
    // against the real filesystem location - the Flask child process's cwd
    // is always inside the app bundle (see startFlaskBackend), not wherever
    // the user's project actually lives, so a bare directory name isn't
    // enough for it to find files to write to. See frontend/app.js's
    // openProjectDirectory and backend/routes.py's resolve_apparatus_file_on_disk.
    return { directoryPath: selectedDir, files };
});

ipcMain.handle('dialog:open-file', async () => {
    const result = await dialog.showOpenDialog(mainWindow, {
        properties: ['openFile'],
        filters: [{ name: 'TEI/XML/Text files', extensions: ['xml', 'tei', 'txt'] }]
    });
    if (result.canceled || result.filePaths.length === 0) return null;

    const filePath = result.filePaths[0];
    return { name: path.basename(filePath), content: fs.readFileSync(filePath, 'utf-8') };
});

ipcMain.handle('dialog:save-file', async (_event, { defaultFilename, content }) => {
    const result = await dialog.showSaveDialog(mainWindow, {
        defaultPath: defaultFilename,
        filters: [
            { name: 'XML files', extensions: ['xml'] },
            { name: 'TEI files', extensions: ['tei'] },
            { name: 'Text files', extensions: ['txt'] }
        ]
    });
    if (result.canceled || !result.filePath) return null;

    fs.writeFileSync(result.filePath, content, 'utf-8');
    return path.basename(result.filePath);
});

// A local-dev venv (python -m venv venv, per docs/deployment.md #1.1) puts
// python.exe at Scripts\python.exe on Windows, alongside a pyvenv.cfg that
// locates the stdlib/DLLs via an absolute "home" path back to whatever
// Python installation created it. That's fine on a dev machine but not
// relocatable - the GitHub Actions Windows build instead vendors a whole
// self-contained Python installation directly into venv/ (python.exe at the
// venv root, no pyvenv.cfg dependency - see .github/workflows/build.yml),
// so check for that layout too.
function resolvePythonPath(venvPath) {
    if (process.platform !== 'win32') {
        return path.join(venvPath, 'bin', 'python');
    }
    const devVenvPython = path.join(venvPath, 'Scripts', 'python.exe');
    if (fs.existsSync(devVenvPython)) {
        return devVenvPython;
    }
    return path.join(venvPath, 'python.exe');
}

function startFlaskBackend() {
    return new Promise((resolve, reject) => {
        console.log('Starting Flask backend...');
        
        // Path to resources (different in dev vs production)
        const isDev = process.argv.includes('--dev');
        const resourcesPath = isDev 
            ? path.join(__dirname, '..')  // Development: project root
            : path.join(process.resourcesPath); // Production: resources directory
            
        // Path to Python virtual environment
        const venvPath = path.join(resourcesPath, 'venv');
        const pythonPath = resolvePythonPath(venvPath);
        
        const backendPath = path.join(resourcesPath, 'backend', 'app.py');
        const projectRoot = resourcesPath;
        
        console.log('Python path:', pythonPath);
        console.log('Backend path:', backendPath);
        console.log('Project root:', projectRoot);
        
        // Start Flask process
        flaskProcess = spawn(pythonPath, [backendPath], {
            cwd: projectRoot,
            env: { 
                ...process.env, 
                PYTHONPATH: projectRoot,
                FLASK_ENV: 'development'
            },
            stdio: ['pipe', 'pipe', 'pipe']
        });

        let settled = false;
        const settleResolve = () => {
            // Only ready once we both know the port (HEICRIT_BACKEND_PORT=...,
            // printed by backend/app.py before it starts serving) and have
            // seen Flask's own "Running on" banner confirming it's up.
            if (!settled && backendPort !== null) {
                settled = true;
                resolve();
            }
        };

        const handleOutput = (data) => {
            const text = data.toString();
            const portMatch = text.match(/HEICRIT_BACKEND_PORT=(\d+)/);
            if (portMatch) {
                backendPort = parseInt(portMatch[1], 10);
            }
            if (text.includes('Running on')) {
                settleResolve();
            }
        };

        flaskProcess.stdout.on('data', (data) => {
            console.log(`Flask stdout: ${data}`);
            handleOutput(data);
        });

        flaskProcess.stderr.on('data', (data) => {
            console.log(`Flask stderr: ${data}`);
            // Flask often outputs normal info to stderr
            handleOutput(data);
        });

        flaskProcess.on('error', (error) => {
            console.error('Failed to start Flask backend:', error);
            dialog.showErrorBox('Backend Error',
                'Failed to start the Flask backend. Please ensure Python and dependencies are installed.');
            if (!settled) {
                settled = true;
                reject(error);
            }
        });

        // Timeout after 10 seconds
        setTimeout(() => {
            if (settled) return;
            settled = true;
            if (backendPort !== null) {
                resolve(); // Didn't see "Running on" but we do have a port - continue
            } else {
                const error = new Error('Flask backend did not report its port within 10 seconds');
                dialog.showErrorBox('Backend Error', error.message);
                reject(error);
            }
        }, 10000);
    });
}

// App event handlers
app.whenReady().then(async () => {
    try {
        createMenu();

        // Start Flask backend first
        await startFlaskBackend();

        // Then create the window
        createWindow();
    } catch (error) {
        console.error('Failed to start application:', error);
        app.quit();
    }

    app.on('activate', () => {
        if (BrowserWindow.getAllWindows().length === 0) {
            createWindow();
        }
    });
});

app.on('window-all-closed', () => {
    // Kill Flask process
    if (flaskProcess) {
        flaskProcess.kill();
    }
    
    if (process.platform !== 'darwin') {
        app.quit();
    }
});

app.on('before-quit', () => {
    // Kill Flask process
    if (flaskProcess) {
        flaskProcess.kill();
    }
});