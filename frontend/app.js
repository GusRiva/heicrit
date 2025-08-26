const API_BASE = 'http://127.0.0.1:5000/api';

class HeiCritApp {
    constructor() {
        this.currentFile = null;
        this.textarea = null;
        this.highlightCode = null;
        this.apparatusData = null;
        this.synopticMapData = null;
        this.mainTextData = null; // Store main text data
        this.projectFiles = new Map(); // Store all project files
        this.groupedEntries = {}; // Store grouped entries by location (legacy)
        
        // Tab management
        this.tabs = new Map(); // Store tab data: id -> {type, title, content, data}
        this.activeTabId = null;
        this.nextTabId = 1;
        
        this.init();
    }

    init() {
        this.bindEvents();
        this.updateStatus('Ready');
    }

    // Tab Management Methods
    createTab(type, title, content = null, data = null) {
        const tabId = `tab-${this.nextTabId++}`;
        const tab = {
            id: tabId,
            type: type, // 'project', 'file'
            title: title,
            content: content,
            data: data
        };
        
        this.tabs.set(tabId, tab);
        this.renderTabs();
        this.switchToTab(tabId);
        return tabId;
    }

    closeTab(tabId) {
        if (!this.tabs.has(tabId)) return;
        
        this.tabs.delete(tabId);
        
        // Remove tab panel
        const panel = document.getElementById(`panel-${tabId}`);
        if (panel) panel.remove();
        
        // If this was the active tab, switch to another
        if (this.activeTabId === tabId) {
            const remainingTabs = Array.from(this.tabs.keys());
            if (remainingTabs.length > 0) {
                this.switchToTab(remainingTabs[0]);
            } else {
                this.activeTabId = null;
                this.showEmptyWorkspace();
            }
        }
        
        this.renderTabs();
    }

    switchToTab(tabId) {
        if (!this.tabs.has(tabId)) return;
        
        // Hide all tab panels
        document.querySelectorAll('.tab-panel').forEach(panel => {
            panel.classList.remove('active');
        });
        
        // Show target panel
        let panel = document.getElementById(`panel-${tabId}`);
        if (!panel) {
            panel = this.createTabPanel(tabId);
        }
        panel.classList.add('active');
        
        this.activeTabId = tabId;
        this.renderTabs();
        
        // Update UI based on tab type
        const tab = this.tabs.get(tabId);
        this.setupTabContent(tab);
    }

    createTabPanel(tabId) {
        const tab = this.tabs.get(tabId);
        const panel = document.createElement('div');
        panel.id = `panel-${tabId}`;
        panel.className = 'tab-panel';
        
        if (tab.type === 'project') {
            panel.innerHTML = `
                <!-- Apparatus Display Container -->
                <div class="view-container apparatus-container">
                    <div class="apparatus-layout">
                        <div class="text-panel">
                            <h3>Main Text (Leithandschrift)</h3>
                            <div id="main-text-content-${tabId}"></div>
                        </div>
                        <div class="apparatus-panel">
                            <div class="apparatus-header-controls">
                                <h3>Critical Apparatus</h3>
                                <div class="apparatus-navigation" style="display: none;" id="apparatus-navigation-${tabId}">
                                    <button class="nav-button apparatus-prev" data-tab="${tabId}">← Previous</button>
                                    <span class="entry-counter apparatus-counter" id="apparatus-counter-${tabId}">1 / 1</span>
                                    <button class="nav-button apparatus-next" data-tab="${tabId}">Next →</button>
                                    
                                    <div class="goto-controls">
                                        <span>Go to:</span>
                                        <input type="text" class="goto-input apparatus-goto-input" data-tab="${tabId}" placeholder="loc">
                                        <button class="goto-button apparatus-goto-button" data-tab="${tabId}">Go</button>
                                    </div>
                                </div>
                            </div>
                            
                            <div class="apparatus-content" id="apparatus-content-${tabId}">
                                <p>No apparatus entries loaded</p>
                            </div>
                            
                            <div class="apparatus-details">
                                <h4>Location Details</h4>
                                <div id="apparatus-details-content-${tabId}">
                                    Click on a location number to see details
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            `;
        } else if (tab.type === 'file') {
            panel.innerHTML = `
                <!-- Recreate original working structure -->
                <div id="xml-editor-container-${tabId}" style="position: relative; width: 100%; height: 100%;">
                    <textarea id="editor-textarea-${tabId}" placeholder="Open or create a file to start editing..." spellcheck="false" autocomplete="off" autocorrect="off" autocapitalize="off"></textarea>
                    <pre id="editor-highlight-${tabId}"><code id="editor-code-${tabId}" class="language-xml"></code></pre>
                </div>
            `;
        }
        
        document.getElementById('tabContent').appendChild(panel);
        return panel;
    }

    setupTabContent(tab) {
        if (tab.type === 'file') {
            // Setup editor for file tab
            const textarea = document.getElementById(`editor-textarea-${tab.id}`);
            const highlightCode = document.getElementById(`editor-code-${tab.id}`);
            
            if (textarea && tab.content) {
                textarea.value = tab.content;
                // Simple immediate highlighting like before tabs
                this.updateHighlighting(textarea, highlightCode);
                this.setupEditorEvents(textarea, highlightCode, tab.id);
            }
        } else if (tab.type === 'project') {
            // Setup project view
            this.setupProjectTabEvents(tab.id);
            if (tab.data) {
                this.loadProjectDataIntoTab(tab.id, tab.data);
            }
        }
    }

    renderTabs() {
        const tabList = document.getElementById('tabList');
        tabList.innerHTML = '';
        
        for (const [tabId, tab] of this.tabs) {
            const tabElement = document.createElement('div');
            tabElement.className = `tab ${this.activeTabId === tabId ? 'active' : ''}`;
            tabElement.innerHTML = `
                <span class="tab-title">${tab.title}</span>
                <button class="tab-close" data-tab-id="${tabId}">×</button>
            `;
            
            tabElement.addEventListener('click', (e) => {
                if (!e.target.classList.contains('tab-close')) {
                    this.switchToTab(tabId);
                }
            });
            
            tabElement.querySelector('.tab-close').addEventListener('click', (e) => {
                e.stopPropagation();
                this.closeTab(tabId);
            });
            
            tabList.appendChild(tabElement);
        }
    }

