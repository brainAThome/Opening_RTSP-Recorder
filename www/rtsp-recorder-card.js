console.info("%c RTSP RECORDER CARD \n%c v1.0.6 ", "color: #3498db; font-weight: bold; background: #222; padding: 5px;");

class RtspRecorderCard extends HTMLElement {
    constructor() {
        super();
        this.attachShadow({ mode: 'open' });
        this._selectedDate = null;
        this._selectedCam = 'Alle';
        this._kioskActive = false;
        this._animationsEnabled = true;
        this._cachedHeader = null;
        this._activeTab = 'general';
        this._currentEvent = null;
        this._currentVideoUrl = null;
        // Erweiterte Objektliste: Outdoor + Indoor (v1.0.6)
        this._analysisObjects = [
            'person', 'cat', 'dog', 'bird',
            'car', 'truck', 'bicycle', 'motorcycle', 'bus',
            'tv', 'couch', 'chair', 'bed', 'dining table', 'potted plant',
            'laptop', 'cell phone', 'remote',
            'bottle', 'cup', 'book', 'backpack', 'umbrella', 'suitcase', 'package'
        ];
        this._analysisSelected = new Set(['person']);
        this._analysisDevice = 'cpu';
        this._analysisOverview = { items: [], stats: {} };
        this._analysisOverviewLoaded = false;
        this._analysisLoading = false;
        this._perfSensors = { cpu: null, igpu: null, coral: null };
        this._analysisDeviceOptions = null;
        this._overlayEnabled = false;
        this._analysisDetections = null;
        this._analysisInterval = 2;
        this._analysisFrameSize = null;
        this._showPerfTab = true;
        this._showPerfPanel = false;
        this._showFooter = true;
        this._settingsKey = 'rtsp_recorder_settings';
        this.loadLocalSettings();
        this._detectorStats = null;
        this._statsPolling = null;
        this._systemSensors = {
            cpu: 'sensor.processor_use',
            memory: 'sensor.memory_use_percent',
            temp: 'sensor.processor_temperature',
            load1m: 'sensor.load_1m',
            disk: 'sensor.disk_use_percent'
        };
        this._liveStats = {};
        this._statsHistory = [];
        this._maxHistoryPoints = 60;
        const now = new Date();
        this._calYear = now.getFullYear();
        this._calMonth = now.getMonth();
    }

    setConfig(config) {
        this._config = config || {};
        this._basePath = this._config.base_path || '/media/rtsp_recordings';
        this._thumbBase = this._config.thumb_path || '/local/thumbnails';
    }

    set hass(hass) {
        this._hass = hass;
        if (!this._renderDone) {
            this.render();
            this._renderDone = true;
            this.loadData();
            this.loadAnalysisConfig(); // v1.0.6: Lade globale Analyse-Einstellungen
            this.renderCalendar();
        }
    }

    // v1.0.6: Laedt globale Analyse-Konfiguration aus der Integration
    async loadAnalysisConfig() {
        try {
            const config = await this._hass.callWS({
                type: 'rtsp_recorder/get_analysis_config'
            });
            if (config && config.analysis_objects && config.analysis_objects.length > 0) {
                // Aktualisiere die ausgewaehlten Objekte mit den globalen Einstellungen
                this._analysisSelected = new Set(config.analysis_objects);
                console.log('[RTSP-Recorder] Loaded global analysis objects:', config.analysis_objects);
                
                // Aktualisiere die Checkboxen in der UI falls bereits gerendert
                this.shadowRoot.querySelectorAll('.fm-obj').forEach(cb => {
                    cb.checked = this._analysisSelected.has(cb.value);
                });
            }
            if (config && config.analysis_device) {
                this._analysisDevice = config.analysis_device;
                // Aktualisiere das Device-Dropdown falls vorhanden
                const deviceSelect = this.shadowRoot.querySelector('#analysis-device');
                if (deviceSelect) {
                    deviceSelect.value = this._analysisDevice;
                }
            }
        } catch (e) {
            console.warn('[RTSP-Recorder] Could not load analysis config:', e);
        }
    }

