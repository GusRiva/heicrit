const API_BASE = 'http://127.0.0.1:5000/api';

class HeiCritApp {
    constructor() {
        this.currentFile = null;
        this.init();
    }

    init() {
        this.bindEvents();
        this.updateStatus('Ready');
        this.loadFileList();
    }

    bindEvents() {
        document.getElementById('openFile').addEventListener('click', () => this.openFile());
        document.getElementById('saveFile').addEventListener('click', () => this.saveFile());
        document.getElementById('newFile').addEventListener('click', () => this.newFile());
    }

    async apiRequest(endpoint, options = {}) {
        try {
            const response = await fetch(`${API_BASE}${endpoint}`, {
                headers: {
                    'Content-Type': 'application/json',
                    ...options.headers
                },
                ...options
            });
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            return await response.json();
        } catch (error) {
            this.updateStatus(`Error: ${error.message}`, 'error');
            throw error;
        }
    }

    async loadFileList(directory = '.') {
        try {
            const data = await this.apiRequest(`/files?directory=${encodeURIComponent(directory)}`);
            this.renderFileList(data.files || []);
        } catch (error) {
            console.error('Failed to load file list:', error);
        }
    }

    renderFileList(files) {
        const fileList = document.getElementById('fileList');
        fileList.innerHTML = '';
        
        files.forEach(file => {
            const fileItem = document.createElement('div');
            fileItem.className = 'file-item';
            fileItem.textContent = file.name;
            fileItem.addEventListener('click', () => this.loadFile(file.path));
            fileList.appendChild(fileItem);
        });
    }

    async loadFile(filepath) {
        try {
            this.updateStatus('Loading file...');
            const data = await this.apiRequest(`/file/${encodeURIComponent(filepath)}`);
            
            document.getElementById('editor').value = data.content;
            document.getElementById('currentFile').textContent = data.filename;
            this.currentFile = filepath;
            
            this.updateStatus(`Loaded: ${data.filename}`);
        } catch (error) {
            console.error('Failed to load file:', error);
        }
    }

    async saveFile() {
        if (!this.currentFile) {
            this.updateStatus('No file selected', 'error');
            return;
        }

        try {
            this.updateStatus('Saving file...');
            const content = document.getElementById('editor').value;
            
            await this.apiRequest('/file', {
                method: 'POST',
                body: JSON.stringify({
                    filename: this.currentFile,
                    content: content
                })
            });
            
            this.updateStatus('File saved successfully');
        } catch (error) {
            console.error('Failed to save file:', error);
        }
    }

    openFile() {
        const input = document.createElement('input');
        input.type = 'file';
        input.accept = '.xml,.tei,.txt';
        input.addEventListener('change', (e) => {
            const file = e.target.files[0];
            if (file) {
                const reader = new FileReader();
                reader.onload = (e) => {
                    document.getElementById('editor').value = e.target.result;
                    document.getElementById('currentFile').textContent = file.name;
                    this.currentFile = file.name;
                    this.updateStatus(`Opened: ${file.name}`);
                };
                reader.readAsText(file);
            }
        });
        input.click();
    }

    newFile() {
        const filename = prompt('Enter filename:');
        if (filename) {
            document.getElementById('editor').value = '';
            document.getElementById('currentFile').textContent = filename;
            this.currentFile = filename;
            this.updateStatus(`New file: ${filename}`);
        }
    }

    updateStatus(message, type = 'info') {
        const status = document.getElementById('status');
        status.textContent = message;
        status.className = type;
        
        if (type === 'error') {
            setTimeout(() => {
                status.textContent = 'Ready';
                status.className = '';
            }, 3000);
        }
    }
}

document.addEventListener('DOMContentLoaded', () => {
    new HeiCritApp();
});