    showEmptyWorkspace() {
        document.getElementById('tabContent').innerHTML = `
            <div class="empty-workspace">
                <p>No files or projects open</p>
                <p>Use <strong>File → Open Project Directory</strong> or <strong>File → Open File</strong> to get started</p>
            </div>
        `;
    }

    setupEditorEvents(textarea, highlightCode, tabId) {
        if (!textarea || !highlightCode) return;
        
        // Prevent duplicate event listeners
        if (textarea.dataset.eventsSetup) return;
        textarea.dataset.eventsSetup = 'true';

        // Debounce highlighting updates for better performance
        let highlightTimer;
        const debouncedHighlight = () => {
            clearTimeout(highlightTimer);
            highlightTimer = setTimeout(() => {
                this.updateHighlighting(textarea, highlightCode);
            }, 16); // ~60fps refresh rate
        };

        // Sync textarea input with syntax highlighting
        textarea.addEventListener('input', debouncedHighlight);

        // Enhanced scroll synchronization
        const syncScrollNow = () => this.syncScroll(textarea, highlightCode);
        
        textarea.addEventListener('scroll', syncScrollNow);
        
        // Also sync on various events that might affect scrolling
        textarea.addEventListener('input', syncScrollNow);
        textarea.addEventListener('keyup', syncScrollNow);
        window.addEventListener('resize', syncScrollNow);

        textarea.addEventListener('keydown', (e) => {
            // Handle tab key for indentation
            if (e.key === 'Tab') {
                e.preventDefault();
                this.insertTab(textarea, highlightCode);
            }
        });
    }