    render() {
        const root = this.shadowRoot;
        root.innerHTML = `
            <style>
                :host { display: block; --primary-color: #03a9f4; --bg-dark: #0d0d0d; --header-bg: #1a1a1a; }
                .fm-container { background: var(--bg-dark); color: #eee; height: 85vh; border-radius: 12px; overflow: hidden; font-family: 'Roboto', sans-serif; display: flex; flex-direction: column; position: relative; }
                .fm-container.kiosk { position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; z-index: 9999; border-radius: 0; margin: 0; }
                .fm-header { height: 64px; display: flex; justify-content: space-between; align-items: center; padding: 0 24px; background: var(--header-bg); border-bottom: 1px solid #222; }
                .fm-title { font-size: 1.2em; font-weight: 500; }
                .fm-toolbar { display: flex; gap: 12px; align-items: center; }
                .fm-btn { background: #2a2a2a; border: 1px solid #333; color: #ccc; padding: 8px 16px; border-radius: 6px; cursor: pointer; display: flex; align-items: center; gap: 8px; }
                .fm-btn.active { color: var(--primary-color); border-color: var(--primary-color); font-weight: bold; }
                .fm-main { display: flex; flex: 1; overflow: hidden; min-height: 0; }
                .fm-player-col { flex: 1; position: relative; background: #000; display: flex; flex-direction: column; align-items: stretch; justify-content: stretch; }
                .fm-player-body { flex: 1; position: relative; display: flex; align-items: center; justify-content: center; overflow: hidden; }
                #main-video { width: 100%; height: 100%; object-fit: contain; }
                #overlay-canvas { position: absolute; top: 0; left: 0; width: 100%; height: 100%; pointer-events: none; }
                .fm-overlay-tl { position: absolute; top: 20px; left: 20px; background: rgba(0,0,0,0.55); padding: 6px 14px; border-radius: 4px; color: #fff; font-size: 0.9em; font-weight: 600; pointer-events: none; }
                .fm-overlay-tr { position: absolute; top: 20px; right: 20px; background: rgba(0,0,0,0.35); padding: 6px 14px; border-radius: 4px; color: #ccc; font-size: 0.85em; pointer-events: none; }
                .fm-sidebar { width: 420px; flex-shrink: 0; background: #111; border-left: 1px solid #222; display: flex; flex-direction: column; }
                .fm-scroll { flex: 1; display: flex; overflow-y: auto; }
                .fm-list { flex: 1; min-width: 0; background: #0d0d0d; display: flex; flex-direction: column; }
                .fm-item { height: 160px; padding: 12px; cursor: pointer; border-bottom: 1px solid #333; position: relative; background: #111; }
                .fm-item:hover { background: #1f1f1f; }
                .fm-item.selected { border: 2.5px solid var(--primary-color); border-radius: 8px; background: #222; z-index: 10; margin: 4px; height: 152px; }
                .fm-thumb-wrap { width: 100%; height: 100%; border-radius: 6px; overflow: hidden; position: relative; background: #222; display: flex; align-items: center; justify-content: center; }
                .fm-thumb-img { width: 100%; height: 100%; object-fit: cover; opacity: 0.8; }
                /* REMOVED UPPERCASE HERE */
                .fm-badge-cam { position: absolute; bottom: 12px; left: 12px; background: rgba(0,0,0,0.7); padding: 4px 10px; border-radius: 4px; font-size: 0.7em; color: #fff; font-weight: 700; letter-spacing: 0.5px; text-transform: capitalize; }
                
                /* RULER RESTORED */
                .fm-ruler { width: 75px; flex-shrink: 0; background: #141414; border-right: 1px solid #222; position: relative; }
                .fm-tick { height: 160px; border-bottom: 1px solid #1a1a1a; position: relative; display: flex; justify-content: center; padding-top: 15px; }
                .fm-tick::after { content: ''; position: absolute; right: 0; top: 0; width: 12px; height: 1px; background: #444; }
                .fm-tick-label { color: #888; font-size: 0.75em; font-weight: 500; }
                
                /* Popups and Menu Styles */
                .fm-popup { position: absolute; top: 68px; right: 24px; background: #222; border: 1px solid #333; border-radius: 10px; display: none; min-width: 240px; z-index: 2000; box-shadow: 0 20px 60px rgba(0,0,0,0.8); }
                #pop-date { right: 140px; }
                .fm-popup-item { padding: 15px 20px; cursor: pointer; border-bottom: 1px solid #2a2a2a; color: #bbb; display: flex; align-items: center; gap: 12px; }
                .fm-popup-item:hover { background: #333; color: #fff; }
                .fm-popup-item.active { color: var(--primary-color); font-weight: bold; }
                .fm-menu-overlay { position: absolute; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.8); z-index: 3000; display: none; align-items: center; justify-content: center; }
                .fm-menu-overlay.open { display: flex; }
                .fm-menu-card { background: #1a1a1a; border: 1px solid #333; width: 600px; max-width: 90%; max-height: 85vh; border-radius: 16px; display: flex; flex-direction: column; overflow: hidden; }
                .fm-menu-header { padding: 20px; border-bottom: 1px solid #333; display: flex; justify-content: space-between; align-items: center; background: #222; }
                .fm-menu-title { font-size: 1.25em; font-weight: 500; color: #fff; }
                .fm-menu-close { cursor: pointer; color: #888; }
                .fm-tabs { display: flex; background: #111; border-bottom: 1px solid #333; }
                .fm-tab { flex: 1; text-align: center; padding: 16px; cursor: pointer; color: #888; border-bottom: 2px solid transparent; text-transform: uppercase; }
                .fm-tab.active { color: var(--primary-color); border-bottom-color: var(--primary-color); background: #1a1a1a; }
                .fm-tab.hidden { display: none; }
                .fm-menu-content { padding: 30px; min-height: 300px; overflow-y: auto; }
                
                /* Calendar */
                .fm-cal-header { display: flex; justify-content: space-between; align-items: center; padding: 10px 15px; border-bottom: 1px solid #333; background: #222; }
                .fm-cal-btn { background: #333; border: none; color: #fff; width: 30px; height: 30px; border-radius: 4px; cursor: pointer; }
                .fm-cal-grid { display: grid; grid-template-columns: repeat(7, 1fr); padding: 10px; gap: 4px; }
                .fm-cal-day { width: 32px; height: 32px; display: flex; align-items: center; justify-content: center; border-radius: 4px; cursor: pointer; color: #bbb; }
                .fm-cal-day.today { border: 1px solid var(--primary-color); }
                .fm-cal-day.selected { background: var(--primary-color); color: #fff; font-weight: bold; }
                .fm-btn-danger { background: rgba(244, 67, 54, 0.15) !important; color: #f44336 !important; border: 1px solid #f44336 !important; width: 100%; padding: 8px; border-radius: 4px; cursor: pointer; transition: 0.2s; }
                .fm-btn-danger:hover { background: #f44336 !important; color: #fff !important; }
                
                /* ========== ANIMATIONS ========== */
                /* Fade-in Animation for Items */
                @keyframes fadeInUp {
                    from { opacity: 0; transform: translateY(20px); }
                    to { opacity: 1; transform: translateY(0); }
                }
                @keyframes fadeIn {
                    from { opacity: 0; }
                    to { opacity: 1; }
                }
                @keyframes scaleIn {
                    from { opacity: 0; transform: scale(0.95); }
                    to { opacity: 1; transform: scale(1); }
                }
                @keyframes slideIn {
                    from { opacity: 0; transform: translateY(-20px); }
                    to { opacity: 1; transform: translateY(0); }
                }
                @keyframes pulse {
                    0%, 100% { transform: scale(1); }
                    50% { transform: scale(1.05); }
                }
                
                /* Animated states - only when animations enabled */
                .fm-container.animated .fm-item {
                    animation: fadeInUp 0.4s ease-out backwards;
                    transition: transform 0.2s ease, background 0.2s ease, box-shadow 0.2s ease;
                }
                .fm-container.animated .fm-item:hover .fm-thumb-wrap {
                    transform: scale(1.02);
                }
                .fm-container.animated .fm-thumb-wrap {
                    transition: transform 0.25s ease;
                }
                .fm-container.animated .fm-item.selected {
                    animation: pulse 0.3s ease;
                }
                .fm-container.animated #main-video {
                    transition: opacity 0.3s ease;
                }
                .fm-container.animated #main-video.loading {
                    opacity: 0.3;
                }
                .fm-container.animated .fm-menu-overlay {
                    transition: opacity 0.25s ease;
                    opacity: 0;
                }
                .fm-container.animated .fm-menu-overlay.open {
                    opacity: 1;
                }
                .fm-container.animated .fm-menu-card {
                    animation: scaleIn 0.3s ease-out;
                }
                .fm-container.animated .fm-popup {
                    animation: slideIn 0.2s ease-out;
                }
                .fm-container.animated .fm-cal-day {
                    transition: transform 0.15s ease, background 0.15s ease;
                }
                .fm-container.animated .fm-cal-day:hover {
                    transform: scale(1.15);
                }
                .fm-container.animated .fm-cal-day:active {
                    transform: scale(0.95);
                }
                .fm-container.animated .fm-btn {
                    transition: all 0.2s ease;
                }
                .fm-container.animated .fm-btn:hover {
                    transform: translateY(-1px);
                    box-shadow: 0 4px 12px rgba(0,0,0,0.3);
                }
                .fm-container.animated .fm-tick {
                    animation: fadeIn 0.3s ease-out backwards;
                }
                
                /* ========== VIDEO CONTROLS ========== */
                .fm-video-controls {
                    position: absolute;
                    bottom: 60px;
                    left: 20px;
                    display: flex;
                    gap: 8px;
                    z-index: 100;
                    opacity: 0;
                    transition: opacity 0.2s ease;
                }
                .fm-player-col:hover .fm-video-controls {
                    opacity: 1;
                }
                .fm-player-footer {
                    position: relative;
                    margin: 8px 16px 12px;
                    display: flex;
                    align-items: center;
                    justify-content: space-between;
                    gap: 12px;
                    background: rgba(0,0,0,0.55);
                    border: 1px solid #333;
                    border-radius: 8px;
                    padding: 8px 12px;
                    z-index: 110;
                    pointer-events: auto;
                }
                .fm-footer-left {
                    display: flex;
                    gap: 14px;
                    align-items: center;
                    flex-wrap: wrap;
                }
                .fm-footer-right {
                    display: flex;
                    gap: 8px;
                    align-items: center;
                    flex-wrap: wrap;
                }
                .fm-toggle {
                    display: flex;
                    align-items: center;
                    gap: 8px;
                    font-size: 0.85em;
                    color: #ddd;
                }
                .fm-perf-card {
                    background: #1b1b1b;
                    border: 1px solid #2a2a2a;
                    border-radius: 6px;
                    padding: 6px 10px;
                    min-width: 110px;
                }
                .fm-perf-label {
                    font-size: 0.75em;
                    color: #888;
                }
                .fm-perf-value {
                    font-size: 0.95em;
                    font-weight: 600;
                    color: var(--primary-color);
                }
                .fm-ctrl-btn {
                    background: rgba(0,0,0,0.7);
                    border: 1px solid #444;
                    color: #fff;
                    padding: 8px 12px;
                    border-radius: 6px;
                    cursor: pointer;
                    font-size: 0.85em;
                    display: flex;
                    align-items: center;
                    gap: 6px;
                    transition: all 0.2s ease;
                }
                .fm-ctrl-btn:hover {
                    background: rgba(3,169,244,0.3);
                    border-color: var(--primary-color);
                }
                .fm-ctrl-btn.active {
                    background: rgba(3,169,244,0.3);
                    border-color: var(--primary-color);
                }
                .fm-ctrl-btn.danger:hover {
                    background: rgba(244,67,54,0.3);
                    border-color: #f44336;
                }
                .fm-speed-btn {
                    min-width: 45px;
                    justify-content: center;
                }
                .fm-speed-btn.active {
                    background: var(--primary-color);
                    border-color: var(--primary-color);
                }
                
                /* ========== STORAGE INFO ========== */
                .fm-storage-bar {
                    height: 20px;
                    background: #333;
                    border-radius: 10px;
                    overflow: hidden;
                    margin: 15px 0;
                }
                .fm-storage-fill {
                    height: 100%;
                    background: linear-gradient(90deg, #4caf50, #8bc34a);
                    border-radius: 10px;
                    transition: width 0.5s ease;
                }
                .fm-storage-fill.warning {
                    background: linear-gradient(90deg, #ff9800, #ffc107);
                }
                .fm-storage-fill.danger {
                    background: linear-gradient(90deg, #f44336, #ff5722);
                }
                .fm-storage-stats {
                    display: grid;
                    grid-template-columns: 1fr 1fr;
                    gap: 15px;
                    margin-top: 20px;
                }
                .fm-stat-card {
                    background: #222;
                    padding: 15px;
                    border-radius: 8px;
                    text-align: center;
                }
                .fm-stat-value {
                    font-size: 1.5em;
                    font-weight: bold;
                    color: var(--primary-color);
                }
                .fm-stat-label {
                    font-size: 0.8em;
                    color: #888;
                    margin-top: 5px;
                }
                
                /* Delete Confirmation */
                .fm-confirm-overlay {
                    position: absolute;
                    top: 0;
                    left: 0;
                    width: 100%;
                    height: 100%;
                    background: rgba(0,0,0,0.9);
                    z-index: 4000;
                    display: none;
                    align-items: center;
                    justify-content: center;
                }
                .fm-confirm-overlay.open {
                    display: flex;
                }
                .fm-confirm-card {
                    background: #1a1a1a;
                    border: 1px solid #333;
                    padding: 30px;
                    border-radius: 12px;
                    text-align: center;
                    max-width: 400px;
                }
                .fm-confirm-btns {
                    display: flex;
                    gap: 15px;
                    margin-top: 25px;
                    justify-content: center;
                }
            </style>
            
            <div class="fm-container animated" id="container">
                <div class="fm-header">
                    <div class="fm-title">Kamera Archiv <span style="font-size:0.6em; opacity:0.5; margin-left:10px; border:1px solid #444; padding:2px 6px; border-radius:4px;">BETA v1.0.6</span></div>
                    <div class="fm-toolbar">
                        <button class="fm-btn active" id="btn-date">Letzte 24 Std</button>
                        <button class="fm-btn" id="btn-cams">Kameras</button>
                        <button class="fm-btn" id="btn-menu">Menue</button>
                    </div>
                </div>
                <div class="fm-main">
                    <div class="fm-player-col">
                        <div class="fm-player-body">
                            <div class="fm-overlay-tl" id="txt-cam">Waehle Aufnahme</div>
                            <div class="fm-overlay-tr" id="txt-date">BETA VERSION</div>
                            <video id="main-video" controls autoplay muted playsinline></video>
                            <canvas id="overlay-canvas"></canvas>
                        
                            <!-- Video Controls -->
                            <div class="fm-video-controls" id="video-controls">
                                <button class="fm-ctrl-btn" id="btn-download" title="Download">
                                    <svg width="16" height="16" fill="currentColor" viewBox="0 0 16 16"><path d="M.5 9.9a.5.5 0 0 1 .5.5v2.5a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-2.5a.5.5 0 0 1 1 0v2.5a2 2 0 0 1-2 2H2a2 2 0 0 1-2-2v-2.5a.5.5 0 0 1 .5-.5z"/><path d="M7.646 11.854a.5.5 0 0 0 .708 0l3-3a.5.5 0 0 0-.708-.708L8.5 10.293V1.5a.5.5 0 0 0-1 0v8.793L5.354 8.146a.5.5 0 1 0-.708.708l3 3z"/></svg>
                                    Download
                                </button>
                                <button class="fm-ctrl-btn danger" id="btn-delete" title="Loeschen">
                                    <svg width="16" height="16" fill="currentColor" viewBox="0 0 16 16"><path d="M5.5 5.5A.5.5 0 0 1 6 6v6a.5.5 0 0 1-1 0V6a.5.5 0 0 1 .5-.5zm2.5 0a.5.5 0 0 1 .5.5v6a.5.5 0 0 1-1 0V6a.5.5 0 0 1 .5-.5zm3 .5a.5.5 0 0 0-1 0v6a.5.5 0 0 0 1 0V6z"/><path fill-rule="evenodd" d="M14.5 3a1 1 0 0 1-1 1H13v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V4h-.5a1 1 0 0 1-1-1V2a1 1 0 0 1 1-1H6a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1h3.5a1 1 0 0 1 1 1v1zM4.118 4 4 4.059V13a1 1 0 0 0 1 1h6a1 1 0 0 0 1-1V4.059L11.882 4H4.118zM2.5 3V2h11v1h-11z"/></svg>
                                    Loeschen
                                </button>
                                <button class="fm-ctrl-btn" id="btn-overlay" title="Overlay">
                                    <svg width="16" height="16" fill="currentColor" viewBox="0 0 16 16"><path d="M8 3C4.5 3 1.73 5.11.46 8c1.27 2.89 4.04 5 7.54 5s6.27-2.11 7.54-5C14.27 5.11 11.5 3 8 3zm0 8.5A3.5 3.5 0 1 1 8 4.5a3.5 3.5 0 0 1 0 7z"/><path d="M8 6.5A1.5 1.5 0 1 0 8 9.5a1.5 1.5 0 0 0 0-3z"/></svg>
                                    Overlay
                                </button>
                                <div style="border-left: 1px solid #444; margin: 0 5px;"></div>
                                <button class="fm-ctrl-btn fm-speed-btn" data-speed="0.5">0.5x</button>
                                <button class="fm-ctrl-btn fm-speed-btn active" data-speed="1">1x</button>
                                <button class="fm-ctrl-btn fm-speed-btn" data-speed="2">2x</button>
                            </div>
                        </div>
                        <div class="fm-player-footer" id="player-footer">
                            <div class="fm-footer-left">
                                <label class="fm-toggle">
                                    <input id="footer-overlay" type="checkbox" ${this._overlayEnabled ? 'checked' : ''} />
                                    <span>Objekte im Video</span>
                                </label>
                                <label class="fm-toggle">
                                    <input id="footer-perf" type="checkbox" ${this._showPerfPanel ? 'checked' : ''} />
                                    <span>Leistung anzeigen</span>
                                </label>
                            </div>
                            <div class="fm-footer-right" id="footer-perf-panel"></div>
                        </div>
                    </div>
                    <div class="fm-sidebar">
                        <div class="fm-scroll">
                            <div class="fm-ruler" id="ruler"></div>
                            <div class="fm-list" id="list"><div style="padding:20px; color:#888;">Lade Aufnahmen...</div></div>
                        </div>
                    </div>
                </div>
                
                <!-- Popups -->
                <div class="fm-popup" id="pop-cam"></div>
                <div class="fm-popup" id="pop-date">
                    <div class="fm-cal-header"><button class="fm-cal-btn" id="cal-prev">&lt;</button><span id="cal-month-year"></span><button class="fm-cal-btn" id="cal-next">&gt;</button></div>
                    <div class="fm-cal-grid" id="cal-grid"></div>
                    <div style="padding: 10px; border-top: 1px solid #333; text-align: center;"><button id="btn-clear-date" class="fm-btn-danger">Filter Leeren</button></div>
                </div>
                
                <!-- Menu -->
                <div class="fm-menu-overlay" id="menu-overlay">
                    <div class="fm-menu-card">
                        <div class="fm-menu-header"><div class="fm-menu-title">Einstellungen</div><div class="fm-menu-close" id="menu-close">X</div></div>
                        <div class="fm-tabs">
                            <div class="fm-tab active" data-tab="general">Allgemein</div>
                            <div class="fm-tab" data-tab="storage">Speicher</div>
                            <div class="fm-tab" data-tab="analysis">Analyse</div>
                            <div class="fm-tab ${this._showPerfTab ? '' : 'hidden'}" data-tab="performance">Leistung</div>
                        </div>
                        <div class="fm-menu-content" id="menu-content"></div>
                    </div>
                </div>
                
                <!-- Delete Confirmation -->
                <div class="fm-confirm-overlay" id="confirm-overlay">
                    <div class="fm-confirm-card">
                        <div style="font-size:2em;margin-bottom:15px;">!</div>
                        <div style="font-size:1.1em;font-weight:500;">Aufnahme loeschen?</div>
                        <div style="color:#888;margin-top:10px;" id="confirm-filename"></div>
                        <div class="fm-confirm-btns">
                            <button class="fm-btn" id="confirm-cancel">Abbrechen</button>
                            <button class="fm-btn-danger" id="confirm-delete" style="padding:10px 20px;">Endgueltig loeschen</button>
                        </div>
                    </div>
                </div>
            </div>
        `;

        this.setupListeners();
        this.updateFooterVisibility();
    }

