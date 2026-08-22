const { contextBridge, ipcRenderer } = require('electron');

// Exposed to the renderer (frontend/app.js) so it can tell it's running
// inside Electron (vs. plain browser/web deployment) and react to native
// File/Edit menu clicks routed from main.js.
contextBridge.exposeInMainWorld('electronAPI', {
    isElectron: true,
    onMenuAction: (callback) => ipcRenderer.on('menu-action', (_event, action) => callback(action)),
    // Native dialogs - see electron/main.js's ipcMain handlers for why these
    // replace the browser-only pickers (input.click()/showSaveFilePicker())
    // when a File action is triggered from the native menu.
    openDirectoryDialog: () => ipcRenderer.invoke('dialog:open-project-directory'),
    openFileDialog: () => ipcRenderer.invoke('dialog:open-file'),
    saveFileDialog: (options) => ipcRenderer.invoke('dialog:save-file', options)
});