    setupProjectTabEvents(tabId) {
        // Setup navigation events for this specific project tab
        const prevBtn = document.querySelector(`button[data-tab="${tabId}"].apparatus-prev`);
        const nextBtn = document.querySelector(`button[data-tab="${tabId}"].apparatus-next`);
        const gotoBtn = document.querySelector(`button[data-tab="${tabId}"].apparatus-goto-button`);
        const gotoInput = document.querySelector(`input[data-tab="${tabId}"].apparatus-goto-input`);

        if (prevBtn) {
            prevBtn.addEventListener('click', () => this.showPreviousEntry(tabId));
        }
        if (nextBtn) {
            nextBtn.addEventListener('click', () => this.showNextEntry(tabId));
        }
        if (gotoBtn) {
            gotoBtn.addEventListener('click', () => this.goToLocNumber(tabId));
        }
        if (gotoInput) {
            gotoInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') {
                    this.goToLocNumber(tabId);
                }
            });
        }
    }

    loadProjectDataIntoTab(tabId, data) {
        if (!data) return;

        // Load main text
        const mainTextContent = document.getElementById(`main-text-content-${tabId}`);
        if (mainTextContent && data.mainTextData && data.mainTextData.content) {
            mainTextContent.innerHTML = data.mainTextData.content;
        }

        // Setup apparatus data for this tab
        const tab = this.tabs.get(tabId);
        if (tab) {
            tab.apparatusData = data.apparatusData;
            tab.synopticMapData = data.synopticMapData;
            tab.mainTextData = data.mainTextData;
            tab.apparatusEntries = data.apparatusEntries;
            tab.currentEntryIndex = 0;
            tab.groupedEntries = this.groupEntriesByCorresp(data.apparatusEntries);
            tab.entryKeys = Object.keys(tab.groupedEntries);

            // Sort entry keys by location
            tab.entryKeys.sort((a, b) => {
                const locA = tab.groupedEntries[a][0]?.loc || '';
                const locB = tab.groupedEntries[b][0]?.loc || '';
                const numA = parseInt(locA) || 0;
                const numB = parseInt(locB) || 0;
                return numA - numB;
            });

            // Display apparatus entries
            this.updateApparatusDisplay(tabId);

            // Show navigation if needed
            const navigation = document.getElementById(`apparatus-navigation-${tabId}`);
            if (navigation && tab.entryKeys.length > 1) {
                navigation.style.display = 'flex';
            }
        }
    }

    updateHighlighting(textarea, highlightCode) {
        if (!textarea || !highlightCode) return;
        
        const content = textarea.value;
        
        // Skip the content change check for now to ensure proper updates
        // if (highlightCode.textContent === content) return;
        
        // Ensure identical whitespace handling including trailing lines
        let processedContent = content;
        
        // Handle empty lines with zero-width spaces
        if (processedContent.includes('\n\n')) {
            processedContent = processedContent.replace(/\n\n/g, '\n\u200B\n');
        }
        
        // Ensure trailing newline consistency
        // If textarea ends with newline, make sure highlight also shows that empty line
        if (processedContent.endsWith('\n')) {
            processedContent += '\u200B'; // Add zero-width space to preserve trailing line
        }
        
        highlightCode.textContent = processedContent;
        
        // Ensure the language class is set for XML
        if (!highlightCode.classList.contains('language-xml')) {
            highlightCode.classList.add('language-xml');
        }
        
        // Apply Prism.js highlighting
        if (typeof Prism !== 'undefined') {
            Prism.highlightElement(highlightCode);
        }
    }

    syncScroll(textarea, highlightCode) {
        if (!textarea || !highlightCode) return;
        const highlight = highlightCode.parentElement;
        if (highlight) {
            // Force immediate scroll sync with bounds checking
            requestAnimationFrame(() => {
                // Constrain scroll position to prevent over-scrolling
                const maxScrollTop = Math.min(
                    textarea.scrollHeight - textarea.clientHeight,
                    highlight.scrollHeight - highlight.clientHeight
                );
                
                const scrollTop = Math.min(textarea.scrollTop, maxScrollTop);
                
                highlight.scrollTop = scrollTop;
                highlight.scrollLeft = textarea.scrollLeft;
            });
        }
    }

    insertTab(textarea, highlightCode) {
        if (!textarea) return;
        
        const start = textarea.selectionStart;
        const end = textarea.selectionEnd;
        const value = textarea.value;
        
        textarea.value = value.substring(0, start) + '    ' + value.substring(end);
        textarea.selectionStart = textarea.selectionEnd = start + 4;
        this.updateHighlighting(textarea, highlightCode);
    }

    updateApparatusDisplay(tabId) {
        const tab = this.tabs.get(tabId);
        if (!tab || !tab.entryKeys || tab.entryKeys.length === 0) {
            const content = document.getElementById(`apparatus-content-${tabId}`);
            if (content) {
                content.innerHTML = '<p>No apparatus entries to display</p>';
            }
            return;
        }

        // Get current entry data
        const currentCorresp = tab.entryKeys[tab.currentEntryIndex];
        const currentEntries = tab.groupedEntries[currentCorresp];
        const currentLoc = currentEntries.length > 0 && currentEntries[0].loc ? currentEntries[0].loc : '';

        // Generate HTML for current entry
        const htmlContent = this.generateSingleEntryHTML(currentLoc, currentEntries);
        
        // Set content
        const content = document.getElementById(`apparatus-content-${tabId}`);
        if (content) {
            content.innerHTML = htmlContent;
        }

        // Update navigation controls
        this.updateNavigationControls(tabId);
        
        // Highlight the corresponding synoptic unit
        if (currentEntries.length > 0) {
            // Extract container ID from the corresp field (remove prefix if present)
            const containerId = currentCorresp.includes(':') ? currentCorresp.split(':')[1] : currentCorresp;
            this.highlightSynopticUnit(containerId);
        }
    }

    updateNavigationControls(tabId) {
        const tab = this.tabs.get(tabId);
        if (!tab) return;

        const counter = document.getElementById(`apparatus-counter-${tabId}`);
        const prevBtn = document.querySelector(`button[data-tab="${tabId}"].apparatus-prev`);
        const nextBtn = document.querySelector(`button[data-tab="${tabId}"].apparatus-next`);
        
        if (counter) {
            counter.textContent = `${tab.currentEntryIndex + 1} / ${tab.entryKeys.length}`;
        }
        
        if (prevBtn) {
            prevBtn.disabled = tab.currentEntryIndex === 0;
        }
        if (nextBtn) {
            nextBtn.disabled = tab.currentEntryIndex === tab.entryKeys.length - 1;
        }
    }

    showPreviousEntry(tabId) {
        const tab = this.tabs.get(tabId);
        if (!tab) return;

        if (tab.currentEntryIndex > 0) {
            tab.currentEntryIndex--;
            this.updateApparatusDisplay(tabId);
        }
    }

    showNextEntry(tabId) {
        const tab = this.tabs.get(tabId);
        if (!tab) return;

        if (tab.currentEntryIndex < tab.entryKeys.length - 1) {
            tab.currentEntryIndex++;
            this.updateApparatusDisplay(tabId);
        }
    }

    goToLocNumber(tabId) {
        const input = document.querySelector(`input[data-tab="${tabId}"].apparatus-goto-input`);
        const tab = this.tabs.get(tabId);
        
        if (!input || !tab) return;
        
        const locNumber = input.value.trim();
        if (!locNumber) return;

        // Find the entry with matching loc number
        const targetIndex = tab.entryKeys.findIndex(corresp => {
            const entries = tab.groupedEntries[corresp];
            if (entries && entries.length > 0) {
                const loc = entries[0].loc;
                return loc === locNumber || loc === String(locNumber);
            }
            return false;
        });

        if (targetIndex !== -1) {
            tab.currentEntryIndex = targetIndex;
            this.updateApparatusDisplay(tabId);
            input.value = '';
        } else {
            // Show feedback for invalid loc number
            input.style.border = '2px solid red';
            setTimeout(() => {
                input.style.border = '';
            }, 1000);
        }
    }

    bindEvents() {
        // Navbar dropdown menu events
        document.getElementById('openFile').addEventListener('click', () => this.openFile());
        document.getElementById('openProjectDirectory').addEventListener('click', () => this.openProjectDirectory());
        document.getElementById('saveFile').addEventListener('click', () => this.saveFile());
        document.getElementById('saveAsFile').addEventListener('click', () => this.saveAsFile());
        
        // Toolbar icon events
        document.getElementById('openProjectDirectoryIcon').addEventListener('click', () => this.openProjectDirectory());
        
        // Add click handler for any element with data-container-id attribute
        document.addEventListener('click', (e) => {
            if (e.target.hasAttribute('data-container-id')) {
                const containerId = e.target.getAttribute('data-container-id');
                if (containerId) {
                    this.goToCorrespEntry(containerId);
                }
            }
        });
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

    async loadFile(filepath) {
        try {
            this.updateStatus('Loading file...');
            const data = await this.apiRequest(`/file/${encodeURIComponent(filepath)}`);
            
            // File content will be displayed in the tab
            
            this.textarea.value = data.content;
            // File content highlighting now handled in tab-specific editor
            // File name is now displayed in the tab title
            this.currentFile = filepath;
            
            this.updateStatus(`Loaded: ${data.filename}`);
        } catch (error) {
            this.updateStatus(`Failed to load file: ${error.message}`, 'error');
        }
    }

    async saveFile() {
        if (!this.currentFile) {
            this.updateStatus('No file selected', 'error');
            return;
        }

        try {
            this.updateStatus('Saving file...');
            const content = this.textarea.value;
            
            await this.apiRequest('/file', {
                method: 'POST',
                body: JSON.stringify({
                    filename: this.currentFile,
                    content: content
                })
            });
            
            this.updateStatus('File saved successfully');
        } catch (error) {
            this.updateStatus(`Failed to save file: ${error.message}`, 'error');
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
                    // Create a new tab for the file
                    const tabId = this.createTab('file', file.name, e.target.result, {
                        filename: file.name,
                        filepath: file.name
                    });
                    
                    this.updateStatus(`Opened: ${file.name}`);
                };
                reader.readAsText(file);
            }
        });
        input.click();
    }

    openProjectDirectory() {
        const input = document.createElement('input');
        input.type = 'file';
        input.webkitdirectory = true; // Allow directory selection
        input.multiple = true;
        
        // Clear the input value to ensure change event fires even for same directory
        input.value = '';
        
        input.addEventListener('change', (e) => {
            const files = Array.from(e.target.files);
            if (files.length > 0) {
                this.processProjectDirectory(files);
            }
        });
        input.click();
    }

    async processProjectDirectory(files) {
        try {
            // Show loading popup
            this.showLoadingPopup();
            this.updateLoadingStep('step-reading', 'active');
            this.updateStatus('Processing project directory...');
            
            // Store all files in the project
            this.projectFiles.clear();
            
            // Read all files and store them
            const fileReadPromises = files.map(file => {
                return new Promise((resolve) => {
                    const reader = new FileReader();
                    reader.onload = (e) => {
                        // Use the webkitRelativePath to preserve directory structure
                        const relativePath = file.webkitRelativePath || file.name;
                        this.projectFiles.set(relativePath, {
                            content: e.target.result,
                            file: file,
                            path: relativePath
                        });
                        resolve();
                    };
                    reader.readAsText(file);
                });
            });
            
            // Wait for all files to be read
            await Promise.all(fileReadPromises);
            
            this.updateLoadingStep('step-reading', 'completed');
            this.updateStatus(`Loaded ${this.projectFiles.size} files from project directory`);
            
            // Auto-detect and process apparatus and synoptic map files
            await this.autoProcessProjectFiles();
            
        } catch (error) {
            this.showErrorPopup('Project Directory Error', `Failed to process project directory: ${error.message}`);
        }
    }

    async autoProcessProjectFiles() {
        // Look for apparatus files in apparatus/ directory
        const apparatusFiles = Array.from(this.projectFiles.entries())
            .filter(([path, fileData]) => path.includes('/apparatus/') && path.endsWith('.xml'))
            .map(([path, fileData]) => ({ path, ...fileData }));
        
        // Look for synoptic map files in synopses/ directory
        const synopticFiles = Array.from(this.projectFiles.entries())
            .filter(([path, fileData]) => path.includes('/synopses/') && path.endsWith('.xml'))
            .map(([path, fileData]) => ({ path, ...fileData }));
        
        // Process apparatus file if found
        if (apparatusFiles.length > 0) {
            this.updateLoadingStep('step-processing', 'active');
            const apparatusFile = apparatusFiles[0]; // Use first apparatus file found
            await this.processApparatusFileFromProject(apparatusFile.content, apparatusFile.path);
            this.updateLoadingStep('step-processing', 'completed');
        }
        
        // Process synoptic map if found  
        if (synopticFiles.length > 0) {
            this.updateLoadingStep('step-synoptic', 'active');
            const synopticFile = synopticFiles[0]; // Use first synoptic file found
            await this.processSynopticMapFileFromProject(synopticFile.content, synopticFile.path);
            this.updateLoadingStep('step-synoptic', 'completed');
        }
        
        if (apparatusFiles.length === 0 && synopticFiles.length === 0) {
            this.updateStatus('No apparatus or synoptic map files found in project directory');
            this.showErrorPopup('No Files Found', 'No apparatus files found in apparatus/ directory or synoptic map files found in synopses/ directory.');
            return;
        }
        
        // Complete remaining steps
        this.updateLoadingStep('step-maintext', 'completed');
        this.updateLoadingStep('step-display', 'active');
        
        // Small delay to show the final step
        setTimeout(() => {
            this.updateLoadingStep('step-display', 'completed');
            this.hideLoadingPopup();
        }, 500);
    }

    async processApparatusFile(content, filename) {
        try {
            this.updateStatus('Processing apparatus file...');
            
            // Basic client-side XML validation first
            if (!this.validateXML(content)) {
                return; // Error popup will be shown by validateXML
            }
            
            // Send file to backend for validation and processing
            await this.sendApparatusToBackend(content, filename);
            
        } catch (error) {
            this.showErrorPopup('Apparatus File Error', `Failed to process apparatus file: ${error.message}`);
        }
    }


    async processApparatusFileFromProject(content, filepath) {
        try {
            this.updateStatus('Processing apparatus file from project...');
            
            // Basic client-side XML validation first
            if (!this.validateXML(content)) {
                return; // Error popup will be shown by validateXML
            }
            
            // Send file to backend with project context for relative path resolution
            await this.sendApparatusToBackendWithProject(content, filepath);
            
        } catch (error) {
            this.showErrorPopup('Apparatus File Error', `Failed to process apparatus file: ${error.message}`);
        }
    }

    async processSynopticMapFileFromProject(content, filepath) {
        try {
            this.updateStatus('Processing synoptic map from project...');
            
            // Basic client-side XML validation first
            if (!this.validateXML(content)) {
                return; // Error popup will be shown by validateXML
            }
            
            // Send file to backend for processing
            await this.sendSynopticMapToBackend(content, filepath);
            
        } catch (error) {
            this.showErrorPopup('Synoptic Map File Error', `Failed to process synoptic map file: ${error.message}`);
        }
    }

    async sendApparatusToBackendWithProject(content, filepath) {
        try {
            // First validate the file with backend
            this.updateStatus('Validating apparatus file structure...');
            
            const validationResponse = await this.apiRequest('/apparatus/validate', {
                method: 'POST',
                body: JSON.stringify({
                    content: content,
                    filename: filepath
                })
            });

            if (!validationResponse.valid) {
                const messages = validationResponse.messages.join('\n');
                this.showErrorPopup('Invalid Apparatus File', messages);
                return;
            }

            // If validation passes, process the file with project context
            this.updateStatus('Processing apparatus file with project context...');
            
            const processResponse = await this.apiRequest('/project/open', {
                method: 'POST',
                body: JSON.stringify({
                    apparatus_content: content,
                    apparatus_filepath: filepath,
                    project_files: this.getProjectFileList()
                })
            });

            if (processResponse.success) {
                this.handleApparatusProcessingResult(processResponse, filepath);
            } else {
                this.showErrorPopup('Processing Error', processResponse.message || 'Unknown error occurred');
            }

        } catch (error) {
            this.showErrorPopup('Backend Error', `Failed to communicate with backend: ${error.message}`);
        }
    }

    getProjectFileList() {
        // Return a list of available files in the project for path resolution
        const fileList = {};
        for (const [path, fileData] of this.projectFiles) {
            fileList[path] = {
                content: fileData.content,
                size: fileData.file.size
            };
        }
        return fileList;
    }

    async sendApparatusToBackend(content, filename) {
        try {
            // First validate the file with backend
            this.updateStatus('Validating apparatus file structure...');
            
            const validationResponse = await this.apiRequest('/apparatus/validate', {
                method: 'POST',
                body: JSON.stringify({
                    content: content,
                    filename: filename
                })
            });

            if (!validationResponse.valid) {
                const messages = validationResponse.messages.join('\n');
                this.showErrorPopup('Invalid Apparatus File', messages);
                return;
            }

            // If validation passes, process the file
            this.updateStatus('Processing apparatus file with heipy...');
            
            const processResponse = await this.apiRequest('/apparatus/process', {
                method: 'POST',
                body: JSON.stringify({
                    content: content,
                    filename: filename
                })
            });

            if (processResponse.success) {
                this.handleApparatusProcessingResult(processResponse, filename);
            } else {
                this.showErrorPopup('Processing Error', processResponse.message || 'Unknown error occurred');
            }

        } catch (error) {
            this.showErrorPopup('Backend Error', `Failed to communicate with backend: ${error.message}`);
        }
    }

    async sendSynopticMapToBackend(content, filename) {
        try {
            this.updateStatus('Processing synoptic map with heipy...');
            
            const processResponse = await this.apiRequest('/synoptic/process', {
                method: 'POST',
                body: JSON.stringify({
                    content: content,
                    filename: filename
                })
            });

            if (processResponse.success) {
                this.handleSynopticMapProcessingResult(processResponse, filename);
            } else {
                this.showErrorPopup('Processing Error', processResponse.message || 'Unknown error occurred');
            }

        } catch (error) {
            this.showErrorPopup('Backend Error', `Failed to communicate with backend: ${error.message}`);
        }
    }

    handleApparatusProcessingResult(result, filename) {
        // Store apparatus data
        this.apparatusData = {
            entries: result.apparatus_entries || [],
            filename: filename,
            count: result.apparatus_count || 0
        };
        
        // If this result also contains synoptic map data (from project processing), store it
        if (result.synoptic_map && Object.keys(result.synoptic_map).length > 0) {
            this.synopticMapData = {
                synoptic_map: result.synoptic_map,
                filename: `${filename} (embedded)`,
                count: result.synoptic_map_count || 0
            };
        }
        
        // Store main text data if available
        if (result.main_text) {
            this.mainTextData = {
                content: result.main_text,
                filename: filename
            };
        }
        
        // Refresh display with apparatus, synoptic map, and main text data
        this.refreshDisplay();
    }

    handleSynopticMapProcessingResult(result, filename) {
        // Store synoptic map data        
        this.synopticMapData = {
            synoptic_map: result.synoptic_map || {},
            filename: filename,
            count: result.synoptic_map_count || 0
        };
        
        // Refresh display with both apparatus and synoptic map data
        this.refreshDisplay();
    }

    refreshDisplay() {
        const apparatusEntries = this.apparatusData ? this.apparatusData.entries : [];
        const synopticMap = this.synopticMapData ? this.synopticMapData.synoptic_map : {};
        
        // Merge apparatus entries with synoptic map to show complete list
        const completeEntries = this.mergeApparatusWithSynopticMap(apparatusEntries, synopticMap);
        
        if (completeEntries.length > 0 || apparatusEntries.length > 0) {
            // Create or update project tab
            const projectName = this.getCurrentDisplayFilename();
            
            // Close existing project tab if any
            const existingProjectTab = Array.from(this.tabs.values()).find(tab => tab.type === 'project');
            if (existingProjectTab) {
                this.closeTab(existingProjectTab.id);
            }
            
            // Create new project tab
            const tabId = this.createTab('project', projectName, null, {
                apparatusEntries: completeEntries.length > 0 ? completeEntries : apparatusEntries,
                apparatusData: this.apparatusData,
                synopticMapData: this.synopticMapData,
                mainTextData: this.mainTextData,
                filename: projectName
            });
            
            const apparatusCount = this.apparatusData ? this.apparatusData.count : 0;
            const totalLocations = Object.keys(synopticMap).length;
            const statusMessage = this.getStatusMessage(apparatusCount, totalLocations);
            this.updateStatus(statusMessage);
        } else {
            this.updateStatus('No data loaded');
        }
    }

    getCurrentDisplayFilename() {
        if (this.apparatusData && this.synopticMapData) {
            return `${this.apparatusData.filename} + ${this.synopticMapData.filename}`;
        } else if (this.apparatusData) {
            return this.apparatusData.filename;
        } else if (this.synopticMapData) {
            return this.synopticMapData.filename;
        }
        return 'No files loaded';
    }

    getStatusMessage(apparatusCount, totalLocations) {
        if (this.apparatusData && this.synopticMapData) {
            return `Loaded ${apparatusCount} apparatus entries from ${totalLocations} locations (apparatus + synoptic map)`;
        } else if (this.apparatusData) {
            return `Loaded ${apparatusCount} apparatus entries (apparatus only)`;
        } else if (this.synopticMapData) {
            return `Loaded ${totalLocations} locations (synoptic map only)`;
        }
        return 'No data loaded';
    }



    generateSingleEntryHTML(loc, entries) {
        
        const corresp = entries.length > 0 && entries[0].corresp ? entries[0].corresp : '';
        let html = `
        <div class="apparatus-display">
            <div class="classical-apparatus">
                <div class="classical-entry-group">`;

        // Show location as clickable button
        html += `<button class="apparatus-loc-button" 
                                data-loc="${this.escapeHtml(loc)}" 
                                data-corresp="${this.escapeHtml(corresp)}" 
                                onclick="window.heiCritApp.showLocationDetails('${this.escapeHtml(loc)}')">${this.escapeHtml(loc)}</button>`;
        
        // Process each entry in this location group
        entries.forEach((entry, index) => {
            html += '<div class="classical-subentry';
            if (entry.is_placeholder) {
                html += ' placeholder-entry';
            }
            html += '">';
            
            // Handle placeholder entries (no apparatus data)
            if (entry.is_placeholder) {
                html += ' <span class="no-apparatus">(no apparatus)</span>';
            } else {
                // Lemma content
                if (entry.lemma && entry.lemma.text) {
                    html += ` ${this.escapeHtml(entry.lemma.text)}`;
                }
                
                // Closing bracket
                html += ' ]';
                
                // Readings with witnesses
                if (entry.readings && entry.readings.length > 0) {
                    const readingParts = [];
                    
                    entry.readings.forEach(reading => {
                        let readingPart = ` ${this.escapeHtml(reading.text)}`;
                        
                        // Add witnesses in italics
                        if (reading.wit) {
                            // Clean up witness list (remove # symbols and extra spaces)
                            const witnesses = reading.wit.replace(/#/g, '').trim().split(/\s+/).join(' ');
                            if (witnesses) {
                                readingPart += ` <em class="apparatus-witnesses">${this.escapeHtml(witnesses)}</em>`;
                            }
                        }
                        
                        readingParts.push(readingPart);
                    });
                    
                    // Join readings with semicolons
                    html += readingParts.join(' ;');
                }
            }
            
            html += '</div>';
        });
        
        html += `
                </div>
            </div>
        </div>`;
        
        return html;
    }

    updateNavigationControls() {
        if (!this.activeTabId) return;
        const tab = this.tabs.get(this.activeTabId);
        if (!tab) return;
        
        const counter = document.getElementById(`apparatus-counter-${this.activeTabId}`);
        const prevBtn = document.querySelector(`button[data-tab="${this.activeTabId}"].apparatus-prev`);
        const nextBtn = document.querySelector(`button[data-tab="${this.activeTabId}"].apparatus-next`);
        
        // Update counter
        if (counter && tab.entryKeys) {
            counter.textContent = `${tab.currentEntryIndex + 1} / ${tab.entryKeys.length}`;
        }
        
        // Update button states
        if (prevBtn && tab.entryKeys) {
            prevBtn.disabled = tab.currentEntryIndex === 0;
        }
        if (nextBtn && tab.entryKeys) {
            nextBtn.disabled = tab.currentEntryIndex === tab.entryKeys.length - 1;
        }
    }

    // Old displayMainText method removed - now handled per tab in loadProjectDataIntoTab

    generateApparatusHTML(apparatusEntries, filename) {
        let html = `
        <div class="apparatus-display">
            <div class="apparatus-header">
                <h2>Apparatus Entries from ${filename}</h2>
                <p>Found ${apparatusEntries.length} apparatus entries</p>
            </div>
            <div class="apparatus-list">`;

        apparatusEntries.forEach((entry, index) => {
            html += `
            <div class="apparatus-entry" data-entry-id="${entry.id}">
                <div class="apparatus-entry-header">
                    <h3>Entry ${entry.id}</h3>
                </div>
                <div class="apparatus-content">`;

            // Display lemma if present
            if (entry.lemma) {
                html += `
                <div class="apparatus-lemma">
                    <strong>Lemma:</strong> ${this.escapeHtml(entry.lemma.text)}
                    ${Object.keys(entry.lemma.attributes).length > 0 ? 
                        `<span class="attributes">(${this.formatAttributes(entry.lemma.attributes)})</span>` : ''}
                </div>`;
            }

            // Display readings
            if (entry.readings && entry.readings.length > 0) {
                html += `<div class="apparatus-readings"><strong>Readings:</strong><ul>`;
                entry.readings.forEach(reading => {
                    html += `
                    <li class="reading">
                        ${this.escapeHtml(reading.text)}
                        ${Object.keys(reading.attributes).length > 0 ? 
                            `<span class="attributes">(${this.formatAttributes(reading.attributes)})</span>` : ''}
                    </li>`;
                });
                html += `</ul></div>`;
            }

            // Show XML content in a collapsible section
            html += `
                <details class="apparatus-xml">
                    <summary>Show XML</summary>
                    <pre class="xml-content">${this.escapeHtml(entry.xml_content)}</pre>
                </details>
            </div>
        </div>`;
        });

        html += `
            </div>
        </div>`;

        return html;
    }

    generateClassicalApparatusHTML(apparatusEntries, filename) {
        let html = `
        <div class="apparatus-display">
            <div class="apparatus-header">
                <h2>Critical Apparatus: ${filename}</h2>
                <p>Found ${apparatusEntries.length} apparatus entries</p>
            </div>
            <div class="classical-apparatus">`;

        // Group entries by corresp
        const groupedEntries = this.groupEntriesByCorresp(apparatusEntries);
        
        // Process each corresp group
        Object.keys(groupedEntries).forEach(corresp => {
            const entries = groupedEntries[corresp];
            const loc = entries.length > 0 && entries[0].loc ? entries[0].loc : '';
            
            html += '<div class="classical-entry-group">';
            
            // Show location as clickable button
            html += `<button class="apparatus-loc-button" data-loc="${this.escapeHtml(loc)}" data-corresp="${this.escapeHtml(corresp)}" onclick="window.heiCritApp.showLocationDetails('${this.escapeHtml(loc)}')">${this.escapeHtml(loc)}</button>`;
            
            // Process each entry in this location group
            entries.forEach((entry) => {
                html += '<div class="classical-subentry';
                if (entry.is_placeholder) {
                    html += ' placeholder-entry';
                }
                html += '">';
                
                // Handle placeholder entries (no apparatus data)
                if (entry.is_placeholder) {
                    html += ' <span class="no-apparatus">(no apparatus)</span>';
                } else {
                    // Lemma content
                    if (entry.lemma && entry.lemma.text) {
                        html += ` ${this.escapeHtml(entry.lemma.text)}`;
                    }
                    
                    // Closing bracket
                    html += ' ]';
                    
                    // Readings with witnesses
                    if (entry.readings && entry.readings.length > 0) {
                        const readingParts = [];
                        
                        entry.readings.forEach(reading => {
                            let readingPart = ` ${this.escapeHtml(reading.text)}`;
                            
                            // Add witnesses in italics
                            if (reading.wit) {
                                // Clean up witness list (remove # symbols and extra spaces)
                                const witnesses = reading.wit.replace(/#/g, '').trim().split(/\s+/).join(' ');
                                if (witnesses) {
                                    readingPart += ` <em class="apparatus-witnesses">${this.escapeHtml(witnesses)}</em>`;
                                }
                            }
                            
                            readingParts.push(readingPart);
                        });
                        
                        // Join readings with semicolons
                        html += readingParts.join(' ;');
                    }
                }
                
                html += '</div>';
            });
            
            html += '</div>';
        });

        html += `
            </div>
        </div>`;

        return html;
    }

    mergeApparatusWithSynopticMap(apparatusEntries, synopticMap) {
        
        // Create a map of apparatus entries by corresp for quick lookup
        const apparatusMap = {};
        apparatusEntries.forEach(entry => {
            const corresp = entry.corresp;
            if (corresp !== undefined && corresp !== null) {
                // Convert to string to match synoptic map keys
                const correspKey = String(corresp);
                if (!apparatusMap[correspKey]) {
                    apparatusMap[correspKey] = [];
                }
                apparatusMap[correspKey].push(entry);
            }
        });
        
        
        // Create complete entries list based on synoptic map
        const completeEntries = [];
        
        // If we have synoptic map, use all corresp values as potential entries
        if (Object.keys(synopticMap).length > 0) {
            Object.keys(synopticMap).forEach(corresp => {
                const correspKey = String(corresp);
                if (apparatusMap[correspKey]) {
                    // This corresp has apparatus data
                    apparatusMap[correspKey].forEach(entry => {
                        completeEntries.push({
                            ...entry,
                            synoptic_data: synopticMap[corresp]
                        });
                    });
                } else {
                    // This corresp has no apparatus data, create placeholder
                    const synopticData = synopticMap[corresp];
                    completeEntries.push({
                        corresp: corresp,
                        loc: synopticData.n || synopticData['n'] || corresp,
                        lemma: null,
                        readings: [],
                        synoptic_data: synopticData,
                        is_placeholder: true
                    });
                }
            });
        } else {
            // No synoptic map, just return apparatus entries as before
            return apparatusEntries;
        }
        
        return completeEntries;
    }

    groupEntriesByCorresp(apparatusEntries) {
        const grouped = {};
        
        apparatusEntries.forEach(entry => {
            const corresp = entry.corresp || '(no corresp)';
            if (!grouped[corresp]) {
                grouped[corresp] = [];
            }
            grouped[corresp].push(entry);
        });
        
        return grouped;
    }

    groupEntriesByLoc(apparatusEntries) {
        const grouped = {};
        
        apparatusEntries.forEach(entry => {
            const loc = entry.loc || '(no loc)';
            if (!grouped[loc]) {
                grouped[loc] = [];
            }
            grouped[loc].push(entry);
        });
        
        return grouped;
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    formatAttributes(attributes) {
        return Object.entries(attributes)
            .map(([key, value]) => `${key}="${value}"`)
            .join(', ');
    }

    isValidApparatusFile(xmlDoc) {
        // TODO: Add your validation logic for TEI apparatus files
        // This method should check if the XML structure contains the expected apparatus elements
        
        // Basic TEI structure check
        const teiRoot = xmlDoc.querySelector('TEI, tei');
        if (!teiRoot) {
            return false;
        }
        
        // Add more specific apparatus validation here based on your requirements
        // For now, just return true if it's a TEI file
        return true;
    }

    async saveAsFile() {
        const content = this.textarea.value;
        const defaultFilename = this.currentFile || 'document.xml';
        
        // Validate XML before saving
        if (!this.validateXML(content)) {
            return; // validateXML will show error popup
        }
        
        try {
            // Try to use the modern File System Access API
            if ('showSaveFilePicker' in window) {
                const fileHandle = await window.showSaveFilePicker({
                    suggestedName: defaultFilename,
                    types: [{
                        description: 'XML files',
                        accept: { 'text/xml': ['.xml'] },
                    }, {
                        description: 'TEI files', 
                        accept: { 'application/tei+xml': ['.tei'] },
                    }, {
                        description: 'Text files',
                        accept: { 'text/plain': ['.txt'] },
                    }],
                });
                
                const writable = await fileHandle.createWritable();
                await writable.write(content);
                await writable.close();
                
                this.currentFile = fileHandle.name;
                // File name is now displayed in the tab title
                this.updateStatus(`File saved as: ${fileHandle.name}`);
            } else {
                // Fallback to download for browsers without File System Access API
                this.downloadFile(content, defaultFilename);
            }
        } catch (error) {
            if (error.name !== 'AbortError') {
                this.updateStatus('Save failed: ' + error.message, 'error');
            }
        }
    }
    
    downloadFile(content, defaultFilename) {
        // For Firefox and other browsers without File System Access API,
        // prompt for filename first
        const filename = prompt('Save file as:', defaultFilename);
        if (!filename) {
            return; // User cancelled
        }
        
        const blob = new Blob([content], { type: 'application/octet-stream' });
        const link = document.createElement('a');
        link.href = URL.createObjectURL(blob);
        link.download = filename;
        
        // Force download without opening in new tab
        link.style.display = 'none';
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        
        setTimeout(() => URL.revokeObjectURL(link.href), 100);
        
        // Update current file reference if save was successful
        this.currentFile = filename;
        // File name is now displayed in the tab title
        this.updateStatus(`File saved as: ${filename}`);
    }
    
    validateXML(content) {
        if (!content.trim()) {
            return true; // Empty content is valid
        }
        
        try {
            const parser = new DOMParser();
            const xmlDoc = parser.parseFromString(content, 'text/xml');
            
            // Check for parsing errors
            const errorNode = xmlDoc.querySelector('parsererror');
            if (errorNode) {
                const errorMsg = errorNode.textContent || 'Unknown XML parsing error';
                this.showErrorPopup('XML Parsing Error', errorMsg);
                return false;
            }
            
            return true;
        } catch (error) {
            this.showErrorPopup('XML Validation Error', error.message);
            return false;
        }
    }
    
    showLoadingPopup() {
        // Remove existing loading popup if present
        const existingPopup = document.querySelector('.loading-overlay');
        if (existingPopup) {
            existingPopup.remove();
        }

        const overlay = document.createElement('div');
        overlay.className = 'loading-overlay';
        overlay.innerHTML = `
            <div class="loading-popup">
                <h3>Loading Project</h3>
                <p>Processing TEI files and building apparatus...</p>
                <div class="loading-spinner"></div>
                <div class="loading-steps">
                    <div class="loading-step" id="step-reading">Reading project files</div>
                    <div class="loading-step" id="step-processing">Processing apparatus</div>
                    <div class="loading-step" id="step-synoptic">Loading synoptic map</div>
                    <div class="loading-step" id="step-maintext">Generating main text</div>
                    <div class="loading-step" id="step-display">Preparing display</div>
                </div>
            </div>
        `;
        document.body.appendChild(overlay);
    }

    updateLoadingStep(stepId, status = 'active') {
        const step = document.getElementById(stepId);
        if (step) {
            // Remove previous status classes
            step.classList.remove('active', 'completed');
            // Add new status
            if (status === 'completed') {
                step.classList.add('completed');
            } else if (status === 'active') {
                step.classList.add('active');
            }
        }
    }

    hideLoadingPopup() {
        const overlay = document.querySelector('.loading-overlay');
        if (overlay) {
            overlay.remove();
        }
    }

    showErrorPopup(title, message) {
        // Hide loading popup if showing
        this.hideLoadingPopup();
        
        // Create a simple error modal
        const modal = document.createElement('div');
        modal.style.cssText = `
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0,0,0,0.5);
            display: flex;
            align-items: center;
            justify-content: center;
            z-index: 1000;
        `;
        
        const dialog = document.createElement('div');
        dialog.style.cssText = `
            background: white;
            padding: 2rem;
            border-radius: 0.5rem;
            max-width: 500px;
            max-height: 400px;
            overflow-y: auto;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        `;
        
        dialog.innerHTML = `
            <h3 style="margin: 0 0 1rem 0; color: #dc3545;">${title}</h3>
            <pre style="white-space: pre-wrap; font-family: monospace; background: #f8f9fa; padding: 1rem; border-radius: 0.25rem; margin: 1rem 0;">${message}</pre>
            <button id="closeError" style="background: #007bff; color: white; border: none; padding: 0.5rem 1rem; border-radius: 0.25rem; cursor: pointer;">Close</button>
        `;
        
        modal.appendChild(dialog);
        document.body.appendChild(modal);
        
        // Close modal handlers
        const closeModal = () => document.body.removeChild(modal);
        document.getElementById('closeError').addEventListener('click', closeModal);
        modal.addEventListener('click', (e) => {
            if (e.target === modal) closeModal();
        });
        
        this.updateStatus('XML parsing error - check document', 'error');
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

    async showLocationDetails(loc) {
        if (!this.activeTabId) return;
        const detailsContent = document.getElementById(`apparatus-details-content-${this.activeTabId}`);
        
        // Find entries for this location
        const apparatusEntries = this.apparatusData ? this.apparatusData.entries : [];
        const synopticMap = this.synopticMapData ? this.synopticMapData.synoptic_map : {};
        
        // Get apparatus entry for this location
        const locationEntries = apparatusEntries.filter(entry => entry.loc === loc);
        
        // Get synoptic map data for this location
        const synopticData = synopticMap[loc];
        
        let message = `<strong>Location: ${this.escapeHtml(loc)}</strong><br><br>`;
        
        // Fetch and display sigla mapping
        try {
            const siglaResponse = await this.apiRequest('/sigla-mapping');
            if (siglaResponse.success && siglaResponse.sigla_mapping) {
                message += `<strong>Sigla Mapping (${siglaResponse.count} entries):</strong><br>`;
                const mapping = siglaResponse.sigla_mapping;
                for (const [filename, data] of Object.entries(mapping)) {
                    message += `${this.escapeHtml(filename)}: ${this.escapeHtml(data.siglum)} (${this.escapeHtml(data.synoptic_pre)})<br>`;
                }
                message += '<br>';
            } else {
                message += '<strong>Sigla Mapping:</strong> Not loaded or empty<br><br>';
            }
        } catch (error) {
            message += '<strong>Sigla Mapping:</strong> Error loading<br><br>';
        }
        
        if (locationEntries.length > 0) {
            message += `<strong>Apparatus entries:</strong> ${locationEntries.length}<br>`;
            locationEntries.forEach((entry, index) => {
                if (entry.lemma) {
                    message += `Entry ${index + 1}: "${this.escapeHtml(entry.lemma.text)}"<br>`;
                }
                if (entry.readings && entry.readings.length > 0) {
                    message += `Readings: ${entry.readings.length}<br>`;
                }
            });
        } else {
            message += 'No apparatus entries for this location<br>';
        }
        
        if (synopticData) {
            message += `<br><strong>Synoptic map data:</strong><br>`;
            message += `Targets: ${synopticData.target ? synopticData.target.join(', ') : 'none'}<br>`;
        } else {
            message += '<br>No synoptic map data for this location<br>';
        }
        
        if (detailsContent) {
            detailsContent.innerHTML = message;
        }
    }

    // Old global navigation methods removed - now handled per tab

    goToCorrespEntry(containerId) {
        if (!containerId) {
            return;
        }
        
        // Find active project tab
        const activeTab = this.tabs.get(this.activeTabId);
        if (!activeTab || activeTab.type !== 'project') {
            // If no active project tab, just highlight the synoptic unit
            this.highlightSynopticUnit(containerId);
            return;
        }
        
        // Find the entry with the matching corresp (ignoring prefix)
        // containerId is like "l_5", corresp is like "a:l_5"  
        const targetIndex = activeTab.entryKeys.findIndex(corresp => {
            // Extract the part after the colon (if present)
            const correspSuffix = corresp.includes(':') ? corresp.split(':')[1] : corresp;
            return correspSuffix === containerId;
        });
        
        if (targetIndex !== -1) {
            activeTab.currentEntryIndex = targetIndex;
            this.updateApparatusDisplay(activeTab.id);
            
            // Scroll to the apparatus panel if it's not visible
            const apparatusPanel = document.querySelector('.apparatus-panel');
            if (apparatusPanel) {
                apparatusPanel.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }
        } else {
            this.highlightSynopticUnit(containerId);
        }
    }

    highlightSynopticUnit(containerId) {
        // Remove existing highlights in all tabs
        document.querySelectorAll('.synoptic-unit.active').forEach(unit => {
            unit.classList.remove('active');
        });

        // If we have an active tab, look within that tab's content
        let searchContext = document;
        if (this.activeTabId) {
            const tabPanel = document.getElementById(`tab-panel-${this.activeTabId}`);
            if (tabPanel) {
                searchContext = tabPanel;
            }
        }

        // Find and highlight the synoptic unit containing the element with this container ID
        const targetElement = searchContext.querySelector(`[data-container-id="${containerId}"]`);
        if (targetElement) {
            const synopticUnit = targetElement.closest('.synoptic-unit');
            if (synopticUnit) {
                synopticUnit.classList.add('active');
                // Scroll to make sure it's visible
                synopticUnit.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }
        }
    }

}

document.addEventListener('DOMContentLoaded', () => {
    window.heiCritApp = new HeiCritApp();
});