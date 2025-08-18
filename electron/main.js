const { app, BrowserWindow, dialog } = require('electron');
const path = require('path');
const { spawn } = require('child_process');

let mainWindow;
let flaskProcess;

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
            webSecurity: true
        },
        icon: path.join(__dirname, 'assets', 'icon.png'), // Add an icon if you have one
        titleBarStyle: 'default'
    });

    // Load the frontend
    mainWindow.loadFile(path.join(__dirname, '..', 'frontend', 'index.html'));

    // Open DevTools in development
    if (isDev) {
        mainWindow.webContents.openDevTools();
    }

    // Handle window closed
    mainWindow.on('closed', () => {
        mainWindow = null;
    });
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
        const pythonPath = process.platform === 'win32' 
            ? path.join(venvPath, 'Scripts', 'python.exe')
            : path.join(venvPath, 'bin', 'python');
        
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

        flaskProcess.stdout.on('data', (data) => {
            console.log(`Flask stdout: ${data}`);
            if (data.includes('Running on')) {
                resolve();
            }
        });

        flaskProcess.stderr.on('data', (data) => {
            console.log(`Flask stderr: ${data}`);
            // Flask often outputs normal info to stderr
            if (data.includes('Running on')) {
                resolve();
            }
        });

        flaskProcess.on('error', (error) => {
            console.error('Failed to start Flask backend:', error);
            dialog.showErrorBox('Backend Error', 
                'Failed to start the Flask backend. Please ensure Python and dependencies are installed.');
            reject(error);
        });

        // Timeout after 10 seconds
        setTimeout(() => {
            resolve(); // Continue even if we don't see the "Running on" message
        }, 10000);
    });
}

// App event handlers
app.whenReady().then(async () => {
    try {
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