const API_BASE = 'http://127.0.0.1:5000/api';

class HeiCritApp {
    constructor() {
        this.currentFile = null;
        this.textarea = null;
        this.highlightCode = null;
        this.apparatusData = null;
        this.synopticMapData = null;
        this.mainTextData = null; // Store main text data
        this.leithsInfo = null; // Store leiths-info with siglum
        this.witnessOrder = []; // Store witness order from apparatus listWit
        this.witnessMapping = {}; // Store witness-to-prefix mapping from apparatus
        this.projectFiles = new Map(); // Store all project files
        
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
            data: data,
            listeners: [] // Store event listeners for proper cleanup
        };
        
        this.tabs.set(tabId, tab);
        
        // Clear empty workspace when creating first tab
        const tabContent = document.getElementById('tabContent');
        const emptyWorkspace = tabContent.querySelector('.empty-workspace');
        if (emptyWorkspace) {
            emptyWorkspace.remove();
        }
        
        this.renderTabs();
        this.switchToTab(tabId);
        return tabId;
    }

    closeTab(tabId) {
        if (!this.tabs.has(tabId)) return;
        
        const tab = this.tabs.get(tabId);
        
        // Clean up stored event listeners to prevent memory leaks
        if (tab && tab.listeners) {
            tab.listeners.forEach(listener => {
                listener.target.removeEventListener(listener.event, listener.handler);
            });
        }
        
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
        let isNewPanel = false;
        if (!panel) {
            panel = this.createTabPanel(tabId);
            isNewPanel = true;
        }
        panel.classList.add('active');
        
        this.activeTabId = tabId;
        this.renderTabs();
        
        // Only setup tab content when panel is first created
        if (isNewPanel) {
            const tab = this.tabs.get(tabId);
            this.setupTabContent(tab);
        }
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
                
                // Check file size and show popup if highlighting is disabled
                const fileSize = tab.content.length;
                const SIZE_THRESHOLD = 2000 * 1024; // 2MB threshold (matching updateHighlighting)
                
                if (fileSize > SIZE_THRESHOLD) {
                    // Show popup notification about disabled highlighting
                    this.showHighlightingDisabledPopup(fileSize);
                }
                
                // Apply highlighting (will be conditional based on file size)
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

        // Get tab reference to store listeners
        const tab = this.tabs.get(tabId);
        if (!tab) return;

        // Debounce highlighting updates for better performance
        let highlightTimer;
        const debouncedHighlight = () => {
            clearTimeout(highlightTimer);
            highlightTimer = setTimeout(() => {
                this.updateHighlighting(textarea, highlightCode);
            }, 16); // ~60fps refresh rate
        };

        // Enhanced scroll synchronization
        const syncScrollNow = () => this.syncScroll(textarea, highlightCode);

        // Add event listeners
        textarea.addEventListener('input', debouncedHighlight);
        textarea.addEventListener('scroll', syncScrollNow);
        textarea.addEventListener('input', syncScrollNow);
        textarea.addEventListener('keyup', syncScrollNow);
        
        // Store window resize listener reference for cleanup
        const resizeListener = () => syncScrollNow();
        window.addEventListener('resize', resizeListener);
        tab.listeners.push({
            target: window,
            event: 'resize',
            handler: resizeListener
        });

        const keydownHandler = (e) => {
            // Handle tab key for indentation
            if (e.key === 'Tab') {
                e.preventDefault();
                this.insertTab(textarea, highlightCode);
            }
        };
        textarea.addEventListener('keydown', keydownHandler);
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

        // Add click handler for subentries to make them active
        const tabPanel = document.getElementById(`panel-${tabId}`);
        if (tabPanel) {
            tabPanel.addEventListener('click', (e) => {
                const subentry = e.target.closest('.classical-subentry[data-subentry-index]');
                if (subentry) {
                    const subentryIndex = parseInt(subentry.getAttribute('data-subentry-index'));
                    const corresp = subentry.getAttribute('data-corresp');
                    this.setActiveSubentry(tabId, corresp, subentryIndex);
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
            tab.activeSubentryIndex = 0; // Track which subentry is active within current location
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
            
            // Mark gap symbols that have apparatus content
            this.markGapSymbolsWithContent(tab);

            // Show navigation if needed
            const navigation = document.getElementById(`apparatus-navigation-${tabId}`);
            if (navigation && tab.entryKeys.length > 1) {
                navigation.style.display = 'flex';
            }
        }
    }

    markGapSymbolsWithContent(tab) {
        if (!tab || !tab.apparatusEntries) return;
        
        // Get all apparatus entries that are NOT placeholders
        const entriesWithContent = tab.apparatusEntries.filter(entry => !entry.is_placeholder);
        
        // Create a set of container IDs that have apparatus content
        const containerIdsWithContent = new Set();
        entriesWithContent.forEach(entry => {
            if (entry.corresp) {
                // Extract container ID from corresp (remove prefix if present)
                const containerId = entry.corresp.includes(':') ? entry.corresp.split(':')[1] : entry.corresp;
                containerIdsWithContent.add(containerId);
            }
        });
        
        // Find all .tei-gap-synoptic elements in the main text
        const gapElements = document.querySelectorAll('.tei-gap-synoptic[data-container-id]');
        gapElements.forEach(gapElement => {
            const containerId = gapElement.getAttribute('data-container-id');
            if (containerId && containerIdsWithContent.has(containerId)) {
                gapElement.classList.add('has-content');
            } else {
                gapElement.classList.remove('has-content');
            }
        });
    }

    updateHighlighting(textarea, highlightCode) {
        if (!textarea || !highlightCode) return;
        
        const content = textarea.value;
        const fileSize = content.length;
        const SIZE_THRESHOLD = 2000 * 1024; // 2MB threshold for disabling highlighting
        
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
        
        // Conditionally apply syntax highlighting based on file size
        if (fileSize > SIZE_THRESHOLD) {
            // For large files, skip Prism.js highlighting to improve performance
            // Remove any existing Prism classes to show plain text
            highlightCode.className = '';
            // Ensure the highlight element is visible (not hidden by empty workspace)
            const highlightParent = highlightCode.parentElement;
            if (highlightParent) {
                highlightParent.style.display = 'block';
            }
        } else {
            // For smaller files, apply normal syntax highlighting
            // Ensure the language class is set for XML
            if (!highlightCode.classList.contains('language-xml')) {
                highlightCode.classList.add('language-xml');
            }
            
            // Apply Prism.js highlighting
            if (typeof Prism !== 'undefined') {
                Prism.highlightElement(highlightCode);
            }
            
            // Ensure the highlight element is visible
            const highlightParent = highlightCode.parentElement;
            if (highlightParent) {
                highlightParent.style.display = 'block';
            }
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
        const htmlContent = this.generateSingleEntryHTML(currentLoc, currentEntries, tab.activeSubentryIndex || 0);
        
        // Set content
        const content = document.getElementById(`apparatus-content-${tabId}`);
        if (content) {
            content.innerHTML = htmlContent;
        }

        // Update navigation controls
        this.updateNavigationControls(tabId);
        
        // Show location details for current entry
        if (currentCorresp) {
            this.showLocationDetailsForTab(tabId, currentCorresp);
        }
        
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
            tab.activeSubentryIndex = 0; // Reset to first subentry when navigating
            this.updateApparatusDisplay(tabId);
        }
    }

    showNextEntry(tabId) {
        const tab = this.tabs.get(tabId);
        if (!tab) return;

        if (tab.currentEntryIndex < tab.entryKeys.length - 1) {
            tab.currentEntryIndex++;
            tab.activeSubentryIndex = 0; // Reset to first subentry when navigating
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
            tab.activeSubentryIndex = 0; // Reset to first subentry when navigating
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

    setActiveSubentry(tabId, corresp, subentryIndex) {
        const tab = this.tabs.get(tabId);
        if (!tab) return;

        // Update active subentry index for current corresp
        tab.activeSubentryIndex = subentryIndex;

        // Remove active class from all subentries in this tab
        const tabPanel = document.getElementById(`panel-${tabId}`);
        if (tabPanel) {
            tabPanel.querySelectorAll('.classical-subentry.active').forEach(entry => {
                entry.classList.remove('active');
            });

            // Add active class to the selected subentry
            const activeSubentry = tabPanel.querySelector(
                `.classical-subentry[data-corresp="${corresp}"][data-subentry-index="${subentryIndex}"]`
            );
            if (activeSubentry) {
                activeSubentry.classList.add('active');
                
                // Highlight corresponding tokens
                this.highlightTokensForEntry(tabId, corresp, subentryIndex);
            }
        }
    }

    highlightTokensForEntry(tabId, corresp, subentryIndex) {
        const tab = this.tabs.get(tabId);
        if (!tab) return;

        // Clear any existing token highlights
        this.clearTokenHighlights(tabId);

        // Get the entry data
        const entries = tab.groupedEntries[corresp];
        if (!entries || subentryIndex >= entries.length) return;

        const entry = entries[subentryIndex];
        if (entry.is_placeholder) return;

        // Highlight lemma tokens in green
        if (entry.lemma && entry.lemma.attributes && entry.lemma.attributes.corresp) {
            this.highlightTokensFromCorresp(entry.lemma.attributes.corresp, 'lemma');
        }

        // Highlight reading tokens in yellow
        if (entry.readings && entry.readings.length > 0) {
            entry.readings.forEach(reading => {
                if (reading.attributes && reading.attributes.corresp) {
                    this.highlightTokensFromCorresp(reading.attributes.corresp, 'reading');
                }
            });
        }
    }

    clearTokenHighlights(tabId) {
        // Remove all token highlighting classes
        const tabPanel = document.getElementById(`panel-${tabId}`);
        if (tabPanel) {
            tabPanel.querySelectorAll('.syn-token.highlight-lemma, .syn-token.highlight-reading').forEach(token => {
                token.classList.remove('highlight-lemma', 'highlight-reading');
            });
        }
    }

    highlightTokensFromCorresp(correspValue, type) {
        // Parse corresp attribute like "a:range(w_12_1, w_12_2)" or "ba:w_12_1 bb:w_12_1"
        console.log(`Highlighting ${type} tokens from corresp: ${correspValue}`);
        
        // More sophisticated parsing to handle ranges with spaces
        const correspParts = [];
        let currentPart = '';
        let inRange = false;
        
        const tokens = correspValue.split(/\s+/);
        for (const token of tokens) {
            if (token.includes('range(')) {
                inRange = true;
                currentPart = token;
            } else if (inRange && token.endsWith(')')) {
                currentPart += ' ' + token;
                correspParts.push(currentPart);
                currentPart = '';
                inRange = false;
            } else if (inRange) {
                currentPart += ' ' + token;
            } else {
                correspParts.push(token);
            }
        }
        
        // Handle case where we're still in a range at the end
        if (currentPart) {
            correspParts.push(currentPart);
        }
        
        correspParts.forEach(part => {
            console.log(`Processed part: "${part}"`);
            if (part.includes(':')) {
                const colonIndex = part.indexOf(':');
                const prefix = part.substring(0, colonIndex);
                const tokenSpec = part.substring(colonIndex + 1);
                console.log(`Processing prefix: "${prefix}", tokenSpec: "${tokenSpec}"`);
                this.highlightTokensForPrefix(prefix, tokenSpec, type);
            }
        });
    }

    highlightTokensForPrefix(prefix, tokenSpec, type) {
        // Find the syn-line-wit element with matching prefix
        const witElement = document.querySelector(`.syn-line-wit[data-line-id*="${prefix}:"]`);
        console.log(`Looking for wit element with prefix ${prefix}, found:`, witElement);
        if (!witElement) return;

        const synLine = witElement.closest('.syn-line');
        console.log(`Found syn-line:`, synLine);
        if (!synLine) return;

        const synLineContent = synLine.querySelector('.syn-line-content');
        console.log(`Found syn-line-content:`, synLineContent);
        if (!synLineContent) return;

        if (tokenSpec.startsWith('range(') && tokenSpec.endsWith(')')) {
            // Handle range specification like "range(w_12_1, w_12_2)"
            const rangeContent = tokenSpec.slice(6, -1); // Remove "range(" and ")"
            const [startToken, endToken] = rangeContent.split(',').map(s => s.trim());
            console.log(`Range: ${startToken} to ${endToken}`);
            this.highlightTokenRange(synLineContent, startToken, endToken, type);
        } else {
            // Handle single token like "w_12_1"
            console.log(`Single token: ${tokenSpec}`);
            this.highlightSingleToken(synLineContent, tokenSpec, type);
        }
    }

    highlightSingleToken(container, tokenId, type) {
        const token = container.querySelector(`.syn-token[data-token-id="${tokenId}"]`);
        console.log(`Looking for token with ID: ${tokenId}, found:`, token);
        if (token) {
            token.classList.add(`highlight-${type}`);
            console.log(`Added highlight-${type} class to token`);
        }
    }

    highlightTokenRange(container, startTokenId, endTokenId, type) {
        const allTokens = container.querySelectorAll('.syn-token[data-token-id]');
        console.log(`Range highlighting: ${startTokenId} to ${endTokenId}, found ${allTokens.length} tokens`);
        let inRange = false;
        let foundStart = false;

        for (const token of allTokens) {
            const tokenId = token.getAttribute('data-token-id');
            console.log(`Checking token: ${tokenId}`);
            
            if (tokenId === startTokenId) {
                inRange = true;
                foundStart = true;
                console.log(`Found start token: ${tokenId}`);
            }
            
            if (inRange) {
                token.classList.add(`highlight-${type}`);
                console.log(`Highlighted token: ${tokenId}`);
            }
            
            if (tokenId === endTokenId && foundStart) {
                console.log(`Found end token: ${tokenId}, stopping`);
                break;
            }
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
                // Show loading popup
                this.showFileLoadingPopup();
                this.updateStatus('Opening file...');
                
                const reader = new FileReader();
                reader.onload = (e) => {
                    // Hide loading popup
                    this.hideFileLoadingPopup();
                    
                    // Create a new tab for the file
                    this.createTab('file', file.name, e.target.result, {
                        filename: file.name,
                        filepath: file.name
                    });
                    
                    this.updateStatus(`Opened: ${file.name}`);
                };
                
                reader.onerror = () => {
                    // Hide loading popup on error
                    this.hideFileLoadingPopup();
                    this.updateStatus('Failed to open file', 'error');
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
            .filter(([path]) => path.includes('/apparatus/') && path.endsWith('.xml'))
            .map(([path, fileData]) => ({ path, ...fileData }));
        
        // Look for synoptic map files in synopses/ directory
        const synopticFiles = Array.from(this.projectFiles.entries())
            .filter(([path]) => path.includes('/synopses/') && path.endsWith('.xml'))
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
            // Synoptic map processing is already handled by /api/project/open endpoint
            // No need for separate processing here
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

    handleApparatusProcessingResult(result, filename) {
        // Store apparatus data
        this.apparatusData = {
            entries: result.apparatus_entries || [],
            filename: filename,
            count: result.apparatus_count || 0
        };
        
        // Store leiths-info if available (contains siglum for main text)
        if (result['leiths-info']) {
            this.leithsInfo = result['leiths-info'];
        }
        
        // Store witness order if available
        if (result.witness_order) {
            this.witnessOrder = result.witness_order;
        }
        
        // Store witness mapping if available
        if (result.witness_mapping) {
            this.witnessMapping = result.witness_mapping;
        }
        
        // If this result also contains synoptic map data (from project processing), store it
        if (result.synoptic_map && Object.keys(result.synoptic_map).length > 0) {
            this.synopticMapData = {
                synoptic_map: result.synoptic_map,
                synoptic_wits: result.synoptic_wits || {},
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
            synoptic_wits: result.synoptic_wits || {},
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
        // If we have leiths-info with siglum, use "App: X" format
        if (this.leithsInfo && this.leithsInfo.siglum) {
            return `App: ${this.leithsInfo.siglum}`;
        }
        
        // Fallback to original filename display
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



    generateSingleEntryHTML(loc, entries, activeSubentryIndex = 0) {
        const corresp = entries.length > 0 && entries[0].corresp ? entries[0].corresp : '';
        let html = `
        <div class="apparatus-display">
            <div class="classical-apparatus">
                <div class="classical-entry-group">`;

        // Show location as bold span
        html += `<span class="apparatus-loc-span" 
                                data-loc="${this.escapeHtml(loc)}" 
                                data-corresp="${this.escapeHtml(corresp)}">${this.escapeHtml(loc)}</span>`;
        
        // Process each entry in this location group
        entries.forEach((entry, index) => {
            const isActive = index === activeSubentryIndex;
            
            html += `<div class="classical-subentry${entry.is_placeholder ? ' placeholder-entry' : ''}${isActive ? ' active' : ''}" 
                         data-subentry-index="${index}" 
                         data-corresp="${this.escapeHtml(corresp)}">`;
            
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

    getSiglumForWitness(witnessId) {
        // Get siglum from synoptic_wits mapping if available
        if (this.synopticMapData && this.synopticMapData.synoptic_wits) {
            const witInfo = this.synopticMapData.synoptic_wits[witnessId];
            if (witInfo && witInfo.siglum) {
                return witInfo.siglum;
            }
        }
        // Fallback to witness ID if no siglum found
        return witnessId;
    }

    createSynLine(siglum, data) {
        return `<div class="syn-line">
                    <div class="syn-line-wit" data-line-id="${this.escapeHtml(data.lineId)}">
                        ${this.escapeHtml(siglum)}:
                    </div> 
                    <div class="syn-line-content">${data.text}</div>
                </div>`;
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

    showFileLoadingPopup() {
        // Remove existing loading popup if present
        const existingPopup = document.querySelector('.file-loading-overlay');
        if (existingPopup) {
            existingPopup.remove();
        }

        const overlay = document.createElement('div');
        overlay.className = 'file-loading-overlay';
        overlay.innerHTML = `
            <div class="file-loading-popup">
                <h3>Opening File</h3>
                <p>Please wait while the file is being loaded...</p>
                <div class="loading-spinner"></div>
            </div>
        `;
        document.body.appendChild(overlay);
    }

    hideFileLoadingPopup() {
        const overlay = document.querySelector('.file-loading-overlay');
        if (overlay) {
            overlay.remove();
        }
    }

    showHighlightingDisabledPopup(fileSize) {
        // Create info modal for disabled highlighting
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
            max-width: 400px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        `;
        
        const fileSizeMB = (fileSize / (1024 * 1024)).toFixed(1);
        
        dialog.innerHTML = `
            <h3 style="margin: 0 0 1rem 0; color: #856404;">Large File Detected</h3>
            <p style="margin-bottom: 1rem;">This file is ${fileSizeMB} MB, which is quite large. Syntax highlighting has been disabled to improve performance and prevent the browser from becoming unresponsive.</p>
            <p style="margin-bottom: 1rem;">The file will be displayed as plain text, but all editing functionality remains available.</p>
            <button id="closeInfo" style="background: #28a745; color: white; border: none; padding: 0.5rem 1rem; border-radius: 0.25rem; cursor: pointer;">OK, Continue</button>
        `;
        
        modal.appendChild(dialog);
        document.body.appendChild(modal);
        
        // Close modal handlers
        const closeModal = () => document.body.removeChild(modal);
        document.getElementById('closeInfo').addEventListener('click', closeModal);
        modal.addEventListener('click', (e) => {
            if (e.target === modal) closeModal();
        });
        
        // Focus the OK button for better UX
        document.getElementById('closeInfo').focus();
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

    async showLocationDetailsForTab(tabId, corresp) {
        const detailsContent = document.getElementById(`apparatus-details-content-${tabId}`);
        
        // Find the synoptic map data for this corresp to get data-link
        const synopticMap = this.synopticMapData ? this.synopticMapData.synoptic_map : {};
        const synopticData = synopticMap[corresp];
        
        let message = ``;
        
        if (synopticData && synopticData.target) {
            // Use the target data as data-link for synoptic comparison
            const dataLink = synopticData.target.join(' ');
            
            try {
                const comparisonResponse = await this.apiRequest('/synoptic/compare', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        data_link: dataLink
                    })
                });
                
                if (comparisonResponse.success) {
                    // Create a mapping from synoptic prefix to comparison data
                    const prefixToData = {};
                    
                    if (comparisonResponse.comparison_data) {
                        // Use new format with explicit prefix mapping
                        comparisonResponse.comparison_data.forEach(item => {
                            prefixToData[item.prefix] = {
                                lineId: item.token,
                                text: item.text
                            };
                        });
                    } else if (comparisonResponse.comparison_texts) {
                        // Fallback to old format (for backward compatibility)
                        comparisonResponse.comparison_texts.forEach((text, index) => {
                            const lineId = synopticData.target[index] || `Witness ${index + 1}`;
                            const synopticPrefix = lineId.includes(':') ? lineId.split(':')[0] : lineId;
                            
                            prefixToData[synopticPrefix] = {
                                lineId: lineId,
                                text: text
                            };
                        });
                    }
                    
                    // Display in apparatus witness order, filtering to only included witnesses
                    if (this.witnessOrder && this.witnessOrder.length > 0 && this.witnessMapping) {
                        this.witnessOrder.forEach(witnessId => {
                            // Get synoptic prefix from witness mapping
                            const mappingInfo = this.witnessMapping[witnessId];
                            if (mappingInfo && mappingInfo.synoptic_prefix) {
                                const synopticPrefix = mappingInfo.synoptic_prefix;
                                if (prefixToData[synopticPrefix]) {
                                    const data = prefixToData[synopticPrefix];
                                    const siglum = mappingInfo.siglum || synopticPrefix;
                                    message += this.createSynLine(siglum, data);
                                }
                            }
                        });
                    } else {
                        // Fallback to original order if no witness order available
                        Object.entries(prefixToData).forEach(([synopticPrefix, data]) => {
                            const siglum = this.getSiglumForWitness(synopticPrefix);
                            message += this.createSynLine(siglum, data);
                        });
                    }
                } else {
                    message += '<strong>Synoptic Comparison:</strong> Error loading comparison data<br>';
                }
            } catch (error) {
                console.error('Error loading synoptic comparison:', error);
                message += '<strong>Synoptic Comparison:</strong> Error loading comparison data<br>';
            }
        } else {
            message += '<strong>Synoptic Comparison:</strong> No synoptic data available for this location<br>';
        }
        
        if (detailsContent) {
            detailsContent.innerHTML = message;
            
            // Trigger token highlighting after synoptic content is loaded
            const tab = this.tabs.get(tabId);
            if (tab) {
                this.highlightTokensForEntry(tabId, corresp, tab.activeSubentryIndex || 0);
            }
        }
    }

    async showLocationDetails(loc) {
        if (!this.activeTabId) return;
        await this.showLocationDetailsForTab(this.activeTabId, loc);
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