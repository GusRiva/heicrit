const API_BASE = 'http://127.0.0.1:5000/api';

class HeiCritApp {
    constructor() {
        this.currentFile = null;
        this.textarea = null;
        this.highlightCode = null;
        this.apparatusData = null;
        this.synopticMapData = null;
        this.synopticMapFile = null; // Absolute path to synoptic map XML file
        this.mainTextData = null; // Store main text data
        this.leithsInfo = null; // Store leiths-info with siglum
        this.witnessOrder = []; // Store witness order from apparatus listWit
        this.witnessMapping = {}; // Store witness-to-prefix mapping from apparatus
        this.projectFiles = new Map(); // Store all project files
        
        // Tab management
        this.tabs = new Map(); // Store tab data: id -> {type, title, content, data}
        this.activeTabId = null;
        this.nextTabId = 1;
        
        // Entry creation mode
        this.creationMode = false;
        this.currentReadingGroup = 'lemma';
        this.selectedTokens = {
            lemma: [],
            'reading-1': []
        };
        this.nextReadingGroupIndex = 2;
        // New-format only: holds 'hc:TranspositionVariant' for a reading
        // group put into transposition (ordered-selection) mode, absent/empty
        // otherwise (Addition/Omission/Substitution are auto-detected). In
        // transposition mode, the lemma is selected normally and each
        // reading group's tokens are numbered by click order per witness -
        // see updateTranspositionNumbering/buildTranspositionSavePayload.
        this.selectedReadingAna = {};

        // Project tracking for save functionality
        this.currentProjectDirectory = null;
        this.currentApparatusFile = null;
        
        // Store bound event handlers for proper removal
        this.tokenClickHandler = null;
        this.delegationHandler = null;
        
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

    // Colored square emoji matching .selected-lemma / .selected-reading-N in
    // styles.css, so dropdown options show at a glance which highlight color
    // a group corresponds to (native <option> elements can't hold styled
    // <span>s, so the color has to come from the glyph itself).
    getReadingGroupLabel(group) {
        if (group === 'lemma') return '🟩 Lemma';
        const match = group.match(/reading-(\d+)/);
        if (!match) return group;
        const number = parseInt(match[1], 10);
        const colorEmojis = ['🟧', '🟪', '🟦', '🟥', '🟫', '🟨'];
        const emoji = colorEmojis[(number - 1) % colorEmojis.length];
        return `${emoji} Reading ${number}`;
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
                                <div class="apparatus-details-header">
                                    <div class="apparatus-details-title">
                                        <h4>Location Details</h4>
                                        <div class="apparatus-toolbar">
                                            <button id="new-variant-btn-${tabId}" class="apparatus-btn">New Entry</button>
                                            <button id="edit-variant-btn-${tabId}" class="apparatus-btn">Edit Entry</button>
                                            <button id="delete-variant-btn-${tabId}" class="apparatus-btn" style="display: none;">Delete Entry</button>
                                            <select id="reading-group-select-${tabId}" class="reading-group-select" style="display: none;">
                                                <option value="lemma">${this.getReadingGroupLabel('lemma')}</option>
                                                <option value="reading-1">${this.getReadingGroupLabel('reading-1')}</option>
                                                <option value="new-group">+ New reading group</option>
                                            </select>
                                            <select id="reading-ana-select-${tabId}" class="reading-ana-select" style="display: none;">
                                                <option value="">Addition / Omission / Substitution (auto)</option>
                                                <option value="hc:TranspositionVariant">Transposition</option>
                                            </select>
                                        </div>
                                    </div>
                                </div>
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
                <div id="xml-editor-container-${tabId}" class="xml-editor-container" style="position: relative; width: 100%; height: 100%;">
                    <textarea id="editor-textarea-${tabId}" class="editor-textarea" placeholder="Open or create a file to start editing..." spellcheck="false" autocomplete="off" autocorrect="off" autocapitalize="off"></textarea>
                    <pre id="editor-highlight-${tabId}" class="editor-highlight"><code id="editor-code-${tabId}" class="language-xml"></code></pre>
                </div>
            `;
        } else if (tab.type === 'synoptic-editor') {
            panel.innerHTML = `
                <div class="synoptic-editor-container">
                    <div class="synoptic-editor-toolbar">
                        <button class="apparatus-btn" id="save-synoptic-btn-${tabId}">Save</button>
                        <button class="apparatus-btn apparatus-btn-secondary" id="add-row-btn-${tabId}">+ Add Row</button>
                        <span class="synoptic-editor-status" id="synoptic-editor-status-${tabId}"></span>
                    </div>
                    <div class="synoptic-table-wrapper" id="synoptic-table-wrapper-${tabId}"></div>
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
        } else if (tab.type === 'synoptic-editor') {
            if (tab.data) {
                this.renderSynopticTable(tab.id, tab.data);
            }
            this.setupSynopticEditorEvents(tab.id);
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
        
        // Setup entry creation events
        const newVariantBtn = document.getElementById(`new-variant-btn-${tabId}`);
        const editVariantBtn = document.getElementById(`edit-variant-btn-${tabId}`);
        const deleteVariantBtn = document.getElementById(`delete-variant-btn-${tabId}`);
        const readingGroupSelect = document.getElementById(`reading-group-select-${tabId}`);
        const readingAnaSelect = document.getElementById(`reading-ana-select-${tabId}`);

        if (newVariantBtn) {
            newVariantBtn.addEventListener('click', () => this.toggleCreationMode(tabId));
        }

        if (editVariantBtn) {
            editVariantBtn.addEventListener('click', () => this.toggleEditMode(tabId));
        }

        if (deleteVariantBtn) {
            deleteVariantBtn.addEventListener('click', () => this.deleteCurrentEntryOnServer(tabId));
        }

        if (readingGroupSelect) {
            readingGroupSelect.addEventListener('change', (e) => this.handleReadingGroupChange(tabId, e.target.value));
        }

        if (readingAnaSelect) {
            readingAnaSelect.addEventListener('change', (e) => this.handleAnaChange(tabId, this.currentReadingGroup, e.target.value));
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
            
            // Set initial activeSubentryIndex to first non-placeholder entry
            if (tab.entryKeys.length > 0) {
                const firstCorresp = tab.entryKeys[0];
                const firstEntries = tab.groupedEntries[firstCorresp];
                tab.activeSubentryIndex = this.findFirstNonPlaceholderEntry(firstEntries);
            } else {
                tab.activeSubentryIndex = -1;
            }

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
        
        // Set up token click event delegation for edit mode detection
        this.setupTokenEventDelegation();
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
            this.updateDeleteButtonVisibility(tabId);
            return;
        }

        // Get current entry data
        const currentCorresp = tab.entryKeys[tab.currentEntryIndex];
        const currentEntries = tab.groupedEntries[currentCorresp];
        const currentLoc = currentEntries.length > 0 && currentEntries[0].loc ? currentEntries[0].loc : '';

        // Generate HTML for current entry
        // Use max(0, activeSubentryIndex) to handle -1 case (no non-placeholder entries)
        const displayIndex = Math.max(0, tab.activeSubentryIndex || 0);
        const htmlContent = this.generateLocationHTML(currentLoc, currentEntries, displayIndex);
        
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
        
        // Set up drag-and-drop sorting for apparatus entries
        this.setupApparatusSorting(tabId);

        // Set up editable note areas (italics -> <mentioned> on save)
        this.setupNoteEditing(tabId);

        this.updateDeleteButtonVisibility(tabId);
    }

    updateDeleteButtonVisibility(tabId) {
        const tab = this.tabs.get(tabId);
        const deleteBtn = document.getElementById(`delete-variant-btn-${tabId}`);
        if (!deleteBtn) return;

        const isNewFormat = tab && tab.data && tab.data.apparatusFormat === 'new';
        if (!isNewFormat || this.creationMode || this.editMode) {
            deleteBtn.style.display = 'none';
            return;
        }

        // Transposition entries CAN be deleted (the backend just removes the
        // <app> by index regardless of its structure) - unlike editing, delete
        // doesn't need to reconstruct or validate the entry's content.
        // Explicit-<lem>-override entries stay excluded, same as edit.
        const entry = this.getCurrentActiveEntry(tabId);
        const isDeletable = entry && !entry.is_placeholder && !entry.lemma_is_explicit;

        deleteBtn.style.display = isDeletable ? '' : 'none';
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
            
            // Set to first non-placeholder entry, or -1 if all are placeholders
            const currentCorresp = tab.entryKeys[tab.currentEntryIndex];
            const currentEntries = tab.groupedEntries[currentCorresp];
            tab.activeSubentryIndex = this.findFirstNonPlaceholderEntry(currentEntries);
            
            this.updateApparatusDisplay(tabId);
        }
    }

    showNextEntry(tabId) {
        const tab = this.tabs.get(tabId);
        if (!tab) return;

        if (tab.currentEntryIndex < tab.entryKeys.length - 1) {
            tab.currentEntryIndex++;
            
            // Set to first non-placeholder entry, or -1 if all are placeholders
            const currentCorresp = tab.entryKeys[tab.currentEntryIndex];
            const currentEntries = tab.groupedEntries[currentCorresp];
            tab.activeSubentryIndex = this.findFirstNonPlaceholderEntry(currentEntries);
            
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
            
            // Set to first non-placeholder entry, or -1 if all are placeholders
            const currentCorresp = tab.entryKeys[targetIndex];
            const currentEntries = tab.groupedEntries[currentCorresp];
            tab.activeSubentryIndex = this.findFirstNonPlaceholderEntry(currentEntries);
            
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

    findFirstNonPlaceholderEntry(entries) {
        if (!entries || entries.length === 0) return -1;
        
        for (let i = 0; i < entries.length; i++) {
            if (!entries[i].is_placeholder) {
                return i;
            }
        }
        return -1; // All entries are placeholders
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

        // First, add gray background to all tokens that have apparatus entries
        this.addApparatusBackgroundToTokens(tabId, corresp);

        // Get the entry data
        const entries = tab.groupedEntries[corresp];
        if (!entries || subentryIndex >= entries.length) return;

        const entry = entries[subentryIndex];
        if (entry.is_placeholder) return;

        // Highlight lemma tokens in green
        if (entry.lemma && entry.lemma.attributes && entry.lemma.attributes.corresp) {
            this.highlightTokensFromCorresp(entry.lemma.attributes.corresp, 'lemma');
        }

        // Highlight reading tokens with different colors for each reading group
        if (entry.readings && entry.readings.length > 0) {
            entry.readings.forEach((reading, index) => {
                if (reading.attributes && reading.attributes.corresp) {
                    // Use different reading classes for each reading group
                    const readingType = `reading-${index + 1}`;
                    this.highlightTokensFromCorresp(reading.attributes.corresp, readingType);
                }
            });
        }
    }

    addApparatusBackgroundToTokens(tabId, corresp) {
        const tab = this.tabs.get(tabId);
        if (!tab) return;

        // Get all entries for this location
        const entries = tab.groupedEntries[corresp];
        if (!entries) return;

        // Collect all corresp values from all entries at this location
        const allCorrespValues = [];
        entries.forEach(entry => {
            if (entry.is_placeholder) return;
            
            // Add lemma corresp
            if (entry.lemma && entry.lemma.attributes && entry.lemma.attributes.corresp) {
                allCorrespValues.push(entry.lemma.attributes.corresp);
            }
            
            // Add reading corresp values
            if (entry.readings && entry.readings.length > 0) {
                entry.readings.forEach(reading => {
                    if (reading.attributes && reading.attributes.corresp) {
                        allCorrespValues.push(reading.attributes.corresp);
                    }
                });
            }
        });

        // Apply has-apparatus class to all these tokens
        allCorrespValues.forEach(correspValue => {
            this.addHasApparatusClassFromCorresp(correspValue);
        });
    }

    addHasApparatusClassFromCorresp(correspValue) {
        // Parse corresp attribute like "a:range(w_12_1, w_12_2)" or "ba:w_12_1 bb:w_12_1"
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
            if (part.includes(':')) {
                const colonIndex = part.indexOf(':');
                const prefix = part.substring(0, colonIndex);
                const tokenSpec = part.substring(colonIndex + 1);
                
                this.addHasApparatusClassForPrefix(prefix, tokenSpec);
            }
        });
    }

    parseTokenSpec(tokenSpec) {
        if (tokenSpec.startsWith('left(') && tokenSpec.endsWith(')'))
            return { type: 'left', id: tokenSpec.slice(5, -1) };
        if (tokenSpec.startsWith('right(') && tokenSpec.endsWith(')'))
            return { type: 'right', id: tokenSpec.slice(6, -1) };
        if (tokenSpec.startsWith('range(') && tokenSpec.endsWith(')')) {
            const [start, end] = tokenSpec.slice(6, -1).split(',').map(s => s.trim());
            return { type: 'range', start, end };
        }
        return { type: 'single', id: tokenSpec };
    }

    addHasApparatusClassForPrefix(prefix, tokenSpec) {
        const witElement = document.querySelector(`.syn-line-wit[data-line-id^="${prefix}:"]`);
        if (!witElement) return;
        const synLine = witElement.closest('.syn-line');
        if (!synLine) return;
        const synLineContent = synLine.querySelector('.syn-line-content');
        if (!synLineContent) return;

        const spec = this.parseTokenSpec(tokenSpec);
        if (spec.type === 'range') {
            this.addHasApparatusClassToTokenRange(synLineContent, spec.start, spec.end);
        } else if (spec.type === 'left') {
            const token = synLineContent.querySelector(`.syn-token-pre[data-token-id="${spec.id}"]`);
            if (token) token.classList.add('has-apparatus');
        } else if (spec.type === 'right') {
            const token = synLineContent.querySelector(`.syn-token-post[data-token-id="${spec.id}"]`);
            if (token) token.classList.add('has-apparatus');
        } else {
            this.addHasApparatusClassToSingleToken(synLineContent, spec.id);
        }
    }

    addHasApparatusClassToSingleToken(container, tokenId) {
        const token = container.querySelector(`.syn-token:not(.syn-token-pre):not(.syn-token-post)[data-token-id="${tokenId}"]`);
        if (token) {
            token.classList.add('has-apparatus');
        }
    }

    addHasApparatusClassToTokenRange(container, startTokenId, endTokenId) {
        const allTokens = container.querySelectorAll('.syn-token:not(.syn-token-pre):not(.syn-token-post)[data-token-id]');

        let inRange = false;
        let foundStart = false;

        for (const token of allTokens) {
            const tokenId = token.getAttribute('data-token-id');

            if (tokenId === startTokenId) {
                inRange = true;
                foundStart = true;
            }

            if (inRange) {
                token.classList.add('has-apparatus');
            }

            if (tokenId === endTokenId && foundStart) {
                break;
            }
        }
    }

