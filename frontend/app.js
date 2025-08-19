const API_BASE = 'http://127.0.0.1:5000/api';

class HeiCritApp {
    constructor() {
        this.currentFile = null;
        this.textarea = null;
        this.highlightCode = null;
        this.apparatusData = null;
        this.synopticMapData = null;
        this.projectFiles = new Map(); // Store all project files
        this.init();
    }

    init() {
        this.textarea = document.getElementById('editor-textarea');
        this.highlightCode = document.getElementById('editor-code');
        this.bindEvents();
        this.setupEditor();
        this.updateStatus('Ready');
    }

    bindEvents() {
        document.getElementById('openFile').addEventListener('click', () => this.openFile());
        document.getElementById('openProjectDirectory').addEventListener('click', () => this.openProjectDirectory());
        document.getElementById('saveFile').addEventListener('click', () => this.saveFile());
        document.getElementById('saveAsFile').addEventListener('click', () => this.saveAsFile());
    }

    setupEditor() {
        // Sync textarea input with syntax highlighting
        this.textarea.addEventListener('input', () => {
            this.updateHighlighting();
        });

        this.textarea.addEventListener('scroll', () => {
            this.syncScroll();
        });

        this.textarea.addEventListener('keydown', (e) => {
            // Handle tab key for indentation
            if (e.key === 'Tab') {
                e.preventDefault();
                this.insertTab();
            }
        });
    }

    updateHighlighting() {
        const content = this.textarea.value;
        this.highlightCode.textContent = content;
        Prism.highlightElement(this.highlightCode);
    }

    syncScroll() {
        const highlight = document.getElementById('editor-highlight');
        highlight.scrollTop = this.textarea.scrollTop;
        highlight.scrollLeft = this.textarea.scrollLeft;
    }

    insertTab() {
        const start = this.textarea.selectionStart;
        const end = this.textarea.selectionEnd;
        const value = this.textarea.value;
        
        this.textarea.value = value.substring(0, start) + '    ' + value.substring(end);
        this.textarea.selectionStart = this.textarea.selectionEnd = start + 4;
        this.updateHighlighting();
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
            
            // Switch to XML editor view for regular files
            this.showXmlEditorView();
            
            this.textarea.value = data.content;
            this.updateHighlighting();
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
                    // Switch to XML editor view for regular files
                    this.showXmlEditorView();
                    
                    this.textarea.value = e.target.result;
                    this.updateHighlighting();
                    document.getElementById('currentFile').textContent = file.name;
                    this.currentFile = file.name;
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
            
            this.updateStatus(`Loaded ${this.projectFiles.size} files from project directory`);
            
            // Auto-detect and process apparatus and synoptic map files
            await this.autoProcessProjectFiles();
            
        } catch (error) {
            console.error('Failed to process project directory:', error);
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
            const apparatusFile = apparatusFiles[0]; // Use first apparatus file found
            console.log(`Processing apparatus file: ${apparatusFile.path}`);
            await this.processApparatusFileFromProject(apparatusFile.content, apparatusFile.path);
        }
        
        // Process synoptic map if found
        if (synopticFiles.length > 0) {
            const synopticFile = synopticFiles[0]; // Use first synoptic file found
            console.log(`Processing synoptic map: ${synopticFile.path}`);
            await this.processSynopticMapFileFromProject(synopticFile.content, synopticFile.path);
        }
        