    setupListeners() {
        const root = this.shadowRoot;
        root.querySelector('#btn-date').onclick = (e) => { e.stopPropagation(); this.togglePopup('pop-date'); };
        root.querySelector('#btn-cams').onclick = (e) => { e.stopPropagation(); this.togglePopup('pop-cam'); };
        root.querySelector('#btn-menu').onclick = () => { this.openMenu(); };
        root.querySelector('#menu-close').onclick = () => { this.closeMenu(); };
        root.querySelector('#menu-overlay').onclick = (e) => { if (e.target === root.querySelector('#menu-overlay')) this.closeMenu(); };

        // Video Controls
        root.querySelector('#btn-download').onclick = () => { this.downloadCurrentVideo(); };
        root.querySelector('#btn-delete').onclick = () => { this.showDeleteConfirm(); };
        const overlayBtn = root.querySelector('#btn-overlay');
        if (overlayBtn) {
            overlayBtn.onclick = () => {
                this._overlayEnabled = !this._overlayEnabled;
                this.updateOverlayStates();
                if (this._overlayEnabled) {
                    this.loadDetectionsForCurrentVideo();
                } else {
                    this.clearOverlay();
                }
            };
        }
        root.querySelector('#confirm-cancel').onclick = () => { this.hideDeleteConfirm(); };
        root.querySelector('#confirm-delete').onclick = () => { this.deleteCurrentVideo(); };
        root.querySelector('#confirm-overlay').onclick = (e) => { if (e.target === root.querySelector('#confirm-overlay')) this.hideDeleteConfirm(); };
        
        // Speed Controls
        root.querySelectorAll('.fm-speed-btn').forEach(btn => {
            btn.onclick = () => {
                const speed = parseFloat(btn.dataset.speed);
                root.querySelector('#main-video').playbackRate = speed;
                root.querySelectorAll('.fm-speed-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
            };
        });

        root.querySelectorAll('.fm-tab').forEach(t => {
            t.onclick = () => {
                root.querySelectorAll('.fm-tab').forEach(x => x.classList.remove('active'));
                t.classList.add('active');
                this._activeTab = t.dataset.tab;
                this.renderMenuContent();
                if (this._activeTab === "analysis" || this._activeTab === "performance") {
                    this.startStatsPolling();
                    this.refreshAnalysisOverview();
                }
            }
        });

        root.querySelector('#cal-prev').onclick = (e) => { e.stopPropagation(); this._calMonth--; if (this._calMonth < 0) { this._calMonth = 11; this._calYear--; } this.renderCalendar(); };
        root.querySelector('#cal-next').onclick = (e) => { e.stopPropagation(); this._calMonth++; if (this._calMonth > 11) { this._calMonth = 0; this._calYear++; } this.renderCalendar(); };
        root.querySelector('#btn-clear-date').onclick = () => { this._selectedDate = null; this.updateDateLabel(); this.togglePopup(); this.renderCalendar(); };

        this.onclick = () => { this.togglePopup(); };

        const video = root.querySelector('#main-video');
        if (video) {
            video.addEventListener('timeupdate', () => this.drawOverlay());
            video.addEventListener('loadedmetadata', () => this.resizeOverlay());
        }

        const footerOverlay = root.querySelector('#footer-overlay');
        if (footerOverlay) {
            footerOverlay.onchange = () => {
                this._overlayEnabled = footerOverlay.checked;
                this.updateOverlayStates();
                if (this._overlayEnabled) {
                    this.loadDetectionsForCurrentVideo();
                } else {
                    this.clearOverlay();
                }
            };
        }

        const footerPerf = root.querySelector('#footer-perf');
        if (footerPerf) {
            footerPerf.onchange = () => {
                this._showPerfPanel = footerPerf.checked;
                this.updatePerfFooter();
            };
        }

        this.updateOverlayStates();
        this.updatePerfFooter();
    }

    togglePopup(id) {
        const root = this.shadowRoot;
        ['pop-cam', 'pop-date'].forEach(pid => {
            const el = root.querySelector('#' + pid);
            if (el) el.style.display = (pid === id && el.style.display !== 'block') ? 'block' : 'none';
        });
        if (id === 'pop-cam') {
            const container = root.querySelector('#pop-cam');
            // DYNAMIC CAMERA LIST
            let cams = ['Alle'];
            if (this._events) {
                const unique = [...new Set(this._events.map(e => e.cam))].sort();
                cams = cams.concat(unique);
            }

            container.innerHTML = cams.map(c => {
                const displayName = c === 'Alle' ? 'Alle' : c.replace(/_/g, ' ');
                return `<div class="fm-popup-item ${this._selectedCam === c ? 'active' : ''}" id="cam-${c}">${displayName}</div>`;
            }).join('');

            cams.forEach(c => {
                const el = container.querySelector('#cam-' + c.replace(/ /g, '\\ ').replace(/\(/g, '\\(').replace(/\)/g, '\\)'));
                if (el) el.onclick = () => { this._selectedCam = c; this.updateView(); this.togglePopup(); };
            });
        }
    }

    updateDateLabel() {
        const btn = this.shadowRoot.querySelector('#btn-date');
        if (this._selectedDate) { btn.classList.remove('active'); btn.innerText = `Datum: ${this._selectedDate}`; }
        else { btn.classList.add('active'); btn.innerText = 'Letzte 24 Std'; }
        this.updateView();
    }

    openMenu() {
        this.shadowRoot.querySelector('#menu-overlay').classList.add('open');
        this.renderMenuContent();
        if (this._activeTab === "analysis" || this._activeTab === "performance") {
            this.startStatsPolling();
            this.refreshAnalysisOverview();
        }
    }
    closeMenu() { this.shadowRoot.querySelector('#menu-overlay').classList.remove('open'); }

    renderMenuContent() {
        const container = this.shadowRoot.querySelector('#menu-content');
        const perfTab = this.shadowRoot.querySelector('.fm-tab[data-tab="performance"]');
        if (perfTab) {
            perfTab.classList.toggle('hidden', !this._showPerfTab);
        }
        if (!this._showPerfTab && this._activeTab === 'performance') {
            this._activeTab = 'general';
        }
        this.shadowRoot.querySelectorAll('.fm-tab').forEach(t => {
            t.classList.toggle('active', t.dataset.tab === this._activeTab);
        });
        if (this._activeTab === 'general') {
            container.innerHTML = `
                <div style="padding:10px;">
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:20px;padding-bottom:15px;border-bottom:1px solid #333;">
                        <div>
                            <span style="font-weight:500;">Kiosk Modus</span>
                            <div style="font-size:0.8em;color:#888;margin-top:4px;">Vollbild ohne Browser-UI</div>
                        </div>
                        <input type="checkbox" id="chk-kiosk" ${this._kioskActive ? 'checked' : ''} style="transform:scale(1.3);cursor:pointer;">
                    </div>
                    <div style="display:flex;justify-content:space-between;align-items:center;">
                        <div>
                            <span style="font-weight:500;">Animationen</span>
                            <div style="font-size:0.8em;color:#888;margin-top:4px;">Sanfte Uebergaenge und Hover-Effekte</div>
                        </div>
                        <input type="checkbox" id="chk-animations" ${this._animationsEnabled ? 'checked' : ''} style="transform:scale(1.3);cursor:pointer;">
                    </div>
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-top:20px;padding-top:15px;border-top:1px solid #333;">
                        <div>
                            <span style="font-weight:500;">Footer anzeigen</span>
                            <div style="font-size:0.8em;color:#888;margin-top:4px;">Zeigt die Footer-Leiste unter dem Video</div>
                        </div>
                        <input type="checkbox" id="chk-footer" ${this._showFooter ? 'checked' : ''} style="transform:scale(1.3);cursor:pointer;">
                    </div>
                </div>
            `;
            container.querySelector('#chk-kiosk').onchange = () => {
                this._kioskActive = !this._kioskActive;
                this.shadowRoot.querySelector('#container').classList.toggle('kiosk', this._kioskActive);
            };
            container.querySelector('#chk-animations').onchange = () => {
                this._animationsEnabled = !this._animationsEnabled;
                this.shadowRoot.querySelector('#container').classList.toggle('animated', this._animationsEnabled);
            };
            container.querySelector('#chk-footer').onchange = () => {
                this._showFooter = !this._showFooter;
                this.updateFooterVisibility();
                this.saveLocalSettings();
            };
        } else if (this._activeTab === 'storage') {
            // Storage Tab
            this.renderStorageTab(container);
        } else if (this._activeTab === 'performance') {
            this.renderPerformanceTab(container);
        } else {
            // Analysis Tab
            this.renderAnalysisTab(container);
        }
    }

    updateFooterVisibility() {
        const footer = this.shadowRoot.querySelector('#player-footer');
        if (!footer) return;
        footer.style.display = this._showFooter ? 'flex' : 'none';
    }

    loadLocalSettings() {
        try {
            const raw = localStorage.getItem(this._settingsKey);
            if (!raw) return;
            const data = JSON.parse(raw);
            if (typeof data.showFooter === 'boolean') {
                this._showFooter = data.showFooter;
            }
        } catch (e) {
            // ignore
        }
    }

    saveLocalSettings() {
        try {
            const data = {
                showFooter: this._showFooter,
            };
            localStorage.setItem(this._settingsKey, JSON.stringify(data));
        } catch (e) {
            // ignore
        }
    }

    renderPerformanceTab(container) {
        const live = this._liveStats || {};
        const stats = this._detectorStats || {};
        const tracker = stats.inference_stats || {};
        const devices = stats.devices || [];
        const hasCoralUsb = devices.includes('coral_usb');
        const history = this._statsHistory || [];

        // Helper for gauge-style cards
        const gaugeCard = (label, value, unit, color, max = 100) => {
            const pct = Math.min(100, Math.max(0, (value / max) * 100));
            return `
                <div style="background:#1a1a1a; border:1px solid #333; border-radius:12px; padding:16px; min-width:160px; flex:1;">
                    <div style="font-size:0.85em; color:#888; margin-bottom:8px;">${label}</div>
                    <div style="font-size:1.8em; font-weight:600; color:${color}; margin-bottom:10px;">${value}${unit}</div>
                    <div style="background:#333; height:6px; border-radius:3px; overflow:hidden;">
                        <div style="background:${color}; height:100%; width:${pct}%; transition:width 0.3s;"></div>
                    </div>
                </div>
            `;
        };

        // System stats
        const cpu = live.cpu?.state ?? 0;
        const cpuColor = cpu > 80 ? '#f44336' : cpu > 50 ? '#ff9800' : '#4caf50';
        const mem = live.memory?.state ?? 0;
        const memColor = mem > 80 ? '#f44336' : mem > 60 ? '#ff9800' : '#4caf50';

        // Coral stats
        const coralPct = tracker.recent_coral_pct ?? 0;
        const coralActive = tracker.last_device === 'coral_usb';
        const lastDevice = tracker.last_device || 'keine';
        const avgMs = tracker.avg_inference_ms || 0;
        const totalInf = tracker.total_inferences || 0;
        const hasInf = totalInf > 0;
        const coralColor = hasInf
            ? (coralPct > 50 ? '#4caf50' : coralPct > 0 ? '#ff9800' : '#666')
            : '#666';
        const coralDisplay = hasInf ? `${coralPct}%` : '-';
        // Device display
        const deviceDisplay = hasInf ? (lastDevice === 'coral_usb' ? 'Coral USB' : 'CPU') : '-';
        const deviceColor = hasInf ? (lastDevice === 'coral_usb' ? '#4caf50' : '#ff9800') : '#666';

        // Mini sparkline from history
        let sparklineSvg = '';
        if (history.length > 1) {
            const w = 200, h = 40;
            const maxCpu = Math.max(...history.map(h => h.cpu), 1);
            const points = history.map((h, i) => {
                const x = (i / (history.length - 1)) * w;
                const y = h - (h.cpu / maxCpu) * (h - 5);
                return `${x},${y}`;
            }).join(' ');
            sparklineSvg = `
                <svg width="${w}" height="${h}" style="display:block;">
                    <polyline points="${points}" fill="none" stroke="#03a9f4" stroke-width="2"/>
                </svg>
            `;
        }

        container.innerHTML = `
            <div style="padding:15px;">
                <!-- Live System Stats -->
                <div style="margin-bottom:20px;">
                    <div style="font-weight:500; margin-bottom:12px; display:flex; align-items:center; gap:8px;">
                        <span style="color:#4caf50;">OK</span> Live System
                    </div>
                    <div style="display:flex; gap:12px; flex-wrap:wrap;">
                        ${gaugeCard('CPU Auslastung', cpu.toFixed(1), '%', cpuColor)}
                        ${gaugeCard('RAM Auslastung', mem.toFixed(1), '%', memColor)}
                    </div>
                </div>

                <!-- Detector Stats -->
                <div style="margin-bottom:20px; padding-top:15px; border-top:1px solid #333;">
                    <div style="font-weight:500; margin-bottom:12px;">Objekt-Erkennung</div>
                    <div style="display:flex; gap:12px; flex-wrap:wrap;">
                        <div style="background:#1a1a1a; border:1px solid #333; border-radius:12px; padding:16px; min-width:160px; flex:1;">
                            <div style="font-size:0.85em; color:#888; margin-bottom:8px;">Coral USB</div>
                            <div style="font-size:1.4em; font-weight:600; color:${hasCoralUsb ? (coralActive ? '#4caf50' : '#ff9800') : '#666'};">
                                ${hasCoralUsb ? (coralActive ? 'Aktiv' : 'Bereit') : 'Nicht verbunden'}
                            </div>
                        </div>
                        <div style="background:#1a1a1a; border:1px solid #333; border-radius:12px; padding:16px; min-width:160px; flex:1;">
                            <div style="font-size:0.85em; color:#888; margin-bottom:8px;">Letztes Device</div>
                            <div style="font-size:1.4em; font-weight:600; color:${deviceColor};">
                                ${deviceDisplay}
                            </div>
                        </div>
                        ${hasCoralUsb ? `
                            <div style="background:#1a1a1a; border:1px solid #333; border-radius:12px; padding:16px; min-width:160px; flex:1;">
                                <div style="font-size:0.85em; color:#888; margin-bottom:8px;">Coral Nutzung</div>
                                <div style="font-size:1.8em; font-weight:600; color:${coralColor};">
                                    ${coralDisplay}
                                </div>
                            </div>
                        ` : ''}
                        <div style="background:#1a1a1a; border:1px solid #333; border-radius:12px; padding:16px; min-width:160px; flex:1;">
                            <div style="font-size:0.85em; color:#888; margin-bottom:8px;">Inferenzzeit</div>
                            <div style="font-size:1.8em; font-weight:600; color:#03a9f4;">
                                ${avgMs > 0 ? avgMs.toFixed(0) + 'ms' : '-'}
                            </div>
                        </div>
                        <div style="background:#1a1a1a; border:1px solid #333; border-radius:12px; padding:16px; min-width:160px; flex:1;">
                            <div style="font-size:0.85em; color:#888; margin-bottom:8px;">Inferenzen gesamt</div>
                            <div style="font-size:1.8em; font-weight:600; color:#03a9f4;">${totalInf}</div>
                        </div>
                    </div>
                    ${!hasInf ? `
                        <div style="margin-top:10px; color:#888; font-size:0.9em;">
                            Coral-Nutzung wird nur bei aktiver Live-Erkennung oder neuer Videoanalyse gezaehlt.
                        </div>
                    ` : ''}
                    <div style="margin-top:12px;">
                        <button id="test-inference-btn" style="background:#03a9f4; color:#fff; border:none; padding:10px 20px; border-radius:6px; cursor:pointer; font-size:0.95em;">
                            Test-Inferenz starten
                        </button>
                        <span id="test-inference-status" style="margin-left:10px; color:#888; font-size:0.9em;"></span>
                    </div>
                </div>

                <!-- CPU History Graph -->
                ${history.length > 5 ? `
                    <div style="padding-top:15px; border-top:1px solid #333;">
                        <div style="font-weight:500; margin-bottom:12px;">CPU Verlauf (letzte ${history.length} Messungen)</div>
                        <div style="background:#1a1a1a; border:1px solid #333; border-radius:8px; padding:10px;">
                            ${sparklineSvg}
                        </div>
                    </div>
                ` : `
                    <div style="padding-top:15px; border-top:1px solid #333; color:#666; font-size:0.9em;">
                        CPU Verlauf wird nach einigen Messungen angezeigt...
                    </div>
                `}

                <!-- Info -->
                <div style="margin-top:20px; padding:12px; background:#222; border-radius:8px; color:#888; font-size:0.85em;">
                    <strong>Hinweis:</strong> Die Statistiken werden alle 5 Sekunden aktualisiert. 
                    Die Coral-Nutzung zeigt den Anteil der Inferenzen, die auf dem Coral USB Accelerator ausgefuehrt wurden.
                </div>
            </div>
        `;
        
        // Attach test inference button handler
        setTimeout(() => {
            const btn = this.shadowRoot.querySelector('#test-inference-btn');
            if (btn) {
                btn.onclick = () => this.runTestInference();
            }
        }, 50);
    }

    async runTestInference() {
        const btn = this.shadowRoot.querySelector('#test-inference-btn');
        const status = this.shadowRoot.querySelector('#test-inference-status');
        if (btn) btn.disabled = true;
        if (status) status.textContent = 'Laeuft...';
        
        try {
            const result = await this._hass.callWS({ type: 'rtsp_recorder/test_inference' });
            console.log('[RTSP-Recorder] Test Inference Result:', result);
            if (result.success) {
                if (status) status.innerHTML = `<span style="color:#4caf50;">✓ ${result.device} (${result.duration_ms}ms)</span>`;
                // Refresh stats after successful test
                await this.fetchDetectorStats();
            } else {
                if (status) status.innerHTML = `<span style="color:#f44336;">Fehler: ${result.message}</span>`;
            }
        } catch (e) {
            console.error('[RTSP-Recorder] Test inference failed:', e);
            if (status) status.innerHTML = `<span style="color:#f44336;">Fehler: ${e.message || e}</span>`;
        }
        
        if (btn) btn.disabled = false;
    }

    renderAnalysisTab(container) {
        const deviceOptions = (this._analysisDeviceOptions && this._analysisDeviceOptions.length)
            ? this._analysisDeviceOptions
            : [
                { value: 'cpu', label: 'CPU' }
            ];

        const objectCheckboxes = this._analysisObjects.map(obj => {
            const checked = this._analysisSelected.has(obj) ? 'checked' : '';
            return `
                <label style="display:flex;align-items:center;gap:8px;padding:6px 0;">
                    <input type="checkbox" class="fm-obj" value="${obj}" ${checked} />
                    <span>${obj}</span>
                </label>
            `;
        }).join('');

        const deviceSelect = deviceOptions.map(d => {
            const selected = this._analysisDevice === d.value ? 'selected' : '';
            return `<option value="${d.value}" ${selected}>${d.label}</option>`;
        }).join('');

        const overview = this._analysisOverview || { items: [], stats: {} };
        const items = overview.items || [];
        const stats = overview.stats || {};
        const perf = this._perfSensors || {};
                const perfCard = (label, sensor) => {
                    if (!sensor) {
                        return `
                            <div style="background:#222; padding:10px 12px; border-radius:8px; min-width:140px;">
                                <div style="font-size:0.9em; color:#888;">${label}</div>
                                <div style="font-size:1.1em; font-weight:600; color:#666;">n/a</div>
                            </div>
                        `;
                    }
                    const value = sensor.state ?? 'n/a';
                    const unit = sensor.unit ? ` ${sensor.unit}` : '';
                    const name = sensor.name || label;
                    return `
                        <div style="background:#222; padding:10px 12px; border-radius:8px; min-width:140px;">
                            <div style="font-size:0.8em; color:#888;">${name}</div>
                            <div style="font-size:1.1em; font-weight:600; color:var(--primary-color);">${value}${unit}</div>
                        </div>
                    `;
                };
        const byDevice = stats.by_device || {};
        const deviceBreakdown = Object.entries(byDevice)
            .sort((a, b) => b[1] - a[1])
            .map(([dev, count]) => `
                <div style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid #333;">
                    <span>${dev}</span>
                    <span style="color:var(--primary-color);font-weight:500;">${count}</span>
                </div>
            `).join('');

        const itemsHtml = items.slice(0, 10).map(item => {
            const name = (item.video_path || '').split('/').pop() || 'unknown';
            const created = item.created_utc || '';
            const device = item.device || 'cpu';
            const duration = item.duration_sec ? `${item.duration_sec}s` : '';
            return `
                <div style="padding:8px 0;border-bottom:1px solid #333;">
                    <div style="font-weight:500;">${name}</div>
                    <div style="font-size:0.8em;color:#888;">${created} · ${device} ${duration ? '· ' + duration : ''}</div>
                </div>
            `;
        }).join('');

        const historyHtml = items.slice(0, 20).map(item => {
            const created = item.created_utc || '';
            const device = item.device || 'cpu';
            const perf = item.perf_snapshot || {};
            const cpu = perf.cpu && perf.cpu.state != null ? `${perf.cpu.state}${perf.cpu.unit || ''}` : 'n/a';
            const igpu = perf.igpu && perf.igpu.state != null ? `${perf.igpu.state}${perf.igpu.unit || ''}` : 'n/a';
            const coral = perf.coral && perf.coral.state != null ? `${perf.coral.state}${perf.coral.unit || ''}` : 'n/a';
            return `
                <div style="display:flex; justify-content:space-between; gap:10px; padding:6px 0; border-bottom:1px solid #333;">
                    <div style="min-width:120px; color:#aaa;">${created}</div>
                    <div style="flex:1;">${device}</div>
                    <div style="display:flex; gap:10px; color:#888; font-size:0.85em;">
                        <span>CPU ${cpu}</span>
                        <span>iGPU ${igpu}</span>
                        <span>Coral ${coral}</span>
                    </div>
                </div>
            `;
        }).join('');

        const overviewHtml = this._analysisLoading
            ? '<div style="color:#888;">Lade Analyseuebersicht...</div>'
            : (items.length ? itemsHtml : '<div style="color:#888;">Keine Analysen gefunden</div>');

        container.innerHTML = `
            <div style="padding:10px;">
                <div style="margin-bottom:15px; font-weight:500;">Objekte auswaehlen</div>
                <div style="max-height:180px; overflow:auto; border:1px solid #333; border-radius:8px; padding:10px;">
                    ${objectCheckboxes}
                </div>
                <div style="margin-top:15px;">
                    <div style="margin-bottom:6px; font-weight:500;">Hardware</div>
                    <select id="analysis-device" style="width:100%; padding:8px; background:#222; color:#eee; border:1px solid #333; border-radius:6px;">
                        ${deviceSelect}
                    </select>
                </div>
                <button class="fm-btn" id="btn-analyze" style="margin-top:20px; width:100%; justify-content:center;">
                    🔍 Analyse aktuelle Aufnahme
                </button>
                <label style="display:flex;align-items:center;gap:8px;margin-top:12px;">
                    <input id="analysis-overlay" type="checkbox" ${this._overlayEnabled ? 'checked' : ''} />
                    <span>Objekte im Video anzeigen</span>
                </label>
                <div style="margin-top:20px; border-top:1px solid #333; padding-top:15px;">
                    <div style="font-weight:500; margin-bottom:10px;">Alle Aufnahmen analysieren</div>
                    <div style="display:grid; grid-template-columns:1fr 1fr; gap:10px;">
                        <label style="display:flex;flex-direction:column;gap:6px;">
                            <span style="font-size:0.8em;color:#888;">Zeitraum (Tage)</span>
                            <input id="analysis-days" type="number" min="0" value="1" style="padding:8px; background:#222; color:#eee; border:1px solid #333; border-radius:6px;" />
                        </label>
                        <label style="display:flex;flex-direction:column;gap:6px;">
                            <span style="font-size:0.8em;color:#888;">Limit</span>
                            <input id="analysis-limit" type="number" min="0" value="50" style="padding:8px; background:#222; color:#eee; border:1px solid #333; border-radius:6px;" />
                        </label>
                    </div>
                    <label style="display:flex;align-items:center;gap:8px;margin-top:10px;">
                        <input id="analysis-skip" type="checkbox" checked />
                        <span>Nur neue Dateien</span>
                    </label>
                    <button class="fm-btn" id="btn-analyze-all" style="margin-top:12px; width:100%; justify-content:center;">
                        Alle Aufnahmen analysieren
                    </button>
                </div>
                <div style="margin-top:20px; border-top:1px solid #333; padding-top:15px;">
                    <div style="font-weight:500; margin-bottom:10px;">Analyseuebersicht</div>
                    ${overviewHtml}
                </div>
                <div style="margin-top:20px; border-top:1px solid #333; padding-top:15px;">
                    <div style="font-weight:500; margin-bottom:10px;">Verlauf (Geraet & Leistung)</div>
                    ${this._analysisLoading ? '<div style="color:#888;">Lade Verlauf...</div>' : (historyHtml || '<div style="color:#888;">Keine Daten</div>')}
                </div>
                <div style="margin-top:20px; border-top:1px solid #333; padding-top:15px;">
                    <div style="font-weight:500; margin-bottom:10px;">Leistungsuebersicht</div>
                    <div style="display:flex; gap:10px; flex-wrap:wrap;">
                        <div style="background:#222; padding:10px 12px; border-radius:8px; min-width:120px;">
                            <div style="font-size:1.2em; font-weight:600; color:var(--primary-color);">${stats.total || 0}</div>
                            <div style="font-size:0.75em;color:#888;">Analysen</div>
                        </div>
                        <div style="background:#222; padding:10px 12px; border-radius:8px; min-width:120px;">
                            <div style="font-size:1.2em; font-weight:600; color:var(--primary-color);">${stats.avg_duration_sec || 0}s</div>
                            <div style="font-size:0.75em;color:#888;">Dauer</div>
                        </div>
                        <div style="background:#222; padding:10px 12px; border-radius:8px; min-width:120px;">
                            <div style="font-size:1.2em; font-weight:600; color:var(--primary-color);">${stats.avg_frame_count || 0}</div>
                            <div style="font-size:0.75em;color:#888;">Frames</div>
                        </div>
                    </div>
                    <div style="margin-top:12px; display:flex; gap:10px; flex-wrap:wrap;">
                        ${perfCard('CPU', perf.cpu)}
                        ${perfCard('iGPU', perf.igpu)}
                        ${perfCard('Coral', perf.coral)}
                    </div>
                    <div style="margin-top:12px;">
                        <div style="font-size:0.8em;color:#888;margin-bottom:6px;">Geraete-Nutzung</div>
                        ${deviceBreakdown || '<div style="color:#888;">Keine Daten</div>'}
                    </div>
                </div>
            </div>
        `;

        container.querySelectorAll('.fm-obj').forEach(cb => {
            cb.onchange = () => {
                const value = cb.value;
                if (cb.checked) this._analysisSelected.add(value);
                else this._analysisSelected.delete(value);
            };
        });

        container.querySelector('#analysis-device').onchange = (e) => {
            this._analysisDevice = e.target.value;
        };

        container.querySelector('#btn-analyze').onclick = () => {
            this.analyzeCurrentVideo();
        };

        const overlayToggle = container.querySelector('#analysis-overlay');
        if (overlayToggle) {
            overlayToggle.onchange = () => {
                this._overlayEnabled = overlayToggle.checked;
                this.updateOverlayStates();
                if (this._overlayEnabled) {
                    this.loadDetectionsForCurrentVideo();
                } else {
                    this.clearOverlay();
                }
            };
        }

        container.querySelector('#btn-analyze-all').onclick = () => {
            this.analyzeAllRecordings();
        };
    }

    async analyzeCurrentVideo() {
        if (!this._currentEvent) {
            this.showToast('Bitte zuerst eine Aufnahme auswaehlen', 'warning');
            return;
        }

        const objects = Array.from(this._analysisSelected);
        if (objects.length === 0) {
            this.showToast('Bitte mindestens ein Objekt auswaehlen', 'warning');
            return;
        }

        try {
            await this._hass.callService('rtsp_recorder', 'analyze_recording', {
                media_id: this._currentEvent.id,
                objects,
                device: this._analysisDevice
            });
            this.showToast('Analyse gestartet', 'success');
        } catch (e) {
            this.showToast('Analyse fehlgeschlagen: ' + e.message, 'error');
        }
    }

    async analyzeAllRecordings() {
        const root = this.shadowRoot;
        const daysEl = root.querySelector('#analysis-days');
        const limitEl = root.querySelector('#analysis-limit');
        const skipEl = root.querySelector('#analysis-skip');

        const since_days = daysEl ? parseInt(daysEl.value || '0', 10) : 0;
        const limit = limitEl ? parseInt(limitEl.value || '0', 10) : 0;
        const skip_existing = skipEl ? skipEl.checked : true;
        const objects = Array.from(this._analysisSelected);

        if (objects.length === 0) {
            this.showToast('Bitte mindestens ein Objekt auswaehlen', 'warning');
            return;
        }

        try {
            await this._hass.callService('rtsp_recorder', 'analyze_all_recordings', {
                since_days,
                limit,
                skip_existing,
                objects,
                device: this._analysisDevice
            });
            this.showToast('Analyse fuer alle Aufnahmen gestartet', 'success');
        } catch (e) {
            this.showToast('Analyse fehlgeschlagen: ' + e.message, 'error');
        }
    }

    async refreshAnalysisOverview() {
        if (this._analysisLoading) return;
        this._analysisLoading = true;
        try {
            const data = await this._hass.callWS({
                type: 'rtsp_recorder/get_analysis_overview',
                limit: 20
            });
            this._analysisOverview = data || { items: [], stats: {} };
            this._perfSensors = (data && data.perf) ? data.perf : { cpu: null, igpu: null, coral: null };
            this.updatePerfFooter();
            this._analysisDeviceOptions = (data && data.devices)
                ? data.devices.map(d => ({ value: d, label: d === 'coral_usb' ? 'Coral USB' : d.toUpperCase() }))
                : null;
            if (this._analysisDeviceOptions && this._analysisDeviceOptions.length) {
                const values = this._analysisDeviceOptions.map(o => o.value);
                if (!values.includes(this._analysisDevice)) {
                    this._analysisDevice = values[0];
                }
            }
            this._analysisOverviewLoaded = true;
        } catch (e) {
            this._analysisOverview = { items: [], stats: {} };
        } finally {
            this._analysisLoading = false;
            if (this._activeTab === 'analysis') {
                this.renderAnalysisTab(this.shadowRoot.querySelector('#menu-content'));
            } else if (this._activeTab === 'performance') {
                this.renderPerformanceTab(this.shadowRoot.querySelector('#menu-content'));
            }
        }
    }

    async loadDetectionsForCurrentVideo() {
        if (!this._currentEvent || !this._overlayEnabled) return;
        try {
            const data = await this._hass.callWS({
                type: 'rtsp_recorder/get_analysis_result',
                media_id: this._currentEvent.id
            });
            if (data && data.detections) {
                this._analysisDetections = data.detections;
                this._analysisInterval = data.frame_interval || 2;
                this._analysisFrameSize = {
                    width: data.frame_width || null,
                    height: data.frame_height || null
                };
                this.drawOverlay();
            } else {
                this._analysisDetections = null;
                this.clearOverlay();
            }
        } catch (e) {
            this._analysisDetections = null;
            this.clearOverlay();
        }
    }

    resizeOverlay() {
        const canvas = this.shadowRoot.querySelector('#overlay-canvas');
        const video = this.shadowRoot.querySelector('#main-video');
        if (!canvas || !video) return;
        canvas.width = video.clientWidth;
        canvas.height = video.clientHeight;
    }

    clearOverlay() {
        const canvas = this.shadowRoot.querySelector('#overlay-canvas');
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        ctx.clearRect(0, 0, canvas.width, canvas.height);
    }

    updateOverlayStates() {
        const btn = this.shadowRoot.querySelector('#btn-overlay');
        if (btn) btn.classList.toggle('active', this._overlayEnabled);

        const footerToggle = this.shadowRoot.querySelector('#footer-overlay');
        if (footerToggle) footerToggle.checked = !!this._overlayEnabled;

        const menuToggle = this.shadowRoot.querySelector('#analysis-overlay');
        if (menuToggle) menuToggle.checked = !!this._overlayEnabled;
    }

    async fetchDetectorStats() {
        if (!this._hass) return;
        try {
            const result = await this._hass.callWS({ type: 'rtsp_recorder/get_detector_stats' });
            console.log('[RTSP-Recorder] Detector Stats Result:', JSON.stringify(result, null, 2));
            this._detectorStats = result;
            
            // Get system stats from our component (reads /proc directly)
            this._liveStats = {};
            const sysStats = result.system_stats || {};
            if (sysStats.cpu_percent != null) {
                this._liveStats.cpu = { state: sysStats.cpu_percent, unit: '%', name: 'CPU' };
            }
            if (sysStats.memory_percent != null) {
                this._liveStats.memory = { state: sysStats.memory_percent, unit: '%', name: 'RAM' };
            }
            this._liveStats.memoryMb = sysStats.memory_used_mb || 0;
            this._liveStats.memoryTotalMb = sysStats.memory_total_mb || 0;
            
            // Add to history for graphs
            if (this._liveStats.cpu) {
                this._statsHistory.push({
                    time: Date.now(),
                    cpu: this._liveStats.cpu.state,
                    memory: this._liveStats.memory?.state || 0
                });
                if (this._statsHistory.length > this._maxHistoryPoints) {
                    this._statsHistory.shift();
                }
            }
            
            this.updatePerfFooter();
            
            // Update performance tab if open
            if (this._activeTab === 'performance') {
                this.renderPerformanceTab(this.shadowRoot.querySelector('#menu-content'));
            }
        } catch (e) {
            console.warn('Failed to fetch detector stats:', e);
        }
    }

    startStatsPolling() {
        if (this._statsPolling) return;
        this.fetchDetectorStats();
        this._statsPolling = setInterval(() => this.fetchDetectorStats(), 5000);
    }

    stopStatsPolling() {
        if (this._statsPolling) {
            clearInterval(this._statsPolling);
            this._statsPolling = null;
        }
    }

    updatePerfFooter() {
        const panel = this.shadowRoot.querySelector('#footer-perf-panel');
        if (!panel) return;

        if (!this._showPerfPanel) {
            panel.innerHTML = '';
            this.stopStatsPolling();
            return;
        }

        // Start polling if not already
        this.startStatsPolling();

        const stats = this._detectorStats || {};
        const live = this._liveStats || {};
        const tracker = stats.inference_stats || {};
        const devices = stats.devices || [];
        const hasCoralUsb = devices.includes('coral_usb');

        // CPU from live HA sensor
        let cpuValue = 'n/a';
        let cpuColor = '#888';
        if (live.cpu && live.cpu.state != null) {
            const cpuPct = live.cpu.state;
            cpuValue = cpuPct.toFixed(1) + '%';
            cpuColor = cpuPct > 80 ? '#f44336' : cpuPct > 50 ? '#ff9800' : '#4caf50';
        }

        // Memory from live HA sensor
        let memValue = 'n/a';
        let memColor = '#888';
        if (live.memory && live.memory.state != null) {
            const memPct = live.memory.state;
            memValue = memPct.toFixed(1) + '%';
            memColor = memPct > 80 ? '#f44336' : memPct > 60 ? '#ff9800' : '#4caf50';
        }

        // Coral device status
        let coralHtml = '';
        if (hasCoralUsb) {
            const coralActive = tracker.last_device === 'coral_usb';
            const coralPct = tracker.recent_coral_pct ?? 0;
            const hasInf = tracker.total_inferences > 0;
            const coralDisplay = hasInf ? `${coralPct}%` : '-';
            const coralColor = !hasInf
                ? '#666'
                : coralPct > 50
                    ? '#4caf50'
                    : coralPct > 0
                        ? '#ff9800'
                        : '#666';
            coralHtml = `
                <div class="fm-perf-card">
                    <div class="fm-perf-label">Coral USB</div>
                    <div class="fm-perf-value" style="color: ${coralActive ? '#4caf50' : '#888'}">
                        ${coralActive ? 'Aktiv' : 'Bereit'}
                    </div>
                </div>
                <div class="fm-perf-card">
                    <div class="fm-perf-label">Coral Anteil</div>
                    <div class="fm-perf-value" style="color: ${coralColor}">
                        ${coralDisplay}
                    </div>
                </div>
            `;
        } else {
            coralHtml = `
                <div class="fm-perf-card">
                    <div class="fm-perf-label">Coral USB</div>
                    <div class="fm-perf-value" style="color: #666">Nicht verbunden</div>
                </div>
            `;
        }

        // Inference stats
        let inferenceHtml = '';
        let inferenceHint = '';
        if (tracker.total_inferences > 0) {
            inferenceHtml = `
                <div class="fm-perf-card">
                    <div class="fm-perf-label">Inferenz</div>
                    <div class="fm-perf-value">${(tracker.avg_inference_ms || 0).toFixed(0)}ms</div>
                </div>
                <div class="fm-perf-card">
                    <div class="fm-perf-label">Gesamt</div>
                    <div class="fm-perf-value">${tracker.total_inferences}</div>
                </div>
            `;
        } else {
            inferenceHint = `
                <div style="flex-basis:100%; font-size:0.85em; color:#888; margin-top:6px;">
                    Coral-Nutzung wird nur bei aktiver Live-Erkennung oder neuer Videoanalyse gezaehlt.
                </div>
            `;
        }

        panel.innerHTML = `
            <div class="fm-perf-card">
                <div class="fm-perf-label">CPU</div>
                <div class="fm-perf-value" style="color: ${cpuColor}">${cpuValue}</div>
            </div>
            <div class="fm-perf-card">
                <div class="fm-perf-label">RAM</div>
                <div class="fm-perf-value" style="color: ${memColor}">${memValue}</div>
            </div>
            ${coralHtml}
            ${inferenceHtml}
            ${inferenceHint}
        `;
    }

    drawOverlay() {
        if (!this._overlayEnabled || !this._analysisDetections) return;
        const canvas = this.shadowRoot.querySelector('#overlay-canvas');
        const video = this.shadowRoot.querySelector('#main-video');
        if (!canvas || !video || !video.videoWidth) return;

        this.resizeOverlay();

        const ctx = canvas.getContext('2d');
        ctx.clearRect(0, 0, canvas.width, canvas.height);

        const frameSize = this._analysisFrameSize || { width: video.videoWidth, height: video.videoHeight };
        const fw = frameSize.width || video.videoWidth;
        const fh = frameSize.height || video.videoHeight;

        const containerW = video.clientWidth;
        const containerH = video.clientHeight;
        const videoAspect = video.videoWidth / video.videoHeight;
        const containerAspect = containerW / containerH;

        let drawW, drawH, offsetX, offsetY;
        if (videoAspect > containerAspect) {
            drawW = containerW;
            drawH = containerW / videoAspect;
            offsetX = 0;
            offsetY = (containerH - drawH) / 2;
        } else {
            drawH = containerH;
            drawW = containerH * videoAspect;
            offsetY = 0;
            offsetX = (containerW - drawW) / 2;
        }

        const scaleX = drawW / fw;
        const scaleY = drawH / fh;

        const t = video.currentTime;
        const key = Math.round(t / this._analysisInterval) * this._analysisInterval;
        const frame = this._analysisDetections.find(d => d.time_s === key);
        if (!frame || !frame.objects) return;

        ctx.strokeStyle = '#00e5ff';
        ctx.lineWidth = 2;
        ctx.font = '12px sans-serif';
        ctx.fillStyle = '#00e5ff';

        frame.objects.forEach(obj => {
            const box = obj.box;
            const x = offsetX + box.x * scaleX;
            const y = offsetY + box.y * scaleY;
            const w = box.w * scaleX;
            const h = box.h * scaleY;
            ctx.strokeRect(x, y, w, h);
            const label = `${obj.label} ${Math.round(obj.score * 100)}%`;
            ctx.fillText(label, x + 2, y - 4);
        });
    }

    async renderStorageTab(container) {
        container.innerHTML = `<div style="text-align:center;color:#888;padding:40px;">Lade Speicherinfo...</div>`;
        
        // Calculate from events
        const totalEvents = this._events ? this._events.length : 0;
        
        // Group by camera
        const camCounts = {};
        if (this._events) {
            this._events.forEach(e => {
                camCounts[e.cam] = (camCounts[e.cam] || 0) + 1;
            });
        }
        
        // Get today's recordings
        const today = new Date();
        const todayStr = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`;
        const todayCount = this._events ? this._events.filter(e => e.iso === todayStr).length : 0;
        
        // Build camera breakdown
        const camBreakdown = Object.entries(camCounts)
            .sort((a, b) => b[1] - a[1])
            .map(([cam, count]) => `
                <div style="display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid #333;">
                    <span>${cam.replace(/_/g, ' ')}</span>
                    <span style="color:var(--primary-color);font-weight:500;">${count}</span>
                </div>
            `).join('');
        
        container.innerHTML = `
            <div style="padding:10px;">
                <div class="fm-storage-stats">
                    <div class="fm-stat-card">
                        <div class="fm-stat-value">${totalEvents}</div>
                        <div class="fm-stat-label">Aufnahmen gesamt</div>
                    </div>
                    <div class="fm-stat-card">
                        <div class="fm-stat-value">${todayCount}</div>
                        <div class="fm-stat-label">Heute</div>
                    </div>
                    <div class="fm-stat-card">
                        <div class="fm-stat-value">${Object.keys(camCounts).length}</div>
                        <div class="fm-stat-label">Kameras</div>
                    </div>
                    <div class="fm-stat-card">
                        <div class="fm-stat-value">~${(totalEvents * 0.05).toFixed(1)}</div>
                        <div class="fm-stat-label">GB geschaetzt</div>
                    </div>
                </div>
                
                <div style="margin-top:25px;">
                    <div style="font-weight:500;margin-bottom:10px;">Aufnahmen pro Kamera</div>
                    ${camBreakdown || '<div style="color:#888;">Keine Daten</div>'}
                </div>
                
                <button class="fm-btn-danger" id="btn-refresh-storage" style="margin-top:20px;">
                    Aktualisieren
                </button>
            </div>
        `;
        
        container.querySelector('#btn-refresh-storage').onclick = () => {
            this.loadData();
            this.renderStorageTab(container);
        };
    }

    _toMediaSourcePath(basePath) {
        if (!basePath || !basePath.startsWith('/media/')) return null;
        const rel = basePath.replace(/^\/media\//, '');
        return `media-source://media_source/local/${rel}`;
    }

    async loadData() {
        const hass = this._hass;
        const path = this._toMediaSourcePath(this._basePath);
        if (!path) {
            this.shadowRoot.querySelector('#list').innerHTML = `<div style="padding:20px;color:red;">Fehler: Base-Pfad muss mit /media/ beginnen. (base_path: ${this._basePath})</div>`;
            return;
        }
        try {
            const root = await hass.callWS({ type: 'media_source/browse_media', media_content_id: path });
            let events = [];
            if (root && root.children) {
                for (const folder of root.children) {
                    if (folder.media_class !== 'directory') continue;
                    if (folder.title === '_analysis') continue;
                    const res = await hass.callWS({ type: 'media_source/browse_media', media_content_id: folder.media_content_id });
                    if (res.children) {
                        res.children.forEach(f => {
                            const parts = f.title.match(/(\d{8})_(\d{6})/);
                            if (parts) {
                                const d = parts[1], t = parts[2];
                                const dt = new Date(`${d.substr(0, 4)}-${d.substr(4, 2)}-${d.substr(6, 2)}T${t.substr(0, 2)}:${t.substr(2, 2)}:${t.substr(4, 2)}`);
                                events.push({
                                    id: f.media_content_id,
                                    date: dt,
                                    cam: folder.title,
                                    iso: `${d.substr(0, 4)}-${d.substr(4, 2)}-${d.substr(6, 2)}`,
                                    thumb: `${this._thumbBase}/${folder.title}/${f.title.replace(/\.mp4$/i, '.jpg')}`
                                });
                            }
                        });
                    }
                }
            }
            this._events = events.sort((a, b) => b.date - a.date);
            this.updateView();
        } catch (e) {
            this.shadowRoot.querySelector('#list').innerHTML = `<div style="padding:20px;color:red;">Fehler beim Laden: ${e.message} (base_path: ${this._basePath})</div>`;
        }
    }

    updateView() {
        const root = this.shadowRoot;
        const list = root.querySelector('#list');
        const ruler = root.querySelector('#ruler');
        if (!list || !ruler) return;
        list.innerHTML = ''; ruler.innerHTML = '';

        let filtered = this._events || [];
        if (this._selectedDate) filtered = filtered.filter(e => e.iso === this._selectedDate);
        else filtered = filtered.filter(e => e.date > new Date(Date.now() - 24 * 60 * 60 * 1000));
        if (this._selectedCam !== 'Alle') filtered = filtered.filter(e => e.cam === this._selectedCam);

        if (filtered.length === 0) { list.innerHTML = `<div style="padding:20px;color:#888;text-align:center;">Keine Aufnahmen.</div>`; return; }

        let index = 0;
        filtered.forEach(ev => {
            const time = ev.date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

            // Render Tick with staggered animation
            const tick = document.createElement('div'); tick.className = 'fm-tick';
            if (this._animationsEnabled) {
                tick.style.animationDelay = `${index * 0.05}s`;
            }
            tick.innerHTML = `<span class="fm-tick-label">${time}</span>`;
            ruler.appendChild(tick);

            // Render Item with staggered animation
            const item = document.createElement('div'); item.className = 'fm-item';
            if (this._animationsEnabled) {
                item.style.animationDelay = `${index * 0.05}s`;
            }
            const displayName = ev.cam.replace(/_/g, ' ');

            item.innerHTML = `
                <div class="fm-thumb-wrap">
                    <img src="${ev.thumb}" class="fm-thumb-img" onerror="this.style.display='none'">
                    <div class="fm-badge-cam">${displayName}</div>
                    <div style="position:absolute;top:10px;right:10px;background:rgba(0,0,0,0.5);padding:2px 6px;border-radius:4px;font-size:0.7em;">${time}</div>
                </div>
            `;
            item.onclick = async () => {
                root.querySelectorAll('.fm-item').forEach(x => x.classList.remove('selected')); 
                item.classList.add('selected');
                
                // Store current event for download/delete
                this._currentEvent = ev;
                
                const video = root.querySelector('#main-video');
                // Add loading state for smooth transition
                if (this._animationsEnabled) {
                    video.classList.add('loading');
                }
                
                const info = await this._hass.callWS({ type: 'media_source/resolve_media', media_content_id: ev.id });
                this._currentVideoUrl = info.url;
                video.src = info.url;
                video.onloadeddata = () => {
                    if (this._animationsEnabled) {
                        video.classList.remove('loading');
                    }
                };
                video.play();
                root.querySelector('#txt-cam').innerText = displayName;
                root.querySelector('#txt-date').innerText = ev.date.toLocaleString('de-DE');
                if (this._overlayEnabled) {
                    this.loadDetectionsForCurrentVideo();
                }
            };
            list.appendChild(item);
            index++;
        });
    }

    renderCalendar() {
        const grid = this.shadowRoot.querySelector('#cal-grid');
        const lbl = this.shadowRoot.querySelector('#cal-month-year');
        if (!grid || !lbl) return;
        const months = ["Januar", "Februar", "Maerz", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober", "November", "Dezember"];
        lbl.innerText = `${months[this._calMonth]} ${this._calYear}`;
        grid.innerHTML = '';
        const firstDay = new Date(this._calYear, this._calMonth, 1).getDay();
        const daysInMonth = new Date(this._calYear, this._calMonth + 1, 0).getDate();
        let startOffset = firstDay === 0 ? 6 : firstDay - 1;
        for (let i = 0; i < startOffset; i++) grid.innerHTML += `<div class="fm-cal-day"></div>`;
        const today = new Date();
        const todayStr = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`;
        for (let d = 1; d <= daysInMonth; d++) {
            const iso = `${this._calYear}-${String(this._calMonth + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
            const el = document.createElement('div'); el.className = 'fm-cal-day'; el.innerText = d;
            if (iso === todayStr) el.classList.add('today');
            if (iso === this._selectedDate) el.classList.add('selected');
            el.onclick = () => { this._selectedDate = iso; this.updateDateLabel(); this.togglePopup(); this.renderCalendar(); };
            grid.appendChild(el);
        }
    }

    // ========== DOWNLOAD ==========
    async downloadCurrentVideo() {
        if (!this._currentVideoUrl || !this._currentEvent) {
            this.showToast('Bitte zuerst eine Aufnahme auswaehlen', 'warning');
            return;
        }
        
        const filename = `${this._currentEvent.cam}_${this._currentEvent.iso}_${this._currentEvent.date.toLocaleTimeString('de-DE', {hour:'2-digit', minute:'2-digit'}).replace(':','-')}.mp4`;
        
        // Try modern File System Access API (Chrome/Edge) for "Save As" dialog
        if ('showSaveFilePicker' in window) {
            try {
                const handle = await window.showSaveFilePicker({
                    suggestedName: filename,
                    types: [{
                        description: 'Video Datei',
                        accept: { 'video/mp4': ['.mp4'] }
                    }]
                });
                
                this.showToast('Download laeuft...', 'info');
                
                // Fetch the video
                const response = await fetch(this._currentVideoUrl);
                const blob = await response.blob();
                
                // Write to selected file
                const writable = await handle.createWritable();
                await writable.write(blob);
                await writable.close();
                
                this.showToast('Download abgeschlossen!', 'success');
                return;
            } catch (e) {
                // User cancelled or API failed - fall through to standard download
                if (e.name === 'AbortError') {
                    return; // User cancelled
                }
                console.warn('Save dialog failed, using standard download:', e);
            }
        }
        
        // Fallback: Standard download (goes to Downloads folder)
        const a = document.createElement('a');
        a.href = this._currentVideoUrl;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        this.showToast('Download gestartet (Standard-Ordner)', 'success');
    }

    // ========== DELETE ==========
    showDeleteConfirm() {
        if (!this._currentEvent) {
            this.showToast('Bitte zuerst eine Aufnahme auswaehlen', 'warning');
            return;
        }
        const filename = `${this._currentEvent.cam} - ${this._currentEvent.date.toLocaleString('de-DE')}`;
        this.shadowRoot.querySelector('#confirm-filename').innerText = filename;
        this.shadowRoot.querySelector('#confirm-overlay').classList.add('open');
    }

    hideDeleteConfirm() {
        this.shadowRoot.querySelector('#confirm-overlay').classList.remove('open');
    }

    async deleteCurrentVideo() {
        if (!this._currentEvent) return;
        
        try {
            // Call HA service to delete the file
            await this._hass.callService('rtsp_recorder', 'delete_recording', {
                media_id: this._currentEvent.id
            });
            
            // Remove from local list
            this._events = this._events.filter(e => e.id !== this._currentEvent.id);
            this._currentEvent = null;
            this._currentVideoUrl = null;
            
            // Clear video
            const video = this.shadowRoot.querySelector('#main-video');
            video.src = '';
            this.shadowRoot.querySelector('#txt-cam').innerText = 'Waehle Aufnahme';
            this.shadowRoot.querySelector('#txt-date').innerText = 'Geloescht';
            
            this.hideDeleteConfirm();
            this.updateView();
            this.showToast('Aufnahme geloescht', 'success');
        } catch (e) {
            console.error('Delete failed:', e);
            this.showToast('Fehler beim Loeschen: ' + e.message, 'error');
            this.hideDeleteConfirm();
        }
    }

    // ========== TOAST NOTIFICATIONS ==========
    showToast(message, type = 'info') {
        const existing = this.shadowRoot.querySelector('.fm-toast');
        if (existing) existing.remove();
        
        const colors = {
            success: '#4caf50',
            warning: '#ff9800',
            error: '#f44336',
            info: '#03a9f4'
        };
        
        const toast = document.createElement('div');
        toast.className = 'fm-toast';
        toast.style.cssText = `
            position: absolute;
            bottom: 80px;
            left: 50%;
            transform: translateX(-50%);
            background: ${colors[type]};
            color: #fff;
            padding: 12px 24px;
            border-radius: 8px;
            font-weight: 500;
            z-index: 5000;
            animation: fadeInUp 0.3s ease-out;
            box-shadow: 0 4px 20px rgba(0,0,0,0.4);
        `;
        toast.innerText = message;
        this.shadowRoot.querySelector('#container').appendChild(toast);
        
        setTimeout(() => {
            toast.style.opacity = '0';
            toast.style.transition = 'opacity 0.3s ease';
            setTimeout(() => toast.remove(), 300);
        }, 3000);
    }

    // ========== STORAGE INFO ==========
    async loadStorageInfo() {
        try {
            const result = await this._hass.callService('rtsp_recorder', 'get_storage_info', {}, true);
            return result;
        } catch (e) {
            // Fallback: estimate from events
            const totalEvents = this._events ? this._events.length : 0;
            const estimatedSize = totalEvents * 50; // ~50MB per recording estimate
            return {
                used_gb: (estimatedSize / 1024).toFixed(1),
                total_gb: 'N/A',
                percent: 0,
                recordings: totalEvents
            };
        }
    }
}

// REGISTER STANDARD CARD
customElements.define('rtsp-recorder-card', RtspRecorderCard);