    clearTokenHighlights(tabId) {
        // Remove navigation highlighting classes but keep .has-apparatus class
        const tabPanel = document.getElementById(`panel-${tabId}`);
        if (tabPanel) {
            // Remove lemma highlighting
            tabPanel.querySelectorAll('.syn-token.highlight-lemma').forEach(token => {
                token.classList.remove('highlight-lemma');
            });
            
            // Remove all reading highlighting classes (reading-1, reading-2, etc.)
            tabPanel.querySelectorAll('.syn-token[class*="highlight-reading"]').forEach(token => {
                // Remove all classes that start with 'highlight-reading'
                const classesToRemove = Array.from(token.classList).filter(cls => cls.startsWith('highlight-reading'));
                token.classList.remove(...classesToRemove);
            });
            
            // Keep .has-apparatus class - it provides useful visual context during editing
        }
    }

    highlightTokensFromCorresp(correspValue, type) {
        // Parse corresp attribute like "a:range(w_12_1, w_12_2)" or "ba:w_12_1 bb:w_12_1"
        
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
            
            if (part.includes(':')) {
                const colonIndex = part.indexOf(':');
                const prefix = part.substring(0, colonIndex);
                const tokenSpec = part.substring(colonIndex + 1);
                
                this.highlightTokensForPrefix(prefix, tokenSpec, type);
            }
        });
    }

    highlightTokensForPrefix(prefix, tokenSpec, type) {
        const witElement = document.querySelector(`.syn-line-wit[data-line-id^="${prefix}:"]`);
        if (!witElement) return;
        const synLine = witElement.closest('.syn-line');
        if (!synLine) return;
        const synLineContent = synLine.querySelector('.syn-line-content');
        if (!synLineContent) return;

        const spec = this.parseTokenSpec(tokenSpec);
        if (spec.type === 'range') {
            this.highlightTokenRange(synLineContent, spec.start, spec.end, type);
        } else if (spec.type === 'left') {
            const token = synLineContent.querySelector(`.syn-token-pre[data-token-id="${spec.id}"]`);
            if (token) token.classList.add(`highlight-${type}`);
        } else if (spec.type === 'right') {
            const token = synLineContent.querySelector(`.syn-token-post[data-token-id="${spec.id}"]`);
            if (token) token.classList.add(`highlight-${type}`);
        } else {
            this.highlightSingleToken(synLineContent, spec.id, type);
        }
    }

    highlightSingleToken(container, tokenId, type) {
        const token = container.querySelector(`.syn-token:not(.syn-token-pre):not(.syn-token-post)[data-token-id="${tokenId}"]`);
        if (token) {
            token.classList.add(`highlight-${type}`);
        }
    }

    highlightTokenRange(container, startTokenId, endTokenId, type) {
        const allTokens = container.querySelectorAll('.syn-token:not(.syn-token-pre):not(.syn-token-post)[data-token-id]');

        let inRange = false;
        let foundStart = false;

        for (const token of allTokens) {
            const tokenId = token.getAttribute('data-token-id');

            if (tokenId === startTokenId) {
                inRange = true;
                foundStart = true;
            }

            if (inRange) {
                token.classList.add(`highlight-${type}`);
            }

            if (tokenId === endTokenId && foundStart) {
                break;
            }
        }
    }

    bindEvents() {
        // Navbar dropdown menu events
        document.getElementById('openFile').addEventListener('click', () => this.openFile());
        document.getElementById('openProjectDirectory').addEventListener('click', () => this.openProjectDirectory());
        document.getElementById('saveProjectIcon').addEventListener('click', () => this.saveProject());
        document.getElementById('saveFile').addEventListener('click', () => this.saveFile());
        document.getElementById('saveAsFile').addEventListener('click', () => this.saveAsFile());
        document.getElementById('saveProject').addEventListener('click', () => this.saveProject());
        
        // Toolbar icon events
        document.getElementById('openProjectDirectoryIcon').addEventListener('click', () => this.openProjectDirectory());
        document.getElementById('editSynopticMapIcon').addEventListener('click', () => this.openSynopticEditor());
        
        // Add click handler for any element with data-container-id attribute
        document.addEventListener('click', (e) => {
            const target = e.target.closest('[data-container-id]');
            if (target) {
                const containerId = target.getAttribute('data-container-id');
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
            
            // Extract and store project directory path
            if (files.length > 0 && files[0].webkitRelativePath) {
                const firstFilePath = files[0].webkitRelativePath;
                // Extract the root directory name (first part of the path)
                this.currentProjectDirectory = firstFilePath.split('/')[0];
            }
            
            // Filter files to only process relevant folders: apparatus, synopses, texts
            const relevantFolders = ['apparatus', 'synopses', 'texts'];
            const filteredFiles = files.filter(file => {
                const relativePath = file.webkitRelativePath || file.name;
                const pathParts = relativePath.split('/');
                
                // Skip files in root directory or irrelevant folders
                if (pathParts.length < 2) return false;
                
                // Check if the first folder (after project root) is in our relevant folders
                const folderName = pathParts[1];
                return relevantFolders.includes(folderName);
            });
            
            // Read filtered files and store them
            const fileReadPromises = filteredFiles.map(file => {
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
            this.updateStatus(`Loaded ${this.projectFiles.size} files from relevant folders (apparatus, synopses, texts)`);
            
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

        // Stash discovered synoptic candidates so the synoptic-load fallback
        // step (processApparatusInSteps) can offer them if the apparatus's
        // declared synoptic map (corresp) fails to resolve.
        this.candidateSynopticFiles = synopticFiles;

        if (apparatusFiles.length === 0 && synopticFiles.length === 0) {
            this.updateStatus('No apparatus or synoptic map files found in project directory');
            this.showErrorPopup('No Files Found', 'No apparatus files found in apparatus/ directory or synoptic map files found in synopses/ directory.');
            return;
        }

        // Process apparatus file if found
        if (apparatusFiles.length === 1) {
            await this.processApparatusFileFromProject(apparatusFiles[0].content, apparatusFiles[0].path);
        } else if (apparatusFiles.length > 1) {
            // Hide the loading overlay while the user makes a choice
            this.hideLoadingPopup();

            const chosen = await new Promise(resolve => {
                this.showFilePickerPopup({
                    title: 'Multiple Apparatus Files Found',
                    description: 'This project contains more than one apparatus file. Choose which one to open.',
                    candidates: apparatusFiles.map(f => ({
                        path: f.path,
                        label: this.extractApparatusTitle(f.content) || f.path.split('/').pop(),
                        sublabel: f.path,
                        content: f.content
                    })),
                    onSelect: (candidate) => resolve(candidate),
                    onCancel: () => resolve(null)
                });
            });

            if (!chosen) {
                this.projectFiles.clear();
                this.currentProjectDirectory = null;
                this.updateStatus('Project open cancelled');
                return;
            }

            this.showLoadingPopup();
            await this.processApparatusFileFromProject(chosen.content, chosen.path);
        }

        // Small delay to show the final step
        setTimeout(() => {
            this.updateLoadingStep('step-display', 'completed');
            this.hideLoadingPopup();
        }, 500);
    }


    async processApparatusFileFromProject(content, filepath) {
        try {
            this.updateStatus('Processing apparatus file from project...');
            
            // Store the apparatus file path for save functionality
            this.currentApparatusFile = filepath;
            
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

            // Process in steps with real backend calls
            await this.processApparatusInSteps(content, filepath);

        } catch (error) {
            this.showErrorPopup('Backend Error', `Failed to communicate with backend: ${error.message}`);
        }
    }

    // Loads the synoptic map for the current apparatus, following the
    // apparatus's declared corresp first. If that can't be resolved, falls
    // back to the project's discovered synoptic candidates: auto-selects
    // when there's exactly one, prompts the user when there are several,
    // and otherwise proceeds with an empty synoptic map (visible via status).
    async resolveSynopticMap(projectFiles, filepath, leithsPrefix) {
        const synopticResponse = await this.apiRequest('/synoptic/load', {
            method: 'POST',
            body: JSON.stringify({
                project_files: projectFiles,
                apparatus_filepath: filepath,
                leiths_prefix: leithsPrefix
            })
        });

        if (!synopticResponse.success || synopticResponse.synoptic_loaded) {
            return synopticResponse;
        }

        const candidates = this.candidateSynopticFiles || [];

        if (candidates.length === 0) {
            this.updateStatus('Warning: No synoptic map file found or resolved — proceeding without synoptic data.');
            return synopticResponse;
        }

        let chosenPath = null;
        if (candidates.length === 1) {
            chosenPath = candidates[0].path;
        } else {
            this.hideLoadingPopup();
            const chosen = await new Promise(resolve => {
                this.showFilePickerPopup({
                    title: 'Choose Synoptic Map File',
                    description: 'The apparatus file does not declare a synoptic map that could be resolved. Choose which synoptic map to use.',
                    candidates: candidates.map(f => ({
                        path: f.path,
                        label: this.extractApparatusTitle(f.content) || f.path.split('/').pop(),
                        sublabel: f.path
                    })),
                    onSelect: (candidate) => resolve(candidate),
                    onCancel: () => resolve(null)
                });
            });
            this.showLoadingPopup();
            this.updateLoadingStep('step-witnesses', 'completed');
            this.updateLoadingStep('step-synoptic', 'active');
            if (!chosen) {
                this.updateStatus('Warning: No synoptic map selected — proceeding without synoptic data.');
                return synopticResponse;
            }
            chosenPath = chosen.path;
        }

        const retryResponse = await this.apiRequest('/synoptic/load', {
            method: 'POST',
            body: JSON.stringify({
                project_files: projectFiles,
                apparatus_filepath: filepath,
                leiths_prefix: leithsPrefix,
                synoptic_filepath: chosenPath
            })
        });

        if (retryResponse.success && !retryResponse.synoptic_loaded) {
            this.updateStatus('Warning: Could not load the selected synoptic map file — proceeding without synoptic data.');
        }

        return retryResponse;
    }

    async processApparatusInSteps(content, filepath) {
        try {
            const projectFiles = this.getProjectFileList();
            let combinedResponse = {};
            
            // Step 1: Parse apparatus file
            this.updateLoadingStep('step-apparatus', 'active');
            this.updateStatus('Parsing apparatus file...');
            
            const apparatusResponse = await this.apiRequest('/apparatus/parse', {
                method: 'POST',
                body: JSON.stringify({
                    apparatus_content: content,
                    apparatus_filepath: filepath,
                    project_files: projectFiles
                })
            });
            
            if (!apparatusResponse.success) {
                this.showErrorPopup('Processing Error', apparatusResponse.error || 'Failed to parse apparatus');
                return;
            }
            
            combinedResponse = { ...combinedResponse, ...apparatusResponse };
            
            // Step 2: Load witness mappings
            this.updateLoadingStep('step-apparatus', 'completed');
            this.updateLoadingStep('step-witnesses', 'active');
            this.updateStatus('Loading witness mappings...');
            
            const witnessResponse = await this.apiRequest('/witnesses/load', {
                method: 'POST',
                body: JSON.stringify({})
            });
            
            if (!witnessResponse.success) {
                this.showErrorPopup('Processing Error', witnessResponse.error || 'Failed to load witnesses');
                return;
            }
            
            combinedResponse = { ...combinedResponse, ...witnessResponse };
            
            // Step 3: Process synoptic map
            this.updateLoadingStep('step-witnesses', 'completed');
            this.updateLoadingStep('step-synoptic', 'active');
            this.updateStatus('Processing synoptic map...');
            
            const synopticResponse = await this.resolveSynopticMap(projectFiles, filepath, witnessResponse.leiths_prefix);

            if (!synopticResponse.success) {
                this.showErrorPopup('Processing Error', synopticResponse.error || 'Failed to process synoptic map');
                return;
            }
            
            combinedResponse = { ...combinedResponse, ...synopticResponse };
            
            // Step 4: Generate main text
            this.updateLoadingStep('step-synoptic', 'completed');
            this.updateLoadingStep('step-maintext', 'active');
            this.updateStatus('Generating main text...');
            
            const maintextResponse = await this.apiRequest('/maintext/generate', {
                method: 'POST',
                body: JSON.stringify({
                    leiths_path: witnessResponse.leiths_path,
                    apparatus_filepath: filepath,
                    project_files: projectFiles
                })
            });
            
            if (!maintextResponse.success) {
                this.showErrorPopup('Processing Error', maintextResponse.error || 'Failed to generate main text');
                return;
            }
            
            combinedResponse = { ...combinedResponse, ...maintextResponse };
            
            // Step 5: Finalize project
            this.updateLoadingStep('step-maintext', 'completed');
            this.updateLoadingStep('step-display', 'active');
            this.updateStatus('Building interface...');
            
            const finalResponse = await this.apiRequest('/project/finalize', {
                method: 'POST',
                body: JSON.stringify({})
            });
            
            if (!finalResponse.success) {
                this.showErrorPopup('Processing Error', finalResponse.error || 'Failed to finalize project');
                return;
            }
            
            // Combine all responses for the final result
            const fullResponse = { 
                success: true,
                ...combinedResponse, 
                ...finalResponse
            };
            
            this.handleApparatusProcessingResult(fullResponse, filepath);
            
        } catch (error) {
            this.showErrorPopup('Processing Error', `Failed to process apparatus: ${error.message}`);
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

        // Store the leithandschrift's synoptic prefix (e.g. "b"), used when building
        // corresp values for newly created apparatus entries - must not be hardcoded,
        // since the base witness's prefix varies per project.
        if (result.leiths_prefix) {
            this.leithsPrefix = result.leiths_prefix;
        }

        // Store the detected apparatus data model ('old' or 'new') - drives which
        // entry create/edit/delete code path (and UI) is used.
        if (result.format) {
            this.apparatusFormat = result.format;
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

        // Store synoptic map file path for the spreadsheet editor
        if (result.synoptic_file) {
            this.synopticMapFile = result.synoptic_file;
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
                filename: projectName,
                // Add project paths for save functionality
                projectDirectory: this.currentProjectDirectory,
                apparatusFile: this.currentApparatusFile,
                synopticMapFile: this.synopticMapFile,
                apparatusFormat: this.apparatusFormat || 'old'
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



    generateLocationHTML(loc, entries, activeSubentryIndex = 0) {
        const corresp = entries.length > 0 && entries[0].corresp ? entries[0].corresp : '';
        let html = `
        <div class="apparatus-display">
            <div class="classical-apparatus">
                <div class="classical-entry-group">`;

        // Show location as bold span
        html += `<span class="apparatus-loc-span" 
                    data-loc="${this.escapeHtml(loc)}" 
                    data-corresp="${this.escapeHtml(corresp)}">${this.escapeHtml(loc)}</span>`;
        
        // Check if there are any real (non-placeholder) entries in this group
        const hasRealEntries = entries.some(entry => !entry.is_placeholder);
        
        // Process each entry in this location group
        entries.forEach((entry, index) => {
            const isActive = index === activeSubentryIndex && !entry.is_placeholder;
            
            // Skip placeholder entries if there are real entries
            if (entry.is_placeholder && hasRealEntries) {
                return;
            }
            
            html += `<div class="classical-subentry${entry.is_placeholder ? ' placeholder-entry' : ''}${isActive ? ' active' : ''}" 
                         data-subentry-index="${index}" 
                         data-corresp="${this.escapeHtml(corresp)}"
                         draggable="true"
                         data-entry-id="${entry.id || index}">`;
            
            // Add drag handle for sortable entries (only for non-placeholder entries)
            if (!entry.is_placeholder) {
                html += '<span class="drag-handle" title="Drag to reorder">⋮⋮</span>';
            }
            
            // Handle placeholder entries (no apparatus data)
            if (entry.is_placeholder) {
                html += ' <span class="no-apparatus">(no apparatus)</span>';
            } else {
                // Lemma content
                if (entry.lemma && entry.lemma.text) {
                    const lemmaHtml = entry.lemma.html ?? this.escapeHtml(entry.lemma.text);
                    html += ` ${lemmaHtml}`;
                    html += ' ]';
                }

                // Readings with witnesses
                if (entry.readings && entry.readings.length > 0) {
                    const readingParts = [];

                    entry.readings.forEach(reading => {
                        const readingHtml = reading.html ?? this.escapeHtml(reading.text);
                        let readingPart = ` ${readingHtml}`;
                        
                        // Add witnesses in italics
                        const wit = reading.attributes?.wit || reading.wit; // Support both new and old format
                        if (wit) {
                            // Clean up witness list (remove # symbols and extra spaces)
                            const witnesses = wit.replace(/#/g, '').trim().split(/\s+/).join(' ');
                            if (witnesses) {
                                readingPart += ` <em class="apparatus-witnesses">${this.escapeHtml(witnesses)}</em>`;
                            }
                        }
                        
                        readingParts.push(readingPart);
                    });
                    
                    // Join readings with semicolons
                    html += readingParts.join(' ;');
                } else {
                    // When there is only lemma
                    html += "<i>om. alii</i>"
                }
            }
            
            html += '</div>';

            // Note area - a sibling of (not nested in) the draggable subentry,
            // so text selection for italicizing doesn't fight with HTML5 drag.
            if (!entry.is_placeholder && entry.note) {
                html += this.renderNoteArea(entry);
            }
        });

        html += `
                </div>
            </div>
        </div>`;

        return html;
    }

    renderNoteArea(entry) {
        // entry.id is 1-based (sequential position among <app> elements);
        // the backend indexes <app> elements 0-based, so convert here once.
        const entryIndex = (entry.id || 1) - 1;
        const note = entry.note;
        const readingIndexAttr = (note.reading_index === null || note.reading_index === undefined)
            ? '' : note.reading_index;

        return `<div class="apparatus-note"
                     contenteditable="true"
                     data-entry-index="${entryIndex}"
                     data-note-target="${this.escapeHtml(note.target)}"
                     data-note-reading-index="${readingIndexAttr}"
                     data-placeholder="+">${note.html || ''}</div><button type="button" class="apparatus-note-save-btn" title="Save note">&check;</button>`;
    }

    setupNoteEditing(tabId) {
        const content = document.getElementById(`apparatus-content-${tabId}`);
        if (!content) return;

        const noteEls = content.querySelectorAll('.apparatus-note');
        console.log(`[notes] setupNoteEditing(${tabId}): found ${noteEls.length} note area(s)`);

        noteEls.forEach(noteEl => {
            const saveBtn = noteEl.nextElementSibling;
            const hasSaveBtn = saveBtn && saveBtn.classList.contains('apparatus-note-save-btn');
            if (!hasSaveBtn) {
                console.warn('[notes] no save button found as nextElementSibling of', noteEl);
            }

            noteEl.addEventListener('keydown', (e) => {
                if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'i') {
                    e.preventDefault();
                    document.execCommand('italic');
                }
            });

            // Show the save button only while the note is focused (per the
            // requested UX), and save on blur too as a fallback.
            noteEl.addEventListener('focus', () => {
                if (hasSaveBtn) saveBtn.style.display = 'inline-block';
            });

            noteEl.addEventListener('blur', () => {
                if (hasSaveBtn) saveBtn.style.display = 'none';
                console.log('[notes] blur -> saveEntryNote', { tabId, entryIndex: noteEl.getAttribute('data-entry-index') });
                this.saveEntryNote(tabId, noteEl);
            });

            if (hasSaveBtn) {
                // mousedown (not click) fires BEFORE the note field blurs, and
                // preventDefault() stops the button from stealing focus - so
                // the note stays focused and its current content is what gets
                // saved, rather than racing the blur handler above.
                saveBtn.addEventListener('mousedown', (e) => {
                    e.preventDefault();
                    console.log('[notes] save button mousedown -> saveEntryNote', { tabId, entryIndex: noteEl.getAttribute('data-entry-index') });
                    this.saveEntryNote(tabId, noteEl, saveBtn);
                });
            }
        });
    }

    async saveEntryNote(tabId, noteEl, saveBtn) {
        const tab = this.tabs.get(tabId);
        if (!tab || !tab.data) {
            console.warn('[notes] saveEntryNote aborted: no tab/tab.data', { tabId, tab });
            this.updateStatus('Could not save note: no active project tab', 'error');
            return;
        }

        const entryIndex = parseInt(noteEl.getAttribute('data-entry-index'), 10);
        const target = noteEl.getAttribute('data-note-target');
        const readingIndexAttr = noteEl.getAttribute('data-note-reading-index');
        const readingIndex = readingIndexAttr === '' ? null : parseInt(readingIndexAttr, 10);
        const noteHtml = noteEl.innerHTML.trim();

        this.updateStatus('Saving note...');
        console.log('[notes] saveEntryNote request', {
            apparatus_file: tab.data.apparatusFile,
            project_directory: tab.data.projectDirectory,
            entry_index: entryIndex, target, reading_index: readingIndex, note_html: noteHtml
        });

        try {
            const response = await this.apiRequest('/apparatus/note/save', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    apparatus_file: tab.data.apparatusFile,
                    project_directory: tab.data.projectDirectory,
                    entry_index: entryIndex,
                    target: target,
                    reading_index: readingIndex,
                    note_html: noteHtml
                })
            });

            console.log('[notes] saveEntryNote response', response);

            if (!response.success) {
                console.error('Failed to save note:', response.error);
                this.updateStatus(`Failed to save note: ${response.error || 'unknown error'}`, 'error');
                this.showErrorPopup('Save Failed', response.error || 'Failed to save the note.');
                return;
            }

            // /apparatus/note/save only returns {success}, not a fresh
            // entries list (unlike create/update/delete) - update the
            // in-memory entry directly so the saved note is still there when
            // the user navigates away and back, without needing a full
            // server round-trip refresh.
            this.updateLocalNoteState(tab, entryIndex, target, readingIndex, noteHtml, noteEl.textContent.trim());

            this.updateStatus('Note saved');
            if (saveBtn) {
                saveBtn.classList.add('just-saved');
                setTimeout(() => saveBtn.classList.remove('just-saved'), 600);
            }
        } catch (error) {
            console.error('Error saving note:', error);
            this.updateStatus(`Error saving note: ${error.message}`, 'error');
            this.showErrorPopup('Save Failed', `Error saving note: ${error.message}`);
        }
    }

    updateLocalNoteState(tab, entryIndex, target, readingIndex, noteHtml, noteText) {
        // entry.id is 1-based; entryIndex (sent to the backend) is 0-based -
        // same conversion as renderNoteArea, inverted.
        const entry = (tab.apparatusEntries || []).find(e => (e.id - 1) === entryIndex);
        if (!entry || !entry.note) {
            console.warn('[notes] updateLocalNoteState: could not find entry to update', { entryIndex });
            return;
        }
        entry.note.html = noteHtml;
        entry.note.text = noteText;
        entry.note.target = target;
        entry.note.reading_index = readingIndex;
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
                    <div class="loading-step" id="step-apparatus">Parsing apparatus file</div>
                    <div class="loading-step" id="step-witnesses">Loading witness mappings</div>
                    <div class="loading-step" id="step-synoptic">Processing synoptic map</div>
                    <div class="loading-step" id="step-maintext">Generating main text</div>
                    <div class="loading-step" id="step-display">Building interface</div>
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

    // Extract a human-readable title from an apparatus/synoptic XML document,
    // for use as a picker label. Returns null if no title is present.
    extractApparatusTitle(xmlContent) {
        try {
            const parser = new DOMParser();
            const xmlDoc = parser.parseFromString(xmlContent, 'text/xml');
            if (xmlDoc.querySelector('parsererror')) {
                return null;
            }
            const titleEl = xmlDoc.querySelector('title[ana="hc:MainTitle"]') || xmlDoc.querySelector('title');
            const text = titleEl ? titleEl.textContent.trim() : '';
            return text || null;
        } catch (error) {
            return null;
        }
    }

    // Generic "choose one of several files" modal. candidates is an array of
    // { path, label, sublabel }. Exactly one of onSelect/onCancel is called.
    showFilePickerPopup({ title, description, candidates, onSelect, onCancel }) {
        this.hideFilePickerPopup();

        const overlay = document.createElement('div');
        overlay.className = 'picker-overlay';

        const popup = document.createElement('div');
        popup.className = 'picker-popup';

        const heading = document.createElement('h3');
        heading.textContent = title;
        popup.appendChild(heading);

        if (description) {
            const desc = document.createElement('p');
            desc.textContent = description;
            popup.appendChild(desc);
        }

        const list = document.createElement('div');
        list.className = 'picker-list';
        candidates.forEach(candidate => {
            const item = document.createElement('button');
            item.type = 'button';
            item.className = 'picker-item';

            const label = document.createElement('div');
            label.className = 'picker-item-label';
            label.textContent = candidate.label;
            item.appendChild(label);

            const sublabel = document.createElement('div');
            sublabel.className = 'picker-item-sublabel';
            sublabel.textContent = candidate.sublabel;
            item.appendChild(sublabel);

            item.addEventListener('click', () => {
                overlay.remove();
                if (onSelect) onSelect(candidate);
            });

            list.appendChild(item);
        });
        popup.appendChild(list);

        const cancelBtn = document.createElement('button');
        cancelBtn.type = 'button';
        cancelBtn.className = 'apparatus-btn apparatus-btn-secondary picker-cancel-btn';
        cancelBtn.textContent = 'Cancel';
        cancelBtn.addEventListener('click', () => {
            overlay.remove();
            if (onCancel) onCancel();
        });
        popup.appendChild(cancelBtn);

        overlay.appendChild(popup);

        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) {
                overlay.remove();
                if (onCancel) onCancel();
            }
        });

        document.body.appendChild(overlay);
    }

    hideFilePickerPopup() {
        const overlay = document.querySelector('.picker-overlay');
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

            // Re-apply clickable attribute to freshly rendered tokens if in creation/edit mode
            if (this.creationMode || this.editMode) {
                this.setupTokenClickHandlers(tabId);
            }

            // Trigger token highlighting after synoptic content is loaded
            const tab = this.tabs.get(tabId);
            if (tab && tab.activeSubentryIndex >= 0) {
                this.highlightTokensForEntry(tabId, corresp, tab.activeSubentryIndex);
            }
        }
    }

    async showLocationDetails(loc) {
        if (!this.activeTabId) return;
        await this.showLocationDetailsForTab(this.activeTabId, loc);
    }


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
        // containerId is like "l_5" (from xml:id) or "5" (from @n on a standalone gap)
        // corresp in entryKeys is like "a:l_5"
        const targetIndex = activeTab.entryKeys.findIndex(corresp => {
            const correspSuffix = corresp.includes(':') ? corresp.split(':')[1] : corresp;
            if (correspSuffix === containerId) return true;
            // Also match against the loc value (for standalone gaps where data-container-id is @n)
            const entries = activeTab.groupedEntries[corresp];
            if (entries && entries.length > 0 && String(entries[0].loc) === containerId) return true;
            return false;
        });
        
        if (targetIndex !== -1) {
            activeTab.currentEntryIndex = targetIndex;
            
            // Set to first non-placeholder entry, or -1 if all are placeholders
            const currentCorresp = activeTab.entryKeys[targetIndex];
            const currentEntries = activeTab.groupedEntries[currentCorresp];
            activeTab.activeSubentryIndex = this.findFirstNonPlaceholderEntry(currentEntries);
            
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

    // Synoptic map editor methods
    async openSynopticEditor() {
        if (!this.synopticMapFile) {
            alert('No synoptic map available. Please open a project first.');
            return;
        }
        try {
            const response = await this.apiRequest('/synoptic/table', {
                method: 'POST',
                body: JSON.stringify({ file_path: this.synopticMapFile })
            });
            if (response.witnesses && response.rows) {
                this.createTab('synoptic-editor', 'Synoptic Map', null, response);
            } else {
                alert('Could not load synoptic map data.');
            }
        } catch (err) {
            alert('Error loading synoptic map: ' + err.message);
        }
    }

    renderSynopticTable(tabId, data) {
        const wrapper = document.getElementById(`synoptic-table-wrapper-${tabId}`);
        if (!wrapper) return;

        const { witnesses, rows } = data;

        let html = '<table class="synoptic-table">';
        // Header
        html += '<thead><tr>';
        html += '<th title="Row ID">n</th>';
        for (const w of witnesses) {
            const label = w.siglum || w.prefix;
            html += `<th title="${w.prefix}">${label}</th>`;
        }
        html += '</tr></thead>';

        // Body
        html += '<tbody>';
        rows.forEach((row, rowIdx) => {
            html += `<tr data-row-index="${rowIdx}">`;
            html += `<td><input class="syn-cell syn-n-cell" data-row-index="${rowIdx}" data-col-index="0" value="${row.n || ''}"></td>`;
            witnesses.forEach((w, colIdx) => {
                const val = (row.cells && row.cells[w.prefix]) ? row.cells[w.prefix] : '';
                html += `<td><input class="syn-cell" data-prefix="${w.prefix}" data-row-index="${rowIdx}" data-col-index="${colIdx + 1}" value="${val}"></td>`;
            });
            html += '</tr>';
        });
        html += '</tbody>';
        html += '</table>';

        wrapper.innerHTML = html;
        // Store witnesses for later use (adding rows)
        wrapper.dataset.witnesses = JSON.stringify(witnesses);
    }

    setupSynopticEditorEvents(tabId) {
        const wrapper = document.getElementById(`synoptic-table-wrapper-${tabId}`);
        const saveBtn = document.getElementById(`save-synoptic-btn-${tabId}`);
        const addRowBtn = document.getElementById(`add-row-btn-${tabId}`);

        if (saveBtn) {
            saveBtn.addEventListener('click', () => this.saveSynopticTable(tabId));
        }
        if (addRowBtn) {
            addRowBtn.addEventListener('click', () => this.addSynopticRow(tabId));
        }

        if (!wrapper) return;

        wrapper.addEventListener('keydown', (e) => {
            const input = e.target;
            if (!input.classList.contains('syn-cell')) return;

            const rowIdx = parseInt(input.dataset.rowIndex, 10);
            const colIdx = parseInt(input.dataset.colIndex, 10);
            const table = wrapper.querySelector('.synoptic-table');
            const rows = table ? Array.from(table.querySelectorAll('tbody tr')) : [];
            const totalCols = rows[0] ? rows[0].querySelectorAll('.syn-cell').length : 0;

            const getCell = (r, c) => {
                if (r < 0 || r >= rows.length) return null;
                const cells = rows[r].querySelectorAll('.syn-cell');
                if (c < 0 || c >= cells.length) return null;
                return cells[c];
            };

            if (e.key === 'Tab' && !e.shiftKey) {
                e.preventDefault();
                const next = getCell(rowIdx, colIdx + 1) || getCell(rowIdx + 1, 0);
                if (next) next.focus();
                else this.addSynopticRow(tabId);
            } else if (e.key === 'Tab' && e.shiftKey) {
                e.preventDefault();
                const prev = getCell(rowIdx, colIdx - 1) || getCell(rowIdx - 1, totalCols - 1);
                if (prev) prev.focus();
            } else if (e.key === 'Enter' || e.key === 'ArrowDown') {
                e.preventDefault();
                const below = getCell(rowIdx + 1, colIdx);
                if (below) below.focus();
            } else if (e.key === 'ArrowUp') {
                e.preventDefault();
                const above = getCell(rowIdx - 1, colIdx);
                if (above) above.focus();
            } else if (e.key === 'd' && e.ctrlKey) {
                e.preventDefault();
                const above = getCell(rowIdx - 1, colIdx);
                if (above) input.value = above.value;
            } else if (e.key === 's' && e.ctrlKey) {
                e.preventDefault();
                this.saveSynopticTable(tabId);
            } else if (e.key === 'Home') {
                e.preventDefault();
                const first = getCell(rowIdx, 0);
                if (first) first.focus();
            } else if (e.key === 'End') {
                e.preventDefault();
                const last = getCell(rowIdx, totalCols - 1);
                if (last) last.focus();
            }
        });
    }

    async saveSynopticTable(tabId) {
        const tab = this.tabs.get(tabId);
        const statusEl = document.getElementById(`synoptic-editor-status-${tabId}`);
        const wrapper = document.getElementById(`synoptic-table-wrapper-${tabId}`);
        if (!wrapper) return;

        const table = wrapper.querySelector('.synoptic-table');
        if (!table) return;

        const rows = [];
        table.querySelectorAll('tbody tr').forEach(tr => {
            const nInput = tr.querySelector('.syn-n-cell');
            const n = nInput ? nInput.value.trim() : '';
            if (!n) return;
            const cells = {};
            tr.querySelectorAll('.syn-cell[data-prefix]').forEach(input => {
                const v = input.value.trim();
                if (v) cells[input.dataset.prefix] = v;
            });
            rows.push({ n, cells });
        });

        const filePath = tab.data && tab.data.file_path;
        if (!filePath) {
            if (statusEl) statusEl.textContent = 'Error: no file path.';
            return;
        }

        if (statusEl) statusEl.textContent = 'Saving…';
        try {
            const result = await this.apiRequest('/synoptic/save-table', {
                method: 'POST',
                body: JSON.stringify({ file_path: filePath, rows })
            });
            if (statusEl) statusEl.textContent = result.message || 'Saved.';
            if (!result.disk_written && result.xml_content) {
                this.downloadFile(result.xml_content, result.filename || 'synoptic_map.xml');
            }
        } catch (err) {
            if (statusEl) statusEl.textContent = 'Error: ' + err.message;
        }
    }

    addSynopticRow(tabId) {
        const wrapper = document.getElementById(`synoptic-table-wrapper-${tabId}`);
        if (!wrapper) return;
        const table = wrapper.querySelector('.synoptic-table');
        if (!table) return;
        const tbody = table.querySelector('tbody');
        if (!tbody) return;

        const witnesses = JSON.parse(wrapper.dataset.witnesses || '[]');
        const existingRows = tbody.querySelectorAll('tr');
        const rowIdx = existingRows.length;

        const tr = document.createElement('tr');
        tr.dataset.rowIndex = rowIdx;

        // Update data-row-index on all cells in new row as we build
        const nTd = document.createElement('td');
        const nInput = document.createElement('input');
        nInput.className = 'syn-cell syn-n-cell';
        nInput.dataset.rowIndex = rowIdx;
        nInput.dataset.colIndex = 0;
        nInput.value = '';
        nTd.appendChild(nInput);
        tr.appendChild(nTd);

        witnesses.forEach((w, colIdx) => {
            const td = document.createElement('td');
            const input = document.createElement('input');
            input.className = 'syn-cell';
            input.dataset.prefix = w.prefix;
            input.dataset.rowIndex = rowIdx;
            input.dataset.colIndex = colIdx + 1;
            input.value = '';
            td.appendChild(input);
            tr.appendChild(td);
        });

        tbody.appendChild(tr);
        nInput.focus();
    }

    // Entry creation mode methods
    toggleCreationMode(tabId) {
        // Handle button click for both creation and edit modes
        if (this.editMode) {
            // Currently in edit mode - finish editing
            this.exitEditMode(tabId);
        } else if (this.creationMode) {
            // Currently in creation mode - exit creation mode
            this.exitCreationMode(tabId);
        } else {
            // Not in any mode - enter creation mode
            this.creationMode = true;
            const newVariantBtn = document.getElementById(`new-variant-btn-${tabId}`);
            const readingGroupSelect = document.getElementById(`reading-group-select-${tabId}`);
            
            // Enter creation mode
            newVariantBtn.textContent = 'Finish';
            newVariantBtn.classList.add('active');
            readingGroupSelect.style.display = 'inline-block';
            
            // Hide the Edit Entry button during creation mode
            const editVariantBtn = document.getElementById(`edit-variant-btn-${tabId}`);
            if (editVariantBtn) {
                editVariantBtn.style.display = 'none';
            }
            
            // Reset dropdown to initial state
            this.resetReadingGroupDropdown(tabId);
            
            // Clear navigation highlights when entering creation mode
            this.clearTokenHighlights(tabId);
            
            // Reset selected tokens
            this.selectedTokens = {
                lemma: [],
                'reading-1': []
            };
            this.currentReadingGroup = 'lemma';
            this.nextReadingGroupIndex = 2;
            this.selectedReadingAna = {};
            this.updateAnaSelectForGroup(tabId, 'lemma');

            // Set up token click handlers and event delegation
            this.setupTokenClickHandlers(tabId);
            this.setupTokenEventDelegation();
            
            // Set up keyboard shortcuts for reading group switching
            this.setupKeyboardShortcuts(tabId);
        }
    }
    
    toggleEditMode(tabId) {
        // Handle button click for edit mode
        if (this.editMode) {
            // Currently in edit mode - finish editing
            this.exitEditMode(tabId);
        } else if (this.creationMode) {
            // Currently in creation mode - exit creation mode first, then enter edit mode
            this.exitCreationMode(tabId);
            // Get the currently active entry and enter edit mode
            const tab = this.tabs.get(tabId);
            if (tab && tab.entryKeys && tab.currentEntryIndex >= 0) {
                const currentCorresp = tab.entryKeys[tab.currentEntryIndex];
                const currentEntries = tab.groupedEntries[currentCorresp];
                if (currentEntries && tab.activeSubentryIndex >= 0 && tab.activeSubentryIndex < currentEntries.length) {
                    const currentEntry = currentEntries[tab.activeSubentryIndex];
                    if (!currentEntry.is_placeholder) {
                        this.enterEditMode(tabId, currentEntry);
                    }
                }
            }
        } else {
            // Not in any mode - enter edit mode for currently active entry
            const tab = this.tabs.get(tabId);
            if (tab && tab.entryKeys && tab.currentEntryIndex >= 0) {
                const currentCorresp = tab.entryKeys[tab.currentEntryIndex];
                const currentEntries = tab.groupedEntries[currentCorresp];
                if (currentEntries && tab.activeSubentryIndex >= 0 && tab.activeSubentryIndex < currentEntries.length) {
                    const currentEntry = currentEntries[tab.activeSubentryIndex];
                    if (!currentEntry.is_placeholder) {
                        this.enterEditMode(tabId, currentEntry);
                    }
                }
            }
        }
    }
    
    exitCreationMode(tabId) {
        // New-format only: persist the new entry before tearing down creation
        // mode. On validation/server failure, stay in creation mode (don't run
        // the cleanup below) so the user can fix the selection and retry.
        const tab = this.tabs.get(tabId);
        if (tab && tab.data && tab.data.apparatusFormat === 'new') {
            const hasSelection = Object.values(this.selectedTokens).some(tokens => tokens && tokens.length > 0);
            if (hasSelection) {
                this.saveNewEntryToServer(tabId).then(success => {
                    if (success) {
                        this._finishExitCreationMode(tabId);
                    }
                });
                return;
            }
        }
        this._finishExitCreationMode(tabId);
    }

    _finishExitCreationMode(tabId) {
        this.creationMode = false;
        const newVariantBtn = document.getElementById(`new-variant-btn-${tabId}`);
        const editVariantBtn = document.getElementById(`edit-variant-btn-${tabId}`);
        const readingGroupSelect = document.getElementById(`reading-group-select-${tabId}`);
        
        newVariantBtn.textContent = 'New Entry';
        newVariantBtn.classList.remove('active');
        readingGroupSelect.style.display = 'none';
        const readingAnaSelect = document.getElementById(`reading-ana-select-${tabId}`);
        if (readingAnaSelect) readingAnaSelect.style.display = 'none';

        // Show the Edit Entry button again
        if (editVariantBtn) {
            editVariantBtn.style.display = '';
        }
        
        // Clear all selected tokens
        this.clearSelectedTokens(tabId);
        
        // Clear currently editing entry reference
        const tab = this.tabs.get(tabId);
        if (tab) {
            tab.currentlyEditingEntry = null;
        }
        
        // Remove token click handlers for creation mode
        this.removeTokenClickHandlers(tabId);
        
        // Remove keyboard shortcuts
        this.removeKeyboardShortcuts();
        
        // Restore token event delegation for navigation (non-creation mode)
        this.setupTokenEventDelegation();
        
        // Update the apparatus display now that we're exiting creation mode
        this.updateApparatusDisplay(tabId);

        // Only highlight if there's a non-placeholder active subentry
        const activeSubentryIndex = tab.activeSubentryIndex;
        if (activeSubentryIndex >= 0 && tab.apparatusEntries[activeSubentryIndex] && !tab.apparatusEntries[activeSubentryIndex].isPlaceholder) {
            // Highlight the gap element for the current location being viewed
            const currentLoc = this.getCurrentLocation(tab);
            const currentLocId = `l_${currentLoc}`;
            
            // Look for the element within the specific tab context
            const tabPanel = document.getElementById(`panel-${tabId}`);
            if (tabPanel) {
                const targetElement = tabPanel.querySelector(`.tei-gap-synoptic[data-container-id="${currentLocId}"]`);
                if (targetElement) {
                    targetElement.classList.add('has-content');
                }
            }
        }
        
    }
    
    setupTokenClickHandlers(tabId) {
        const tabPanel = document.getElementById(`panel-${tabId}`);
        if (!tabPanel) {
            return;
        }
        
        // Simply set cursor pointer - we'll use event delegation instead
        const tokens = tabPanel.querySelectorAll('.syn-token');
        
        tokens.forEach(token => {
            token.style.cursor = 'pointer';
            // Add a data attribute to mark tokens as clickable in creation mode
            token.setAttribute('data-creation-clickable', 'true');
        });
        
    }
    
    setupTokenEventDelegation() {
        // Remove existing delegation if any
        if (this.delegationHandler) {
            document.removeEventListener('click', this.delegationHandler);
        }
        
        // Create new delegation handler
        this.delegationHandler = (event) => {
            // Check if the clicked element is a token
            if (event.target.classList.contains('syn-token')) {
                // Handle creation mode (requires data-creation-clickable attribute)
                if (this.creationMode && event.target.hasAttribute('data-creation-clickable')) {
                    this.handleTokenClick(this.activeTabId, event);
                }
                // Handle edit mode detection (any token click when not in creation/edit mode)
                else if (!this.creationMode && !this.editMode) {
                    this.handleTokenClick(this.activeTabId, event);
                }
                // Handle edit mode (requires data-creation-clickable attribute)
                else if (this.editMode && event.target.hasAttribute('data-creation-clickable')) {
                    this.handleTokenClick(this.activeTabId, event);
                }
            }
        };
        
        // Add the delegation handler
        document.addEventListener('click', this.delegationHandler);
    }
    
    setupApparatusSorting(tabId) {
        const apparatusContent = document.getElementById(`apparatus-content-${tabId}`);
        if (!apparatusContent) return;
        
        const sortableEntries = apparatusContent.querySelectorAll('.classical-subentry[draggable="true"]');
        
        sortableEntries.forEach(entry => {
            // Remove existing listeners to avoid duplicates
            entry.removeEventListener('dragstart', this.handleDragStart);
            entry.removeEventListener('dragend', this.handleDragEnd);
            entry.removeEventListener('dragover', this.handleDragOver);
            entry.removeEventListener('drop', this.handleDrop);
            
            // Add drag event listeners
            entry.addEventListener('dragstart', this.handleDragStart.bind(this));
            entry.addEventListener('dragend', this.handleDragEnd.bind(this));
            entry.addEventListener('dragover', this.handleDragOver.bind(this));
            entry.addEventListener('drop', this.handleDrop.bind(this, tabId));
        });
    }
    
    handleDragStart(e) {
        e.target.classList.add('dragging');
        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('text/html', e.target.outerHTML);
        e.dataTransfer.setData('text/plain', e.target.dataset.subentryIndex);
    }
    
    handleDragEnd(e) {
        e.target.classList.remove('dragging');
        
        // Remove drag-over class from all entries
        document.querySelectorAll('.classical-subentry').forEach(entry => {
            entry.classList.remove('drag-over');
        });
    }
    
    handleDragOver(e) {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
        
        // Add visual feedback
        if (e.target.classList.contains('classical-subentry')) {
            e.target.classList.add('drag-over');
        }
    }
    
    handleDrop(tabId, e) {
        e.preventDefault();
        e.target.classList.remove('drag-over');
        
        if (!e.target.classList.contains('classical-subentry')) return;
        
        const draggedIndex = parseInt(e.dataTransfer.getData('text/plain'));
        const targetIndex = parseInt(e.target.dataset.subentryIndex);
        const corresp = e.target.dataset.corresp;
        
        if (draggedIndex === targetIndex) return;
        
        // Update the data structure
        this.reorderApparatusEntries(tabId, corresp, draggedIndex, targetIndex);
        
        // Refresh the display
        this.updateApparatusDisplay(tabId);
    }
    
    reorderApparatusEntries(tabId, corresp, fromIndex, toIndex) {
        const tab = this.tabs.get(tabId);
        if (!tab || !tab.groupedEntries || !tab.groupedEntries[corresp]) return;
        
        const entries = tab.groupedEntries[corresp];
        
        // Move the entry from fromIndex to toIndex
        const [movedEntry] = entries.splice(fromIndex, 1);
        entries.splice(toIndex, 0, movedEntry);
        
        // Update the activeSubentryIndex if needed
        if (tab.activeSubentryIndex === fromIndex) {
            tab.activeSubentryIndex = toIndex;
        } else if (tab.activeSubentryIndex > fromIndex && tab.activeSubentryIndex <= toIndex) {
            tab.activeSubentryIndex--;
        } else if (tab.activeSubentryIndex < fromIndex && tab.activeSubentryIndex >= toIndex) {
            tab.activeSubentryIndex++;
        }
    
    }
    
    setupKeyboardShortcuts(tabId) {
        // Create keyboard shortcut handler
        this.keyboardHandler = (event) => {
            // Only handle keyboard shortcuts during creation mode or edit mode
            if (!this.creationMode && !this.editMode) return;
            
            // Only handle number keys 0-9
            if (event.key >= '0' && event.key <= '9') {
                event.preventDefault();
                event.stopPropagation();
                
                const keyNumber = parseInt(event.key);
                this.switchToReadingGroupByNumber(tabId, keyNumber);
            }
        };
        
        // Add keyboard event listener
        document.addEventListener('keydown', this.keyboardHandler);
    }
    
    removeKeyboardShortcuts() {
        if (this.keyboardHandler) {
            document.removeEventListener('keydown', this.keyboardHandler);
            this.keyboardHandler = null;
        }
    }
    
    switchToReadingGroupByNumber(tabId, number) {
        let targetGroup;
        
        if (number === 0) {
            targetGroup = 'lemma';
        } else {
            targetGroup = `reading-${number}`;
        }
        
        // Get available reading groups (groups that have tokens or are the next available)
        const availableGroups = this.getAvailableReadingGroups();
        
        // Check if this is a valid group to switch to
        if (targetGroup === 'lemma' || availableGroups.includes(targetGroup)) {
            this.currentReadingGroup = targetGroup;
            
            // Update the dropdown to reflect the change
            const readingGroupSelect = document.getElementById(`reading-group-select-${tabId}`);
            if (readingGroupSelect) {
                // If this is a new group that doesn't exist in dropdown yet, create it
                if (targetGroup !== 'lemma' && !readingGroupSelect.querySelector(`option[value="${targetGroup}"]`)) {
                    this.createNewReadingGroupOption(tabId, targetGroup);
                }
                
                readingGroupSelect.value = targetGroup;
            }
            this.updateAnaSelectForGroup(tabId, targetGroup);
        }
    }
    
    getAvailableReadingGroups() {
        const availableGroups = [];
        
        // Add all groups that currently have selected tokens
        Object.keys(this.selectedTokens).forEach(group => {
            if (group !== 'lemma' && this.selectedTokens[group] && this.selectedTokens[group].length > 0) {
                availableGroups.push(group);
            }
        });
        
        // Add the next available reading group (one number higher than the highest existing)
        let maxReadingIndex = 0;
        availableGroups.forEach(group => {
            const match = group.match(/reading-(\d+)/);
            if (match) {
                maxReadingIndex = Math.max(maxReadingIndex, parseInt(match[1]));
            }
        });
        
        // Always allow switching to reading-1, or the next number after the highest existing
        const nextGroup = `reading-${Math.max(1, maxReadingIndex + 1)}`;
        if (!availableGroups.includes(nextGroup)) {
            availableGroups.push(nextGroup);
        }
        
        // Also always allow reading-1 if it doesn't exist yet
        if (!availableGroups.includes('reading-1')) {
            availableGroups.push('reading-1');
        }
        
        return availableGroups;
    }
    
    createNewReadingGroupOption(tabId, groupName) {
        const select = document.getElementById(`reading-group-select-${tabId}`);
        if (!select) return;
        
        const match = groupName.match(/reading-(\d+)/);
        if (!match) return;
        
        const readingNumber = parseInt(match[1]);
        
        // Initialize selectedTokens for this new group
        if (!this.selectedTokens[groupName]) {
            this.selectedTokens[groupName] = [];
        }
        
        // Create new option
        const newOption = document.createElement('option');
        newOption.value = groupName;
        newOption.textContent = this.getReadingGroupLabel(groupName);
        
        // Insert in the correct position (before the "new group" option)
        const newGroupOption = select.querySelector('option[value="new-group"]');
        if (newGroupOption) {
            select.insertBefore(newOption, newGroupOption);
        } else {
            select.appendChild(newOption);
        }
        
        // Update the next reading group index if needed
        if (readingNumber >= this.nextReadingGroupIndex) {
            this.nextReadingGroupIndex = readingNumber + 1;
        }
    }
    
    removeTokenClickHandlers(tabId) {
        const tabPanel = document.getElementById(`panel-${tabId}`);
        if (!tabPanel) return;
        
        const tokens = tabPanel.querySelectorAll('.syn-token');
        tokens.forEach(token => {
            token.style.cursor = '';
            token.removeAttribute('data-creation-clickable');
        });
    }
    
    handleTokenClick(tabId, event) {
        if (!this.creationMode && !this.editMode) {
            // Check if this token is part of an existing apparatus entry
            // this.checkTokenForEdit(tabId, event);
            return;
        }
        
        event.stopPropagation();
        const token = event.target;
        const tokenId = token.getAttribute('data-token-id');
        
        if (!tokenId) {
            return;
        }
        
        // Determine which line this token belongs to
        const synLine = token.closest('.syn-line');
        const isMainText = synLine && synLine.classList.contains('main-text');

        // Get witness information to distinguish tokens with same ID from different witnesses
        const witnessInfo = this.getWitnessInfoFromLine(synLine);
        const isPreSpace = token.classList.contains('syn-token-pre');
        const isPostSpace = token.classList.contains('syn-token-post');

        // If clicking on main text (first line), force lemma selection
        const readingGroup = isMainText ? 'lemma' : this.currentReadingGroup;
        const witnessId = witnessInfo ? witnessInfo.witnessId : null;

        // Find which group (if any) currently contains this specific token
        // Match on tokenId, witnessId, AND pre/post space type (pre-space and word share the same tokenId)
        let currentGroup = null;
        for (const group of Object.keys(this.selectedTokens)) {
            if (this.selectedTokens[group] && this.selectedTokens[group].some(t =>
                t.tokenId === tokenId &&
                t.witnessInfo && t.witnessInfo.witnessId === witnessId &&
                !!t.isPreSpace === isPreSpace &&
                !!t.isPostSpace === isPostSpace)) {
                currentGroup = group;
                break;
            }
        }

        const sameToken = t =>
            t.tokenId === tokenId &&
            t.witnessInfo && t.witnessInfo.witnessId === witnessId &&
            !!t.isPreSpace === isPreSpace &&
            !!t.isPostSpace === isPostSpace;

        if (currentGroup === readingGroup) {
            // Token is already in target group - remove it (toggle off)
            this.selectedTokens[readingGroup] = this.selectedTokens[readingGroup].filter(t => !sameToken(t));
            token.classList.remove(`selected-${readingGroup}`);
        } else {
            // Remove token from current group (if any)
            if (currentGroup && this.selectedTokens[currentGroup]) {
                this.selectedTokens[currentGroup] = this.selectedTokens[currentGroup].filter(t => !sameToken(t));
                token.classList.remove(`selected-${currentGroup}`);
            }

            // Add token to target group
            if (!this.selectedTokens[readingGroup]) {
                this.selectedTokens[readingGroup] = [];
            }

            this.selectedTokens[readingGroup].push({
                tokenId: tokenId,
                text: token.textContent.trim(),
                witnessInfo: witnessInfo,
                isPreSpace: isPreSpace,
                isPostSpace: isPostSpace
            });

            token.classList.add(`selected-${readingGroup}`);
        }
        


        
        // Save entry immediately after any token change (only in creation mode).
        // Old format only: this builds a client-only "ghost" entry keyed by an
        // old-format corresp string (leithsPrefix:l_N) and points
        // tab.currentEntryIndex at it for live preview. New-format corresp
        // keys look different (they include the poem-number segment, e.g.
        // "b:l_71_9" not "b:l_9"), so doing this for new-format projects left
        // tab.currentEntryIndex pointing at a key that doesn't exist in the
        // real server response once the entry is actually saved on Finish -
        // refreshApparatusEntriesInTab then failed to find it and fell back
        // to index 0, jumping the view back to the first entry. New-format
        // entries are only persisted once, at Finish, via saveNewEntryToServer;
        // the selection highlighting above already provides live feedback
        // without needing this bookkeeping.
        const tab = this.tabs.get(tabId);
        const isNewFormat = tab && tab.data && tab.data.apparatusFormat === 'new';
        if (this.creationMode && !isNewFormat) {
            this.saveNewEntry(tabId);
        }

        // Refresh the transposition order-number badges (lemma tokens numbered
        // by document position, each transposition reading group's tokens
        // numbered by click order per witness) whenever the lemma or a
        // transposition-flagged reading group changes.
        if (isNewFormat && Object.values(this.selectedReadingAna).includes('hc:TranspositionVariant')) {
            this.updateTranspositionNumbering(tabId);
        }

        // Check if event handlers are still attached
        const tokens = document.querySelectorAll('.syn-token');
        let tokensWithHandlers = 0;
        tokens.forEach(token => {
            if (token.style.cursor === 'pointer') {
                tokensWithHandlers++;
            }
        });
    }

    findWordTokenElement(tokenId, witnessId) {
        // Word tokens only (never a .syn-token-pre/-post gap marker) - gap
        // positions aren't meaningful for transposition pairing.
        const tokenElements = document.querySelectorAll(`[data-token-id="${tokenId}"]`);
        for (const tokenElement of tokenElements) {
            if (tokenElement.classList.contains('syn-token-pre') || tokenElement.classList.contains('syn-token-post')) {
                continue;
            }
            const synLine = tokenElement.closest('.syn-line');
            const witnessInfo = this.getWitnessInfoFromLine(synLine);
            if (witnessInfo && witnessInfo.witnessId === witnessId) {
                return tokenElement;
            }
        }
        return null;
    }

    setTranspositionNumber(tokenData, index) {
        const el = this.findWordTokenElement(tokenData.tokenId, tokenData.witnessInfo.witnessId);
        if (!el) return;
        el.classList.add('transposition-numbered');
        el.setAttribute('data-transposition-index', index);
    }

    updateTranspositionNumbering(tabId) {
        // Lemma tokens are selected normally (no special click handling) and
        // numbered by their DOCUMENT position (order-independent - the lemma
        // selection doesn't encode correspondence order on its own). Each
        // transposition-flagged reading group's tokens are numbered by CLICK
        // order instead, separately per witness, so witness token #N is
        // understood to correspond to lemma token #N (see
        // buildTranspositionSavePayload, which pairs them by that index).
        const tabPanel = document.getElementById(`panel-${tabId}`);
        if (!tabPanel) return;

        tabPanel.querySelectorAll('.transposition-numbered').forEach(el => {
            el.classList.remove('transposition-numbered');
            el.removeAttribute('data-transposition-index');
        });

        const transpositionGroups = Object.keys(this.selectedReadingAna).filter(
            group => this.selectedReadingAna[group] === 'hc:TranspositionVariant'
        );
        if (transpositionGroups.length === 0) return; // nothing in transposition mode - leave everything cleared

        // Number the lemma as soon as any group is in transposition mode,
        // even before the first reading token is clicked - it's already
        // selected via the normal lemma selection by this point.
        const lemmaTokens = this.selectedTokens.lemma || [];
        const sortedLemma = [...lemmaTokens].sort((a, b) => this.tokenSortKey(a.tokenId) - this.tokenSortKey(b.tokenId));
        sortedLemma.forEach((tokenData, index) => {
            this.setTranspositionNumber(tokenData, index + 1);
        });

        transpositionGroups.forEach(group => {
            const tokens = this.selectedTokens[group] || [];
            const countByWitness = {};
            tokens.forEach(tokenData => {
                const witId = tokenData.witnessInfo.witnessId;
                countByWitness[witId] = (countByWitness[witId] || 0) + 1;
                this.setTranspositionNumber(tokenData, countByWitness[witId]);
            });
        });
    }

    // checkTokenForEdit(tabId, event) {
    //     console.log('DEBUG: checkTokenForEdit called');
    //     event.stopPropagation();
    //     const token = event.target;
    //     const tokenId = token.getAttribute('data-token-id');
        
    //     console.log('DEBUG: Clicked token:', token, 'tokenId:', tokenId);
        
    //     if (!tokenId) {
    //         console.log('DEBUG: No tokenId found');
    //         return;
    //     }
        
    //     // Get witness information for this token
    //     const synLine = token.closest('.syn-line');
    //     const witnessInfo = this.getWitnessInfoFromLine(synLine);
    //     if (!witnessInfo) {
    //         return;
    //     }
        
    //     // Create the token reference that would be used in apparatus entries
    //     const tokenRef = `${witnessInfo.prefix}:${tokenId}`;
        
    //     // Find apparatus entry that contains this token
    //     const tab = this.tabs.get(tabId);
    //     if (!tab || !tab.apparatusEntries) {
    //         return;
    //     }
        
    //     const entryToEdit = this.findApparatusEntryForToken(tab, tokenRef, witnessInfo.witnessId);
        
    //     if (entryToEdit) {
    //         // Navigate to this entry (make it the active entry)
    //         this.navigateToApparatusEntry(tabId, entryToEdit);
    //     }
    // }
    
    navigateToApparatusEntry(tabId, entry) {
        const tab = this.tabs.get(tabId);
        if (!tab || !entry) return;
        
        // Find the corresp (location) for this entry
        const targetCorresp = entry.corresp;
        if (!targetCorresp) return;
        
        // Find the index of this corresp in the entry keys
        const targetIndex = tab.entryKeys.indexOf(targetCorresp);
        if (targetIndex === -1) return;
        
        // Navigate to this location
        tab.currentEntryIndex = targetIndex;
        
        // Find the index of this specific entry within the grouped entries
        const entriesAtLocation = tab.groupedEntries[targetCorresp];
        if (entriesAtLocation) {
            const subentryIndex = entriesAtLocation.indexOf(entry);
            if (subentryIndex !== -1) {
                tab.activeSubentryIndex = subentryIndex;
            } else {
                // Fallback to first non-placeholder entry
                tab.activeSubentryIndex = this.findFirstNonPlaceholderEntry(entriesAtLocation);
            }
        }
        
        // Update the display
        this.updateApparatusDisplay(tabId);
        
    }
    
    // findApparatusEntryForToken(tab, tokenRef, witnessId) {
    //     // Check all apparatus entries to see if any contain this token reference
    //     for (const entry of tab.apparatusEntries) {
    //         // Check lemma
    //         if (entry.lemma && entry.lemma.attributes && entry.lemma.attributes.corresp) {
    //             const lemmaCorresp = entry.lemma.attributes.corresp;
    //             if (lemmaCorresp.includes(tokenRef)) {
    //                 return entry;
    //             }
    //         }
            
    //         // Check readings
    //         if (entry.readings) {
    //             for (const reading of entry.readings) {
    //                 if (reading.attributes && reading.attributes.corresp) {
    //                     const readingCorresp = reading.attributes.corresp;
    //                     const readingWit = reading.attributes.wit;
                        
    //                     // Check if this token is in this reading and this witness is included
    //                     if (readingCorresp.includes(tokenRef) && readingWit && readingWit.includes(`#${witnessId}`)) {
    //                         return entry;
    //                     }
    //                 }
    //             }
    //         }
    //     }
        
    //     return null;
    // }
    
    enterEditMode(tabId, entry) {
        // New-format only: transposition entries (<link> pairs, no @target) and
        // explicit-<lem>-override entries stay read-only for now - editing them
        // needs a fundamentally different authoring UI that hasn't been built.
        const tab = this.tabs.get(tabId);
        if (tab && tab.data && tab.data.apparatusFormat === 'new') {
            if (entry.readings && entry.readings.some(r => r.links)) {
                this.showErrorPopup('Cannot Edit', 'Transposition entries cannot be edited here yet.');
                return;
            }
            if (entry.lemma_is_explicit) {
                this.showErrorPopup('Cannot Edit', 'Entries with an explicit adopted-reading override cannot be edited here yet.');
                return;
            }
        }

        // Set edit mode flag and store the entry being edited
        this.editMode = true;
        this.editingEntry = entry;
        this.creationMode = false; // Not creation mode, but edit mode
        
        const newVariantBtn = document.getElementById(`new-variant-btn-${tabId}`);
        const editVariantBtn = document.getElementById(`edit-variant-btn-${tabId}`);
        const readingGroupSelect = document.getElementById(`reading-group-select-${tabId}`);
        
        // Change the Edit Entry button to show Finish
        if (editVariantBtn) {
            editVariantBtn.textContent = 'Finish';
            editVariantBtn.classList.add('active');
        }
        
        // Hide the New App button during edit mode
        if (newVariantBtn) {
            newVariantBtn.style.display = 'none';
        }
        
        if (readingGroupSelect) {
            readingGroupSelect.style.display = 'inline-block';
        }
        
        // Clear all existing token selections and navigation highlights
        this.clearSelectedTokens(tabId);
        this.clearTokenHighlights(tabId);
        
        // Reset and populate selectedTokens based on the entry
        this.populateSelectedTokensFromEntry(tabId, entry);
        
        // Set up token click handlers and keyboard shortcuts  
        this.setupTokenClickHandlersForEdit(tabId);
        this.setupKeyboardShortcuts(tabId);
        
    }
    
    populateSelectedTokensFromEntry(tabId, entry) {

        // Reset selectedTokens
        this.selectedTokens = {
            lemma: [],
            'reading-1': []
        };
        this.nextReadingGroupIndex = 2;
        this.selectedReadingAna = {};

        // Parse lemma tokens
        if (entry.lemma && entry.lemma.attributes && entry.lemma.attributes.corresp) {
            const lemmaCorresp = entry.lemma.attributes.corresp;
            const lemmaTokens = this.parseTokensFromCorresp(lemmaCorresp);
            this.selectedTokens.lemma = lemmaTokens;
        }

        // Parse reading tokens
        if (entry.readings) {
            entry.readings.forEach((reading, index) => {
                if (reading.attributes && reading.attributes.corresp) {
                    const readingGroup = `reading-${index + 1}`;

                    // Ensure the reading group exists in selectedTokens
                    if (!this.selectedTokens[readingGroup]) {
                        this.selectedTokens[readingGroup] = [];
                    }

                    const readingTokens = this.parseTokensFromCorresp(reading.attributes.corresp);
                    this.selectedTokens[readingGroup] = readingTokens;

                    // New-format only: seed this reading group's variant type
                    if (reading.attributes.ana) {
                        this.selectedReadingAna[readingGroup] = reading.attributes.ana;
                    }

                    // Update next reading group index
                    this.nextReadingGroupIndex = Math.max(this.nextReadingGroupIndex, index + 2);
                }
            });
        }
        
        // Add visual selection to tokens
        this.applyTokenSelections(tabId);
        
        // Reset dropdown to lemma
        this.currentReadingGroup = 'lemma';
        this.resetReadingGroupDropdownForEdit(tabId);
        this.updateAnaSelectForGroup(tabId, 'lemma');
    }
    
    parseTokensFromCorresp(corresp) {
        const tokens = [];
        const tokenRefs = corresp.split(' ');

        tokenRefs.forEach(ref => {
            if (!ref.includes(':')) return;
            const colonIndex = ref.indexOf(':');
            const prefix = ref.substring(0, colonIndex);
            const tokenSpec = ref.substring(colonIndex + 1);

            const spec = this.parseTokenSpec(tokenSpec);
            if (spec.type === 'range') return; // ranges not pre-selected in edit mode

            const tokenId = spec.id;
            const isPreSpace = spec.type === 'left';
            const isPostSpace = spec.type === 'right';

            const tokenElements = document.querySelectorAll(`[data-token-id="${tokenId}"]`);

            tokenElements.forEach(tokenElement => {
                // Match the correct span type
                const elIsPreSpace = tokenElement.classList.contains('syn-token-pre');
                const elIsPostSpace = tokenElement.classList.contains('syn-token-post');
                if (elIsPreSpace !== isPreSpace || elIsPostSpace !== isPostSpace) return;

                const synLine = tokenElement.closest('.syn-line');
                const witnessInfo = this.getWitnessInfoFromLine(synLine);

                if (witnessInfo && witnessInfo.prefix === prefix) {
                    tokens.push({
                        tokenId: tokenId,
                        text: tokenElement.textContent.trim(),
                        witnessInfo: witnessInfo,
                        isPreSpace: isPreSpace,
                        isPostSpace: isPostSpace
                    });
                }
            });
        });

        return tokens;
    }
    
    applyTokenSelections(tabId) {
        Object.keys(this.selectedTokens).forEach(group => {
            this.selectedTokens[group].forEach(tokenData => {
                const tokenElements = document.querySelectorAll(`[data-token-id="${tokenData.tokenId}"]`);

                tokenElements.forEach(tokenElement => {
                    // Only apply to the matching span type (pre-space, post-space, or word)
                    const elIsPreSpace = tokenElement.classList.contains('syn-token-pre');
                    const elIsPostSpace = tokenElement.classList.contains('syn-token-post');
                    if (!!elIsPreSpace !== !!tokenData.isPreSpace || !!elIsPostSpace !== !!tokenData.isPostSpace) return;

                    const synLine = tokenElement.closest('.syn-line');
                    const witnessInfo = this.getWitnessInfoFromLine(synLine);

                    if (witnessInfo && witnessInfo.witnessId === tokenData.witnessInfo.witnessId) {
                        tokenElement.classList.add(`selected-${group}`);
                    }
                });
            });
        });
    }
    
    setupTokenClickHandlersForEdit(tabId) {
        // Similar to setupTokenClickHandlers but for edit mode
        const tabPanel = document.getElementById(`panel-${tabId}`);
        if (!tabPanel) return;
        
        const tokens = tabPanel.querySelectorAll('.syn-token');
        tokens.forEach(token => {
            token.style.cursor = 'pointer';
            token.setAttribute('data-creation-clickable', 'true');
        });
        
        // Set up event delegation if not already done
        if (!this.delegationHandler) {
            this.setupTokenEventDelegation();
        }
    }
    
    resetReadingGroupDropdownForEdit(tabId) {
        const readingGroupSelect = document.getElementById(`reading-group-select-${tabId}`);
        if (!readingGroupSelect) return;
        
        // Clear existing options except lemma
        readingGroupSelect.innerHTML = `<option value="lemma">${this.getReadingGroupLabel('lemma')}</option>`;

        // Add options for existing reading groups
        Object.keys(this.selectedTokens).forEach(group => {
            if (group !== 'lemma') {
                const match = group.match(/reading-(\d+)/);
                if (match) {
                    const option = document.createElement('option');
                    option.value = group;
                    option.textContent = this.getReadingGroupLabel(group);
                    readingGroupSelect.appendChild(option);
                }
            }
        });
        
        // Add "new group" option
        const newGroupOption = document.createElement('option');
        newGroupOption.value = 'new-group';
        newGroupOption.textContent = '+ New Reading';
        readingGroupSelect.appendChild(newGroupOption);
        
        // Set to lemma
        readingGroupSelect.value = 'lemma';
    }
    
    exitEditMode(tabId) {
        const tab = this.tabs.get(tabId);
        if (tab && tab.data && tab.data.apparatusFormat === 'new') {
            // New-format only: persist the edit before tearing down edit mode.
            // On validation/server failure, stay in edit mode so the user can
            // fix the selection and retry.
            this.saveEditedEntryToServer(tabId).then(success => {
                if (success) {
                    this._finishExitEditMode(tabId);
                }
            });
            return;
        }

        // Old format: save the edited entry (client-only, unchanged)
        this.saveEditedEntry(tabId);
        this._finishExitEditMode(tabId);
    }

    _finishExitEditMode(tabId) {
        // Clean up edit mode
        this.editMode = false;
        this.editingEntry = null;
        
        const newVariantBtn = document.getElementById(`new-variant-btn-${tabId}`);
        const editVariantBtn = document.getElementById(`edit-variant-btn-${tabId}`);
        const readingGroupSelect = document.getElementById(`reading-group-select-${tabId}`);
        
        // Restore the New Entry button
        if (newVariantBtn) {
            newVariantBtn.textContent = 'New Entry';
            newVariantBtn.classList.remove('active');
            newVariantBtn.style.backgroundColor = '';
            newVariantBtn.style.display = ''; // Show it again
        }
        
        // Restore the Edit Entry button
        if (editVariantBtn) {
            editVariantBtn.textContent = 'Edit Entry';
            editVariantBtn.classList.remove('active');
        }
        
        if (readingGroupSelect) {
            readingGroupSelect.style.display = 'none';
        }
        const readingAnaSelect = document.getElementById(`reading-ana-select-${tabId}`);
        if (readingAnaSelect) readingAnaSelect.style.display = 'none';
        
        // Clear all selected tokens
        this.clearSelectedTokens(tabId);
        
        // Remove token click handlers for edit mode
        this.removeTokenClickHandlers(tabId);
        this.removeKeyboardShortcuts();
        
        // Restore token event delegation for navigation (non-edit mode)
        this.setupTokenEventDelegation();
        
        // Update the apparatus display
        this.updateApparatusDisplay(tabId);
    }
    
    saveEditedEntry(tabId) {
        if (!this.editingEntry) return;
        
        // Get current location from the editing entry
        const currentLoc = this.editingEntry.loc;
        
        // Create new entry data from current selections
        const updatedEntryData = this.createApparatusEntry(currentLoc);
        
        // Update the editing entry with new data, preserving original structure
        this.editingEntry.lemma = updatedEntryData.lemma;
        this.editingEntry.readings = updatedEntryData.readings;
        
        // Since this.editingEntry is a reference to the original entry object,
        // the changes should automatically be reflected in all data structures
    }
    
    updateGroupedEntriesForEditedEntry(tab, editedEntry) {
        const corresp = editedEntry.corresp;
        
        if (tab.groupedEntries && tab.groupedEntries[corresp]) {
            // Find and update the entry in grouped entries
            const entryIndex = tab.groupedEntries[corresp].findIndex(entry => entry === editedEntry);
            if (entryIndex >= 0) {
                tab.groupedEntries[corresp][entryIndex] = editedEntry;
            }
        }
    }
    
    getWitnessInfoFromLine(synLine) {
        if (!synLine) return null;
        
        const witElement = synLine.querySelector('.syn-line-wit');
        if (!witElement) return null;
        
        const lineId = witElement.getAttribute('data-line-id');
        if (!lineId) return null;
        
        // Extract witness prefix from line-id (e.g., "a:123" -> "a")
        const prefix = lineId.includes(':') ? lineId.split(':')[0] : lineId;
        
        // Find corresponding witness from mapping
        for (const [witnessId, mappingInfo] of Object.entries(this.witnessMapping || {})) {
            if (mappingInfo.synoptic_prefix === prefix) {
                return {
                    witnessId: witnessId,
                    siglum: mappingInfo.siglum || witnessId,
                    prefix: prefix
                };
            }
        }
        
        return { witnessId: prefix, siglum: prefix, prefix: prefix };
    }
    
    resetReadingGroupDropdown(tabId) {
        const select = document.getElementById(`reading-group-select-${tabId}`);
        if (!select) return;
        
        // Clear all options
        select.innerHTML = '';
        
        // Add default options
        const options = [
            { value: 'lemma', text: this.getReadingGroupLabel('lemma') },
            { value: 'reading-1', text: this.getReadingGroupLabel('reading-1') },
            { value: 'new-group', text: '+ New reading group' }
        ];
        
        options.forEach(optionData => {
            const option = document.createElement('option');
            option.value = optionData.value;
            option.textContent = optionData.text;
            select.appendChild(option);
        });
        
        // Select lemma as default
        select.value = 'lemma';
    }
    
    handleReadingGroupChange(tabId, value) {
        
        if (value === 'new-group') {
            // Create new reading group
            const newGroupName = `reading-${this.nextReadingGroupIndex}`;
            this.selectedTokens[newGroupName] = [];
            this.nextReadingGroupIndex++;
            
            // Update dropdown
            const select = document.getElementById(`reading-group-select-${tabId}`);
            const newOption = document.createElement('option');
            newOption.value = newGroupName;
            newOption.textContent = this.getReadingGroupLabel(newGroupName);
            select.insertBefore(newOption, select.lastElementChild);
            
            // Select the new group
            select.value = newGroupName;
            this.currentReadingGroup = newGroupName;
        } else {
            this.currentReadingGroup = value;
        }
        this.updateAnaSelectForGroup(tabId, this.currentReadingGroup);
    }
    
    clearSelectedTokens(tabId) {
        const tabPanel = document.getElementById(`panel-${tabId}`);
        if (!tabPanel) return;

        // Remove all selection classes
        Object.keys(this.selectedTokens).forEach(group => {
            tabPanel.querySelectorAll(`.selected-${group}`).forEach(token => {
                token.classList.remove(`selected-${group}`);
            });
        });

        // Clear any leftover transposition order-number badges
        tabPanel.querySelectorAll('.transposition-numbered').forEach(token => {
            token.classList.remove('transposition-numbered');
            token.removeAttribute('data-transposition-index');
        });
    }
    
    saveNewEntry(tabId) {

        const tab = this.tabs.get(tabId);
        if (!tab) return;
        
        // Get current location from the active entry
        const currentLoc = this.getCurrentLocation(tab);
        const currentCorresp = `${this.leithsPrefix || 'a'}:l_${currentLoc}`;
        
        // Initialize newEntries array if not exists
        if (!tab.newEntries) {
            tab.newEntries = [];
        }
        
        // Initialize currentlyEditing entry for this session if not exists
        if (!tab.currentlyEditingEntry) {
            tab.currentlyEditingEntry = null;
        }
        
        // Check if we have any selected tokens
        const hasSelections = Object.values(this.selectedTokens).some(group => group.length > 0);
        
        if (hasSelections) {
            // Create apparatus entry from current selections
            const entryData = this.createApparatusEntry(currentLoc);
            
            if (!tab.currentlyEditingEntry || tab.currentlyEditingEntry.corresp !== currentCorresp) {
                // Starting to edit a new entry - create it
                tab.currentlyEditingEntry = entryData;
                tab.currentlyEditingEntry.isUserCreated = true;
                
                // Add to newEntries array
                tab.newEntries.push(tab.currentlyEditingEntry);
                
                // Add to grouped entries for display
                this.updateGroupedEntriesWithNewEntry(tab, tab.currentlyEditingEntry);
            } else {
                // Update the currently editing entry
                Object.assign(tab.currentlyEditingEntry, entryData);
                
                // Update in grouped entries
                this.updateExistingEntryInGroupedEntries(tab, tab.currentlyEditingEntry);
            }
            
        } else {
            // No selections - clear currently editing entry if it exists
            if (tab.currentlyEditingEntry && tab.currentlyEditingEntry.corresp === currentCorresp) {
                // Remove from newEntries
                const entryIndex = tab.newEntries.indexOf(tab.currentlyEditingEntry);
                if (entryIndex >= 0) {
                    tab.newEntries.splice(entryIndex, 1);
                }
                
                // Remove from grouped entries
                this.removeNewEntryFromGroupedEntries(tab, tab.currentlyEditingEntry);
                
                // Clear currently editing reference
                tab.currentlyEditingEntry = null;
            }
        }
        
        // Don't update the apparatus display during creation mode to avoid DOM rebuilds
        // that interfere with token selection. The display will be updated when
        // creation mode is exited.
        if (!this.creationMode) {
            this.updateApparatusDisplay(tabId);
        }
    }
    
    getCurrentLocation(tab) {
        if (tab.entryKeys && tab.entryKeys.length > 0 && typeof tab.currentEntryIndex === 'number') {
            const currentCorresp = tab.entryKeys[tab.currentEntryIndex];
            const entries = tab.groupedEntries[currentCorresp];
            if (entries && entries.length > 0) {
                return entries[0].loc;
            }
        }
        return '1'; // Default location
    }
    
    getAnchorWordText(tokenData) {
        const witElement = document.querySelector(`.syn-line-wit[data-line-id^="${tokenData.witnessInfo.prefix}:"]`);
        if (!witElement) return '';
        const synLine = witElement.closest('.syn-line');
        if (!synLine) return '';
        const wordSpan = synLine.querySelector(`.syn-tei-w[data-token-id="${tokenData.tokenId}"]`);
        return wordSpan ? wordSpan.textContent.trim() : '';
    }

    tokenSortKey(tokenId) {
        const m = tokenId.match(/w_(\d+)_(\d+)/);
        return m ? parseInt(m[1]) * 100000 + parseInt(m[2]) : 0;
    }

    buildCorrespPartsForTokens(prefix, tokens) {
        // Returns the individual "prefix:spec" address parts as an array (not
        // joined into a string) - a range() part contains an internal ", "
        // separator, so callers that need to count/enumerate distinct
        // addresses must use this instead of splitting buildCorrespForTokens's
        // joined output on whitespace (that would wrongly split one range()
        // into two parts).
        const wordTokens = tokens.filter(t => !t.isPreSpace && !t.isPostSpace);
        const prePostParts = tokens
            .filter(t => t.isPreSpace || t.isPostSpace)
            .map(t => t.isPreSpace ? `${prefix}:left(${t.tokenId})` : `${prefix}:right(${t.tokenId})`);

        let wordPart;
        if (wordTokens.length >= 2) {
            const sorted = [...wordTokens].sort((a, b) => this.tokenSortKey(a.tokenId) - this.tokenSortKey(b.tokenId));
            wordPart = `${prefix}:range(${sorted[0].tokenId}, ${sorted[sorted.length - 1].tokenId})`;
        } else if (wordTokens.length === 1) {
            wordPart = `${prefix}:${wordTokens[0].tokenId}`;
        }

        return [...prePostParts, ...(wordPart ? [wordPart] : [])];
    }

    buildCorrespForTokens(prefix, tokens) {
        return this.buildCorrespPartsForTokens(prefix, tokens).join(' ');
    }

    buildLeftContent(tokenData) {
        const anchorWord = this.getAnchorWordText(tokenData);
        const tail = anchorWord ? ` ${anchorWord}` : '';
        return {
            text: `vor${tail}`,
            html: `<em>vor</em>${this.escapeHtml(tail)}`,
            children: [{ tag: 'emph', text: 'vor', tail: tail }]
        };
    }

    buildRightContent(tokenData) {
        const anchorWord = this.getAnchorWordText(tokenData);
        const tail = anchorWord ? ` ${anchorWord}` : '';
        return {
            text: `nach${tail}`,
            html: `<em>nach</em>${this.escapeHtml(tail)}`,
            children: [{ tag: 'emph', text: 'nach', tail: tail }]
        };
    }

    buildNewFormatSavePayload() {
        // New-format only: turn the current token selection into a
        // { target, readings } payload for /apparatus/entry/create or
        // /apparatus/entry/update, or an { error } describing why the
        // current selection can't be saved. Dispatches to the transposition
        // branch when any reading group is in transposition (paired-click)
        // mode; otherwise auto-detects Addition/Omission/Substitution from
        // the shape of the lemma vs. each reading group's selection.
        const transpositionGroups = Object.keys(this.selectedReadingAna).filter(
            group => this.selectedReadingAna[group] === 'hc:TranspositionVariant'
        );
        if (transpositionGroups.length > 0) {
            return this.buildTranspositionSavePayload(transpositionGroups);
        }

        const lemmaTokens = this.selectedTokens.lemma || [];
        if (lemmaTokens.length === 0) {
            return { error: 'Select at least one lemma token (from the base text row) before saving.' };
        }
        const nonBaseLemmaToken = lemmaTokens.find(t => t.witnessInfo.prefix !== this.leithsPrefix);
        if (nonBaseLemmaToken) {
            return { error: 'The lemma must be selected from the base text row only.' };
        }
        const targetParts = this.buildCorrespPartsForTokens(this.leithsPrefix, lemmaTokens);
        if (targetParts.length !== 1) {
            return { error: 'The lemma selection must resolve to a single location (one word, range, or gap position).' };
        }
        const target = targetParts[0];
        const lemmaIsGapOnly = lemmaTokens.every(t => t.isPreSpace || t.isPostSpace);
        const lemmaIsWordOnly = lemmaTokens.every(t => !t.isPreSpace && !t.isPostSpace);

        const readingGroupNames = Object.keys(this.selectedTokens).filter(
            group => group !== 'lemma' && this.selectedTokens[group] && this.selectedTokens[group].length > 0
        );
        if (readingGroupNames.length === 0) {
            return { error: 'Select at least one reading (tokens from a witness other than the base text).' };
        }

        const readings = [];
        for (const group of readingGroupNames) {
            const tokens = this.selectedTokens[group];

            const isGapOnly = tokens.every(t => t.isPreSpace || t.isPostSpace);
            const isWordOnly = tokens.every(t => !t.isPreSpace && !t.isPostSpace);
            if (!isGapOnly && !isWordOnly) {
                return { error: `${group}: select either words or a single gap position, not both.` };
            }

            // Variant type is fully determined by the shape of the lemma vs.
            // this reading - no manual choice needed (see the plan's table:
            // word/word -> Substitution, gap/word -> Addition, word/gap ->
            // Omission, gap/gap -> error, at least one side needs a word).
            let ana;
            if (lemmaIsGapOnly && isGapOnly) {
                return { error: `${group}: the base text and this reading can't both be empty gap positions - at least one side must have a word.` };
            } else if (lemmaIsGapOnly && isWordOnly) {
                ana = 'hc:AdditionVariant';
            } else if (lemmaIsWordOnly && isGapOnly) {
                ana = 'hc:OmissionVariant';
            } else {
                ana = 'hc:SubstitutionVariant';
            }

            const witGroups = {};
            tokens.forEach(token => {
                const witId = token.witnessInfo.witnessId;
                if (!witGroups[witId]) witGroups[witId] = [];
                witGroups[witId].push(token);
            });

            const wit = Object.keys(witGroups);
            const ptrs = [];
            Object.values(witGroups).forEach(witTokens => {
                const parts = this.buildCorrespPartsForTokens(witTokens[0].witnessInfo.prefix, witTokens);
                ptrs.push(...parts);
            });

            readings.push({ wit, ana, ptrs });
        }

        return { target, readings };
    }

    buildTranspositionSavePayload(transpositionGroups) {
        // Lemma is selected normally (base-text tokens, any order) and
        // numbered by document position (see updateTranspositionNumbering).
        // Each transposition reading group's tokens are numbered by CLICK
        // order per witness - witness token #N pairs with lemma token #N, so
        // each witness present must contribute exactly as many tokens as the
        // lemma has.
        const lemmaTokens = this.selectedTokens.lemma || [];
        if (lemmaTokens.length === 0) {
            return { error: 'Select the base-text (lemma) tokens involved in the transposition first.' };
        }
        const nonBaseLemmaToken = lemmaTokens.find(t => t.witnessInfo.prefix !== this.leithsPrefix);
        if (nonBaseLemmaToken) {
            return { error: 'The lemma must be selected from the base text row only.' };
        }
        if (lemmaTokens.some(t => t.isPreSpace || t.isPostSpace)) {
            return { error: 'Transposition lemma tokens must be words, not gap positions.' };
        }
        const sortedLemma = [...lemmaTokens].sort((a, b) => this.tokenSortKey(a.tokenId) - this.tokenSortKey(b.tokenId));

        const mixedGroup = Object.keys(this.selectedTokens).find(group =>
            group !== 'lemma' && !transpositionGroups.includes(group) &&
            this.selectedTokens[group] && this.selectedTokens[group].length > 0
        );
        if (mixedGroup) {
            return { error: `${mixedGroup} has a normal token selection - a transposition entry can't mix transposition and non-transposition readings.` };
        }

        const readings = [];
        for (const group of transpositionGroups) {
            const tokens = (this.selectedTokens[group] || []).filter(t => !t.isPreSpace && !t.isPostSpace);
            if (tokens.length === 0) {
                return { error: `${group}: click the witness token(s) that correspond, in order, to the ${sortedLemma.length} lemma token(s).` };
            }

            const byWitness = {};
            tokens.forEach(t => {
                const witId = t.witnessInfo.witnessId;
                if (!byWitness[witId]) byWitness[witId] = [];
                byWitness[witId].push(t);
            });

            const links = [];
            for (const [witId, witTokens] of Object.entries(byWitness)) {
                if (witTokens.length !== sortedLemma.length) {
                    return { error: `${group}: witness "${witId}" has ${witTokens.length} token(s) selected, but the lemma has ${sortedLemma.length} - select exactly the same number, in corresponding order.` };
                }
                witTokens.forEach((witnessToken, index) => {
                    links.push({
                        base: `${sortedLemma[index].witnessInfo.prefix}:${sortedLemma[index].tokenId}`,
                        witness: `${witnessToken.witnessInfo.prefix}:${witnessToken.tokenId}`
                    });
                });
            }

            readings.push({ wit: Object.keys(byWitness), ana: 'hc:TranspositionVariant', links });
        }

        return { target: null, readings };
    }

    getCurrentActiveEntry(tabId) {
        const tab = this.tabs.get(tabId);
        if (!tab || !tab.entryKeys || tab.currentEntryIndex < 0) return null;
        const currentCorresp = tab.entryKeys[tab.currentEntryIndex];
        const currentEntries = tab.groupedEntries[currentCorresp];
        if (!currentEntries || tab.activeSubentryIndex < 0 || tab.activeSubentryIndex >= currentEntries.length) return null;
        return currentEntries[tab.activeSubentryIndex];
    }

    refreshApparatusEntriesInTab(tabId, freshEntries) {
        // Rebuilds a tab's whole apparatus-entries view from a fresh server
        // response after a create/update/delete - avoids reasoning about
        // stale entry.id/index values, which shift after any insert/delete.
        const tab = this.tabs.get(tabId);
        if (!tab) return;

        const synopticMap = tab.synopticMapData ? tab.synopticMapData.synoptic_map : {};
        const mergedEntries = this.mergeApparatusWithSynopticMap(freshEntries, synopticMap);

        const previousCorresp = tab.entryKeys ? tab.entryKeys[tab.currentEntryIndex] : null;

        tab.apparatusEntries = mergedEntries;
        tab.groupedEntries = this.groupEntriesByCorresp(mergedEntries);
        tab.entryKeys = Object.keys(tab.groupedEntries);
        tab.entryKeys.sort((a, b) => {
            const locA = tab.groupedEntries[a][0]?.loc || '';
            const locB = tab.groupedEntries[b][0]?.loc || '';
            const numA = parseInt(locA) || 0;
            const numB = parseInt(locB) || 0;
            return numA - numB;
        });

        const restoredIndex = previousCorresp ? tab.entryKeys.indexOf(previousCorresp) : -1;
        tab.currentEntryIndex = restoredIndex >= 0 ? restoredIndex : 0;

        if (tab.entryKeys.length > 0) {
            const currentEntries = tab.groupedEntries[tab.entryKeys[tab.currentEntryIndex]];
            tab.activeSubentryIndex = this.findFirstNonPlaceholderEntry(currentEntries);
        } else {
            tab.activeSubentryIndex = -1;
        }

        this.updateApparatusDisplay(tabId);
        this.markGapSymbolsWithContent(tab);
    }

    async saveNewEntryToServer(tabId) {
        const tab = this.tabs.get(tabId);
        if (!tab || !tab.data) return false;

        const payload = this.buildNewFormatSavePayload();
        if (payload.error) {
            this.showErrorPopup('Cannot Save Entry', payload.error);
            return false;
        }

        try {
            const response = await this.apiRequest('/apparatus/entry/create', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    apparatus_file: tab.data.apparatusFile,
                    project_directory: tab.data.projectDirectory,
                    target: payload.target,
                    readings: payload.readings
                })
            });

            if (!response.success) {
                this.showErrorPopup('Save Failed', response.error || 'Failed to save the new entry.');
                return false;
            }

            this.refreshApparatusEntriesInTab(tabId, response.apparatus_entries);
            return true;
        } catch (error) {
            this.showErrorPopup('Save Failed', `Error saving entry: ${error.message}`);
            return false;
        }
    }

    async saveEditedEntryToServer(tabId) {
        const tab = this.tabs.get(tabId);
        if (!tab || !tab.data || !this.editingEntry) return false;

        const payload = this.buildNewFormatSavePayload();
        if (payload.error) {
            this.showErrorPopup('Cannot Save Entry', payload.error);
            return false;
        }

        const entryIndex = (this.editingEntry.id || 1) - 1;

        try {
            const response = await this.apiRequest('/apparatus/entry/update', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    apparatus_file: tab.data.apparatusFile,
                    project_directory: tab.data.projectDirectory,
                    entry_index: entryIndex,
                    target: payload.target,
                    readings: payload.readings
                })
            });

            if (!response.success) {
                this.showErrorPopup('Save Failed', response.error || 'Failed to save changes to the entry.');
                return false;
            }

            this.refreshApparatusEntriesInTab(tabId, response.apparatus_entries);
            return true;
        } catch (error) {
            this.showErrorPopup('Save Failed', `Error saving entry: ${error.message}`);
            return false;
        }
    }

    async deleteCurrentEntryOnServer(tabId) {
        const tab = this.tabs.get(tabId);
        if (!tab || !tab.data) return;

        const entry = this.getCurrentActiveEntry(tabId);
        if (!entry || entry.is_placeholder) {
            this.showErrorPopup('Cannot Delete', 'No apparatus entry is currently selected.');
            return;
        }
        if (entry.lemma_is_explicit) {
            this.showErrorPopup('Cannot Delete', 'Entries with an explicit adopted-reading override cannot be deleted here yet.');
            return;
        }

        if (!confirm('Delete this apparatus entry? This cannot be undone.')) {
            return;
        }

        try {
            const response = await this.apiRequest('/apparatus/entry/delete', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    apparatus_file: tab.data.apparatusFile,
                    project_directory: tab.data.projectDirectory,
                    entry_index: (entry.id || 1) - 1
                })
            });

            if (!response.success) {
                this.showErrorPopup('Delete Failed', response.error || 'Failed to delete the entry.');
                return;
            }

            this.refreshApparatusEntriesInTab(tabId, response.apparatus_entries);
        } catch (error) {
            this.showErrorPopup('Delete Failed', `Error deleting entry: ${error.message}`);
        }
    }

    handleAnaChange(tabId, group, value) {
        if (!group || group === 'lemma') return;
        if (value) {
            this.selectedReadingAna[group] = value;
        } else {
            delete this.selectedReadingAna[group];
        }
        // Show/clear the order-number badges immediately - don't wait for the
        // first reading-token click, the lemma is typically already selected
        // by the time Transposition is chosen here.
        this.updateTranspositionNumbering(tabId);
    }

    updateAnaSelectForGroup(tabId, group) {
        const tab = this.tabs.get(tabId);
        const select = document.getElementById(`reading-ana-select-${tabId}`);
        if (!select) return;

        // Only shown during creation: Addition/Omission/Substitution are
        // auto-detected from the selection shape (no manual choice needed),
        // and the only remaining manual choice - Transposition - isn't
        // available when editing (existing entries can't be converted into
        // or out of a transposition here; enterEditMode already refuses to
        // edit transposition entries at all).
        const isNewFormat = tab && tab.data && tab.data.apparatusFormat === 'new';

        if (isNewFormat && this.creationMode && group && group !== 'lemma') {
            select.style.display = '';
            select.value = this.selectedReadingAna[group] || '';
        } else {
            select.style.display = 'none';
        }
    }

    createApparatusEntry(loc) {
        const entry = {
            loc: loc,
            corresp: `${this.leithsPrefix || 'a'}:l_${loc}`,
            lemma: null,
            readings: []
        };
        
        // Process lemma
        if (this.selectedTokens.lemma && this.selectedTokens.lemma.length > 0) {
            const lemmaTokens = this.selectedTokens.lemma;

            // Group tokens by witness (same logic as readings)
            const witGroups = {};
            lemmaTokens.forEach(token => {
                const witId = token.witnessInfo.witnessId;
                if (!witGroups[witId]) witGroups[witId] = [];
                witGroups[witId].push(token);
            });

            const witIds = Object.keys(witGroups).map(id => `#${id}`).join(' ');
            const correspParts = [];
            Object.entries(witGroups).forEach(([witId, tokens]) => {
                correspParts.push(this.buildCorrespForTokens(tokens[0].witnessInfo.prefix, tokens));
            });

            // Use first witness tokens for text content
            const firstWitnessTokens = witGroups[Object.keys(witGroups)[0]];
            const preSpaceToken = firstWitnessTokens.find(t => t.isPreSpace);
            const postSpaceToken = firstWitnessTokens.find(t => t.isPostSpace);
            let lemmaText, lemmaHtml, lemmaChildren;
            if (preSpaceToken) {
                const content = this.buildLeftContent(preSpaceToken);
                lemmaText = content.text;
                lemmaHtml = content.html;
                lemmaChildren = content.children;
            } else if (postSpaceToken) {
                const content = this.buildRightContent(postSpaceToken);
                lemmaText = content.text;
                lemmaHtml = content.html;
                lemmaChildren = content.children;
            } else {
                lemmaText = firstWitnessTokens.map(t => t.text).join(' ');
                lemmaHtml = null;
                lemmaChildren = null;
            }

            entry.lemma = {
                text: lemmaText,
                ...(lemmaHtml && { html: lemmaHtml }),
                ...(lemmaChildren && { children: lemmaChildren }),
                attributes: {
                    wit: witIds,
                    corresp: correspParts.join(' ')
                }
            };
        }
        
        // Process readings
        Object.keys(this.selectedTokens).forEach(group => {
            if (group !== 'lemma' && this.selectedTokens[group].length > 0) {
                const readingTokens = this.selectedTokens[group];
                
                // Group tokens by witness
                const witGroups = {};
                readingTokens.forEach(token => {
                    const witId = token.witnessInfo.witnessId;
                    if (!witGroups[witId]) {
                        witGroups[witId] = [];
                    }
                    witGroups[witId].push(token);
                });
                
                // Get reading text from the first witness only
                const firstWitnessId = Object.keys(witGroups)[0];
                const firstWitnessTokens = witGroups[firstWitnessId];
                const firstPreSpace = firstWitnessTokens.find(t => t.isPreSpace);
                const firstPostSpace = firstWitnessTokens.find(t => t.isPostSpace);

                let readingText, readingHtml, readingChildren;
                if (firstPreSpace) {
                    const content = this.buildLeftContent(firstPreSpace);
                    readingText = content.text;
                    readingHtml = content.html;
                    readingChildren = content.children;
                } else if (firstPostSpace) {
                    const content = this.buildRightContent(firstPostSpace);
                    readingText = content.text;
                    readingHtml = content.html;
                    readingChildren = content.children;
                } else {
                    readingText = firstWitnessTokens.map(t => t.text).join(' ');
                    readingHtml = null;
                    readingChildren = null;
                }

                // Create corresp and wit attributes
                const witIds = Object.keys(witGroups).map(id => `#${id}`).join(' ');
                const correspParts = [];
                Object.entries(witGroups).forEach(([witId, tokens]) => {
                    correspParts.push(this.buildCorrespForTokens(tokens[0].witnessInfo.prefix, tokens));
                });

                entry.readings.push({
                    text: readingText,
                    ...(readingHtml && { html: readingHtml }),
                    ...(readingChildren && { children: readingChildren }),
                    attributes: {
                        wit: witIds,
                        corresp: correspParts.join(' ')
                    }
                });
            }
        });
        
        return entry;
    }
    
    updateGroupedEntriesWithNewEntry(tab, newEntry) {
        const corresp = newEntry.corresp;
        
        // Initialize grouped entries if not exists
        if (!tab.groupedEntries) {
            tab.groupedEntries = {};
        }
        
        // Mark the entry as user-created for styling
        newEntry.isUserCreated = true;
        
        // Add to grouped entries
        if (!tab.groupedEntries[corresp]) {
            tab.groupedEntries[corresp] = [];
            
            // Add to entryKeys and sort
            if (!tab.entryKeys) {
                tab.entryKeys = [];
            }
            tab.entryKeys.push(corresp);
            
            // Re-sort entry keys by location
            tab.entryKeys.sort((a, b) => {
                const locA = tab.groupedEntries[a][0]?.loc || '';
                const locB = tab.groupedEntries[b][0]?.loc || '';
                const numA = parseInt(locA) || 0;
                const numB = parseInt(locB) || 0;
                return numA - numB;
            });
        }
        
        // Always add new user-created entry (don't replace existing ones)
        tab.groupedEntries[corresp].push(newEntry);
        const subentryIndex = tab.groupedEntries[corresp].length - 1;
        
        // Make this entry active and navigate to its location
        const correspIndex = tab.entryKeys.indexOf(corresp);
        if (correspIndex >= 0) {
            tab.currentEntryIndex = correspIndex;
            tab.activeSubentryIndex = subentryIndex;
        }
    }
    
    updateExistingEntryInGroupedEntries(tab, updatedEntry) {
        const corresp = updatedEntry.corresp;
        
        if (tab.groupedEntries && tab.groupedEntries[corresp]) {
            // Find the entry in grouped entries and update it
            const entryIndex = tab.groupedEntries[corresp].findIndex(entry => entry === updatedEntry);
            if (entryIndex >= 0) {
                // Entry is already in the array and will be updated by reference
            }
        }
    }
    
    removeNewEntryFromGroupedEntries(tab, removedEntry) {
        const corresp = removedEntry.corresp;
        
        if (tab.groupedEntries && tab.groupedEntries[corresp]) {
            // Remove user-created entries for this corresp
            tab.groupedEntries[corresp] = tab.groupedEntries[corresp].filter(entry => !entry.isUserCreated);
            
            // If no entries left for this corresp, remove the corresp key entirely
            if (tab.groupedEntries[corresp].length === 0) {
                delete tab.groupedEntries[corresp];
                
                // Remove from entryKeys
                const keyIndex = tab.entryKeys.indexOf(corresp);
                if (keyIndex >= 0) {
                    tab.entryKeys.splice(keyIndex, 1);
                }
                
                // Adjust current entry index if needed
                if (tab.currentEntryIndex >= tab.entryKeys.length && tab.entryKeys.length > 0) {
                    tab.currentEntryIndex = tab.entryKeys.length - 1;
                }
            }
        }
    }
    
    async saveProject() {
        if (!this.activeTabId) {
            alert('No active project tab to save');
            return;
        }
        
        const tab = this.tabs.get(this.activeTabId);
        if (!tab || tab.type !== 'project') {
            alert('Active tab is not a project');
            return;
        }
        
        if (!tab.newEntries || tab.newEntries.length === 0) {
            alert('No new entries to save');
            return;
        }
        
        try {
            const requestData = {
                apparatus_file: tab.data.apparatusFile,
                new_entries: tab.newEntries,
                project_directory: tab.data.projectDirectory
            };
            
            
            const response = await this.apiRequest('/apparatus/save', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(requestData)
            });
            
            if (response.success) {
                alert(`Project saved! ${tab.newEntries.length} new entries added.`);
                // Clear the new entries as they're now saved
                tab.newEntries = [];
            } else {
                console.error('Save failed:', response);
                alert(`Failed to save project: ${response.error || 'Unknown error'}`);
            }
        } catch (error) {
            console.error('Error saving project:', error);
            alert('Error saving project. Check the console for details.');
        }
    }

}

document.addEventListener('DOMContentLoaded', () => {
    window.heiCritApp = new HeiCritApp();
});