        if (apparatusFiles.length === 0 && synopticFiles.length === 0) {
            this.updateStatus('No apparatus or synoptic map files found in project directory');
            this.showErrorPopup('No Files Found', 'No apparatus files found in apparatus/ directory or synoptic map files found in synopses/ directory.');
        }
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
            console.error('Failed to process apparatus file:', error);
            this.showErrorPopup('Apparatus File Error', `Failed to process apparatus file: ${error.message}`);
        }
    }

    async processSynopticMapFile(content, filename) {
        try {
            this.updateStatus('Processing synoptic map file...');
            
            // Basic client-side XML validation first
            if (!this.validateXML(content)) {
                return; // Error popup will be shown by validateXML
            }
            
            // Send file to backend for processing
            await this.sendSynopticMapToBackend(content, filename);
            
        } catch (error) {
            console.error('Failed to process synoptic map file:', error);
            this.showErrorPopup('Synoptic Map File Error', `Failed to process synoptic map file: ${error.message}`);
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
            console.error('Failed to process apparatus file:', error);
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
            console.error('Failed to process synoptic map file:', error);
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
            
            const processResponse = await this.apiRequest('/apparatus/process-with-project', {
                method: 'POST',
                body: JSON.stringify({
                    content: content,
                    filepath: filepath,
                    project_files: this.getProjectFileList()
                })
            });

            if (processResponse.success) {
                this.handleApparatusProcessingResult(processResponse, filepath);
            } else {
                this.showErrorPopup('Processing Error', processResponse.message || 'Unknown error occurred');
            }

        } catch (error) {
            console.error('Backend communication failed:', error);
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
            console.error('Backend communication failed:', error);
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
            console.error('Backend communication failed:', error);
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
        
        // Refresh display with both apparatus and synoptic map data
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
        
        if (completeEntries.length > 0) {
            // Display all entries (from synoptic map) with apparatus data where available
            this.displayApparatusEntries(completeEntries, this.getCurrentDisplayFilename());
            
            const apparatusCount = this.apparatusData ? this.apparatusData.count : 0;
            const totalLocations = Object.keys(synopticMap).length;
            const statusMessage = this.getStatusMessage(apparatusCount, totalLocations);
            this.updateStatus(statusMessage);
        } else if (apparatusEntries.length > 0) {
            // Only apparatus data, no synoptic map
            this.displayApparatusEntries(apparatusEntries, this.apparatusData.filename);
            this.updateStatus(`Loaded ${this.apparatusData.count} apparatus entries from ${this.apparatusData.filename}`);
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

    displaySimpleApparatusList(locAttributes, filename, count) {
        console.log('displaySimpleApparatusList called with:', locAttributes, filename, count);
        
        // Switch to apparatus view
        this.showApparatusView();
        
        // Create simple HTML display of loc attributes
        let htmlContent = `
        <div class="apparatus-display">
            <div class="apparatus-header">
                <h2>Apparatus Entries from ${filename}</h2>
                <p>Found ${count} apparatus entries</p>
            </div>
            <div class="apparatus-list">
                <ul>`;

        locAttributes.forEach((loc, index) => {
            htmlContent += `
                <li class="apparatus-entry-simple">
                    <strong>Entry ${index + 1}:</strong> loc="${loc || '(no loc attribute)'}"
                </li>`;
        });

        htmlContent += `
                </ul>
            </div>
        </div>`;
        
        console.log('Generated HTML content:', htmlContent.substring(0, 200) + '...');
        
        // Set content in apparatus container
        const apparatusContent = document.getElementById('apparatus-content');
        console.log('Setting apparatus content...');
        apparatusContent.innerHTML = htmlContent;
        console.log('Apparatus content set successfully');
        
        // Update current file reference
        this.currentFile = filename;
        document.getElementById('currentFile').textContent = `${filename} (${count} apparatus entries)`;
        console.log('Display completed');
    }

    showXmlEditorView() {
        // Show XML editor, hide apparatus view
        document.getElementById('xml-editor-container').style.display = 'block';
        document.getElementById('apparatus-container').style.display = 'none';
    }

    showApparatusView() {
        // Show apparatus view, hide XML editor
        document.getElementById('xml-editor-container').style.display = 'none';
        document.getElementById('apparatus-container').style.display = 'block';
    }

    displayApparatusEntries(apparatusEntries, filename) {
        // Switch to apparatus view
        this.showApparatusView();
        
        // Create HTML display of apparatus entries in classical format
        let htmlContent = this.generateClassicalApparatusHTML(apparatusEntries, filename);
        
        // Set content in apparatus container
        const apparatusContent = document.getElementById('apparatus-content');
        apparatusContent.innerHTML = htmlContent;
        
        // Update current file reference
        this.currentFile = filename;
        document.getElementById('currentFile').textContent = `${filename} (${apparatusEntries.length} apparatus entries)`;
    }

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

        // Group entries by loc
        const groupedEntries = this.groupEntriesByLoc(apparatusEntries);
        
        // Process each location group
        Object.keys(groupedEntries).forEach(loc => {
            const entries = groupedEntries[loc];
            
            html += '<div class="classical-entry-group">';
            
            // Show location only once for the group
            html += `<strong class="apparatus-loc">${this.escapeHtml(loc)}</strong>`;
            
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
        // Create a map of apparatus entries by loc for quick lookup
        const apparatusMap = {};
        apparatusEntries.forEach(entry => {
            const loc = entry.loc;
            if (loc) {
                if (!apparatusMap[loc]) {
                    apparatusMap[loc] = [];
                }
                apparatusMap[loc].push(entry);
            }
        });
        
        // Create complete entries list based on synoptic map
        const completeEntries = [];
        
        // If we have synoptic map, use all n values as potential entries
        if (Object.keys(synopticMap).length > 0) {
            Object.keys(synopticMap).forEach(n => {
                if (apparatusMap[n]) {
                    // This location has apparatus data
                    apparatusMap[n].forEach(entry => {
                        completeEntries.push({
                            ...entry,
                            synoptic_data: synopticMap[n]
                        });
                    });
                } else {
                    // This location has no apparatus data, create placeholder
                    completeEntries.push({
                        loc: n,
                        lemma: null,
                        readings: [],
                        synoptic_data: synopticMap[n],
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
                document.getElementById('currentFile').textContent = fileHandle.name;
                this.updateStatus(`File saved as: ${fileHandle.name}`);
            } else {
                // Fallback to download for browsers without File System Access API
                this.downloadFile(content, defaultFilename);
            }
        } catch (error) {
            if (error.name !== 'AbortError') {
                console.error('Save failed:', error);
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
        document.getElementById('currentFile').textContent = filename;
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
    
    showErrorPopup(title, message) {
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
}

document.addEventListener('DOMContentLoaded', () => {
    new HeiCritApp();
});