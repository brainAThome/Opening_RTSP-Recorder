// ===== RTSP Recorder Card v1.0.7 =====
// MED-008 Fix: Debug logging behind feature flag
const RTSP_DEBUG = localStorage.getItem('rtsp_recorder_debug') === 'true';
const rtspLog = (...args) => { if (RTSP_DEBUG) console.log('[RTSP]', ...args); };
const rtspInfo = (...args) => { if (RTSP_DEBUG) console.info('[RTSP]', ...args); };
const rtspWarn = (...args) => console.warn('[RTSP]', ...args);  // Warnings always shown
const rtspError = (...args) => console.error('[RTSP]', ...args);  // Errors always shown

if (RTSP_DEBUG) {
    console.info("%c RTSP RECORDER CARD \n%c v1.0.7 (DEBUG) ", "color: #3498db; font-weight: bold; background: #222; padding: 5px;", "color: #e74c3c;");
}

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
        this._people = [];
        this._peopleLoaded = false;
        this._selectedPersonId = null;
        this._analysisFaceSamples = [];
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
                .fm-menu-card { background: #1a1a1a; border: 1px solid #333; width: 600px; max-width: 90%; max-height: 90vh; border-radius: 16px; display: flex; flex-direction: column; overflow: hidden; }
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
            
            <div class="fm-container animated" id="container" role="application" aria-label="RTSP Recorder Kamera Archiv">
                <div class="fm-header" role="banner">
                    <div class="fm-title">Kamera Archiv <span style="font-size:0.6em; opacity:0.5; margin-left:10px; border:1px solid #444; padding:2px 6px; border-radius:4px;">BETA v1.0.7</span></div>
                    <div class="fm-toolbar" role="toolbar" aria-label="Filteroptionen">
                        <button class="fm-btn active" id="btn-date" aria-haspopup="true" aria-expanded="false">Letzte 24 Std</button>
                        <button class="fm-btn" id="btn-cams" aria-haspopup="true" aria-expanded="false">Kameras</button>
                        <button class="fm-btn" id="btn-menu" aria-label="Menue oeffnen">Menue</button>
                    </div>
                </div>
                <div class="fm-main" role="main">
                    <div class="fm-player-col">
                        <div class="fm-player-body">
                            <div class="fm-overlay-tl" id="txt-cam" aria-live="polite">Waehle Aufnahme</div>
                            <div class="fm-overlay-tr" id="txt-date">BETA VERSION</div>
                            <video id="main-video" controls autoplay muted playsinline aria-label="Aufnahme Videoplayer"></video>
                            <canvas id="overlay-canvas" aria-hidden="true"></canvas>
                        
                            <!-- Video Controls -->
                            <div class="fm-video-controls" id="video-controls" role="group" aria-label="Video Steuerung">
                                <button class="fm-ctrl-btn" id="btn-download" title="Download" aria-label="Video herunterladen">
                                    <svg width="16" height="16" fill="currentColor" viewBox="0 0 16 16" aria-hidden="true"><path d="M.5 9.9a.5.5 0 0 1 .5.5v2.5a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-2.5a.5.5 0 0 1 1 0v2.5a2 2 0 0 1-2 2H2a2 2 0 0 1-2-2v-2.5a.5.5 0 0 1 .5-.5z"/><path d="M7.646 11.854a.5.5 0 0 0 .708 0l3-3a.5.5 0 0 0-.708-.708L8.5 10.293V1.5a.5.5 0 0 0-1 0v8.793L5.354 8.146a.5.5 0 1 0-.708.708l3 3z"/></svg>
                                    Download
                                </button>
                                <button class="fm-ctrl-btn danger" id="btn-delete" title="Loeschen" aria-label="Video loeschen">
                                    <svg width="16" height="16" fill="currentColor" viewBox="0 0 16 16" aria-hidden="true"><path d="M5.5 5.5A.5.5 0 0 1 6 6v6a.5.5 0 0 1-1 0V6a.5.5 0 0 1 .5-.5zm2.5 0a.5.5 0 0 1 .5.5v6a.5.5 0 0 1-1 0V6a.5.5 0 0 1 .5-.5zm3 .5a.5.5 0 0 0-1 0v6a.5.5 0 0 0 1 0V6z"/><path fill-rule="evenodd" d="M14.5 3a1 1 0 0 1-1 1H13v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V4h-.5a1 1 0 0 1-1-1V2a1 1 0 0 1 1-1H6a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1h3.5a1 1 0 0 1 1 1v1zM4.118 4 4 4.059V13a1 1 0 0 0 1 1h6a1 1 0 0 0 1-1V4.059L11.882 4H4.118zM2.5 3V2h11v1h-11z"/></svg>
                                    Loeschen
                                </button>
                                <button class="fm-ctrl-btn" id="btn-overlay" title="Overlay" aria-label="Erkennungs-Overlay umschalten" aria-pressed="false">
                                    <svg width="16" height="16" fill="currentColor" viewBox="0 0 16 16" aria-hidden="true"><path d="M8 3C4.5 3 1.73 5.11.46 8c1.27 2.89 4.04 5 7.54 5s6.27-2.11 7.54-5C14.27 5.11 11.5 3 8 3zm0 8.5A3.5 3.5 0 1 1 8 4.5a3.5 3.5 0 0 1 0 7z"/><path d="M8 6.5A1.5 1.5 0 1 0 8 9.5a1.5 1.5 0 0 0 0-3z"/></svg>
                                    Overlay
                                </button>
                                <div style="border-left: 1px solid #444; margin: 0 5px;" aria-hidden="true"></div>
                                <button class="fm-ctrl-btn fm-speed-btn" data-speed="0.5" aria-label="Geschwindigkeit 0.5x">0.5x</button>
                                <button class="fm-ctrl-btn fm-speed-btn active" data-speed="1" aria-label="Geschwindigkeit Normal" aria-pressed="true">1x</button>
                                <button class="fm-ctrl-btn fm-speed-btn" data-speed="2" aria-label="Geschwindigkeit 2x">2x</button>
                            </div>
                        </div>
                        <div class="fm-player-footer" id="player-footer" role="region" aria-label="Videooptionen">
                            <div class="fm-footer-left">
                                <label class="fm-toggle">
                                    <input id="footer-overlay" type="checkbox" ${this._overlayEnabled ? 'checked' : ''} aria-describedby="overlay-desc" />
                                    <span id="overlay-desc">Objekte im Video</span>
                                </label>
                                <label class="fm-toggle">
                                    <input id="footer-perf" type="checkbox" ${this._showPerfPanel ? 'checked' : ''} aria-describedby="perf-desc" />
                                    <span id="perf-desc">Leistung anzeigen</span>
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
                    <div class="fm-cal-header"><button class="fm-cal-btn" id="cal-prev" aria-label="Vorheriger Monat">&lt;</button><span id="cal-month-year"></span><button class="fm-cal-btn" id="cal-next" aria-label="Naechster Monat">&gt;</button></div>
                    <div class="fm-cal-grid" id="cal-grid" role="grid" aria-label="Kalender"></div>
                    <div style="padding: 10px; border-top: 1px solid #333; text-align: center;"><button id="btn-clear-date" class="fm-btn-danger" aria-label="Datumsfilter zuruecksetzen">Filter Leeren</button></div>
                </div>
                
                <!-- Menu -->
                <div class="fm-menu-overlay" id="menu-overlay" role="dialog" aria-modal="true" aria-labelledby="menu-title">
                    <div class="fm-menu-card">
                        <div class="fm-menu-header"><div class="fm-menu-title" id="menu-title">Einstellungen</div><div class="fm-menu-close" id="menu-close" role="button" aria-label="Menue schliessen" tabindex="0">X</div></div>
                        <div class="fm-tabs" role="tablist" aria-label="Einstellungskategorien">
                            <div class="fm-tab active" data-tab="general" role="tab" aria-selected="true" tabindex="0">Allgemein</div>
                            <div class="fm-tab" data-tab="storage" role="tab" aria-selected="false" tabindex="-1">Speicher</div>
                            <div class="fm-tab" data-tab="analysis" role="tab" aria-selected="false" tabindex="-1">Analyse</div>
                            <div class="fm-tab" data-tab="people" role="tab" aria-selected="false" tabindex="-1">Personen</div>
                            <div class="fm-tab ${this._showPerfTab ? '' : 'hidden'}" data-tab="performance" role="tab" aria-selected="false" tabindex="-1">Leistung</div>
                        </div>
                        <div class="fm-menu-content" id="menu-content" role="tabpanel"></div>
                    </div>
                </div>
                
                <!-- Delete Confirmation -->
                <div class="fm-confirm-overlay" id="confirm-overlay" role="alertdialog" aria-modal="true" aria-labelledby="confirm-title" aria-describedby="confirm-desc">
                    <div class="fm-confirm-card">
                        <div style="font-size:2em;margin-bottom:15px;" aria-hidden="true">!</div>
                        <div style="font-size:1.1em;font-weight:500;" id="confirm-title">Aufnahme loeschen?</div>
                        <div style="color:#888;margin-top:10px;" id="confirm-filename" id="confirm-desc"></div>
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
        } else if (this._activeTab === 'people') {
            // People Tab
            this.renderPeopleTab(container);
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

    renderPeopleTab(container) {
        if (!this._peopleLoaded) {
            container.innerHTML = `<div style="color:#888; padding:20px;">Lade Personen...</div>`;
            this.refreshPeople().then(() => {
                if (this._activeTab === 'people') {
                    this.renderPeopleTab(container);
                }
            });
            return;
        }

        const people = this._people || [];
        const peopleOptions = people.map(p => {
            const selected = this._selectedPersonId === p.id ? 'selected' : '';
            return `<option value="${p.id}" ${selected}>${p.name} (${p.embeddings_count})</option>`;
        }).join('');

        const peopleList = people.map(p => {
            const thumbs = (p.recent_thumbs || []).slice(0, 5).map((t, idx) =>
                `<img src="${t}" 
                    style="width:48px; height:48px; object-fit:cover; border-radius:8px; border:2px solid #444; cursor:pointer; transition:transform 0.2s, border-color 0.2s;" 
                    data-person-id="${p.id}" 
                    data-thumb-idx="${idx}"
                    title="Klicken zum Vergrößern"
                    onmouseover="this.style.transform='scale(1.1)'; this.style.borderColor='var(--primary-color)';"
                    onmouseout="this.style.transform='scale(1)'; this.style.borderColor='#444';"
                />`
            ).join('');
            return `
                <div class="person-card" style="background:#1a1a1a; border-radius:12px; padding:12px; margin-bottom:10px;">
                    <div style="display:flex; justify-content:space-between; align-items:flex-start;">
                        <div style="flex:1;">
                            <div style="font-weight:600; font-size:1.1em; margin-bottom:4px;">${p.name}</div>
                            <div style="font-size:0.85em; color:#888;">📸 ${p.embeddings_count} Embeddings</div>
                        </div>
                        <div style="display:flex; gap:6px;">
                            <button class="fm-btn" data-action="rename" data-id="${p.id}" style="padding:6px 12px; font-size:0.85em;">✏️</button>
                            <button class="fm-btn-danger" data-action="delete" data-id="${p.id}" style="padding:6px 12px; font-size:0.85em;">🗑️</button>
                        </div>
                    </div>
                    ${thumbs ? `<div style="margin-top:10px; display:flex; gap:6px; flex-wrap:wrap;">${thumbs}</div>` : '<div style="margin-top:10px; color:#666; font-size:0.85em;">Keine Vorschaubilder</div>'}
                </div>
            `;
        }).join('');

        const faceSamples = this._analysisFaceSamples || [];
        if (!this._enrolledSampleKeys) {
            this._enrolledSampleKeys = new Set();
        }
        
        // Gruppiere Face-Samples: Unbekannt vs. Erkannt
        const unknownFaces = faceSamples.filter(f => !f.match);
        const knownFaces = faceSamples.filter(f => f.match);
        
        const renderFaceGrid = (faces, showAssignBtn = true) => {
            if (!faces.length) return '';
            return faces.slice(0, 20).map((f, idx) => {
                const realIdx = faceSamples.indexOf(f);
                const match = f.match ? `${f.match.name}` : '';
                const similarity = f.match ? `${Math.round(f.match.similarity * 100)}%` : '';
                const sampleKey = `${f.time_s}|${f.thumb || ''}`;
                const isEnrolled = this._enrolledSampleKeys.has(sampleKey);
                const borderColor = isEnrolled ? '#27ae60' : (f.match ? 'var(--primary-color)' : '#555');
                return `
                    <div class="face-sample" style="display:flex; flex-direction:column; align-items:center; width:85px; ${isEnrolled ? 'opacity:0.6;' : ''}">
                        <div style="position:relative;">
                            ${f.thumb 
                                ? `<img src="${f.thumb}" style="width:70px; height:70px; object-fit:cover; border-radius:10px; border:3px solid ${borderColor}; cursor:pointer;" 
                                    data-action="enroll" data-idx="${realIdx}" title="${showAssignBtn ? 'Klicken zum Zuweisen' : match}" />`
                                : `<div style="width:70px; height:70px; background:#333; border-radius:10px; display:flex; align-items:center; justify-content:center;">👤</div>`
                            }
                            ${isEnrolled ? '<div style="position:absolute; top:-5px; right:-5px; background:#27ae60; border-radius:50%; width:20px; height:20px; display:flex; align-items:center; justify-content:center; font-size:12px;">✓</div>' : ''}
                        </div>
                        <div style="font-size:0.7em; color:#888; margin-top:4px; text-align:center; max-width:80px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">
                            ${match || `t=${f.time_s}s`}
                        </div>
                        ${similarity ? `<div style="font-size:0.65em; color:var(--primary-color);">${similarity}</div>` : ''}
                        ${showAssignBtn ? `<button class="fm-btn-small" data-action="no-face" data-idx="${realIdx}" style="margin-top:4px; background:#444; color:#eee; border:none; border-radius:6px; padding:2px 8px; font-size:0.75em; cursor:pointer;">Kein Gesicht</button>` : ''}
                    </div>
                `;
            }).join('');
        };
        
        const unknownFacesHtml = unknownFaces.length 
            ? `<div style="margin-bottom:15px;">
                <div style="font-weight:500; margin-bottom:8px; color:#e74c3c;">👤 Unbekannte Gesichter (${unknownFaces.length})</div>
                <div style="display:flex; flex-wrap:wrap; gap:8px; padding:10px; background:#1a1a1a; border-radius:10px; max-height:400px; overflow-y:auto;">
                    ${renderFaceGrid(unknownFaces, true)}
                </div>
               </div>`
            : '';
            
        const knownFacesHtml = knownFaces.length
            ? `<div>
                <div style="font-weight:500; margin-bottom:8px; color:#27ae60;">✓ Erkannte Gesichter (${knownFaces.length})</div>
                <div style="display:flex; flex-wrap:wrap; gap:8px; padding:10px; background:#1a1a1a; border-radius:10px; max-height:400px; overflow-y:auto;">
                    ${renderFaceGrid(knownFaces, false)}
                </div>
               </div>`
            : '';
        
        const noFacesHtml = !faceSamples.length ? '<div style="color:#888; padding:20px; text-align:center;">Keine Face-Samples geladen.<br><small>Wähle eine Aufnahme und klicke "Analyse laden"</small></div>' : '';

        container.innerHTML = `
            <div style="padding:10px;">
                <div style="font-weight:500; margin-bottom:10px;">Personen verwalten</div>
                <div style="display:flex; gap:8px; margin-bottom:12px;">
                    <input id="person-name" type="text" placeholder="Neuer Name" style="flex:1; padding:8px; background:#222; color:#eee; border:1px solid #333; border-radius:6px;" />
                    <button class="fm-btn" id="btn-add-person">Hinzufuegen</button>
                </div>
                <div id="people-list">
                    ${peopleList || '<div style="color:#888;">Keine Personen vorhanden</div>'}
                </div>

                <div style="margin-top:20px; border-top:1px solid #333; padding-top:15px;">
                    <div style="font-weight:500; margin-bottom:10px;">Training aus Analyse</div>
                    <div style="display:flex; gap:8px; align-items:center; margin-bottom:10px;">
                        <select id="people-select" style="flex:1; padding:8px; background:#222; color:#eee; border:1px solid #333; border-radius:6px;">
                            <option value="">-- Person waehlen --</option>
                            ${peopleOptions}
                        </select>
                        <button class="fm-btn" id="btn-load-faces">Analyse laden</button>
                    </div>
                    
                    ${unknownFacesHtml}
                    ${knownFacesHtml}
                    ${noFacesHtml}
                    
                    <div style="margin-top:12px; font-size:0.8em; color:#666; text-align:center;">
                        💡 Klicke auf ein unbekanntes Gesicht um es einer Person zuzuweisen
                    </div>
                </div>
            </div>
        `;

        const addBtn = container.querySelector('#btn-add-person');
        if (addBtn) {
            addBtn.onclick = async () => {
                const input = container.querySelector('#person-name');
                const name = input ? input.value.trim() : '';
                if (!name) {
                    this.showToast('Bitte Namen eingeben', 'warning');
                    return;
                }
                await this.addPerson(name);
                if (input) input.value = '';
            };
        }

        // Event-Handler für "Kein Gesicht"-Button
        container.querySelectorAll('button[data-action="no-face"]').forEach(btn => {
            btn.onclick = () => {
                const idx = parseInt(btn.getAttribute('data-idx'), 10);
                if (!isNaN(idx)) {
                    // Entferne das Sample aus der Liste
                    this._analysisFaceSamples.splice(idx, 1);
                    this.showToast('Sample als "kein Gesicht" entfernt.', 'info');
                    this.renderPeopleTab(container);
                }
            };
        });

        container.querySelectorAll('[data-action="rename"]').forEach(btn => {
            btn.onclick = async () => {
                const id = btn.getAttribute('data-id');
                const current = people.find(p => p.id === id);
                const newName = prompt('Neuer Name', current ? current.name : '');
                if (newName && newName.trim()) {
                    await this.renamePerson(id, newName.trim());
                }
            };
        });

        container.querySelectorAll('[data-action="delete"]').forEach(btn => {
            btn.onclick = async () => {
                const id = btn.getAttribute('data-id');
                const current = people.find(p => p.id === id);
                if (confirm(`Person "${current ? current.name : ''}" wirklich loeschen?`)) {
                    await this.deletePerson(current || { id });
                }
            };
        });

        const loadFacesBtn = container.querySelector('#btn-load-faces');
        if (loadFacesBtn) {
            loadFacesBtn.onclick = async () => {
                if (this._loadingFaceSamples) return;
                await this.loadFaceSamplesForCurrent();
                if (this._activeTab === 'people') {
                    this.renderPeopleTab(container);
                }
            };
        }

        const selectEl = container.querySelector('#people-select');
        if (selectEl) {
            selectEl.onchange = () => {
                this._selectedPersonId = selectEl.value || null;
            };
        }

        // Event-Handler für Enroll (Button oder Bild-Klick)
        container.querySelectorAll('[data-action="enroll"]').forEach(el => {
            el.onclick = async (e) => {
                e.preventDefault();
                const idx = parseInt(el.getAttribute('data-idx'), 10);
                const personId = this._selectedPersonId;
                
                // Wenn keine Person ausgewählt, zeige Schnellauswahl-Dialog
                if (!personId) {
                    const people = this._people || [];
                    if (people.length === 0) {
                        this.showToast('Bitte erst eine Person anlegen', 'warning');
                        return;
                    }
                    
                    // Erstelle Schnellauswahl-Popup
                    const sample = this._analysisFaceSamples[idx];
                    if (!sample) return;
                    
                    const popup = document.createElement('div');
                    popup.style.cssText = 'position:fixed; top:0; left:0; right:0; bottom:0; background:rgba(0,0,0,0.8); display:flex; align-items:center; justify-content:center; z-index:10000;';
                    popup.innerHTML = `
                        <div style="background:#222; border-radius:16px; padding:20px; max-width:400px; width:90%;">
                            <div style="text-align:center; margin-bottom:15px;">
                                ${sample.thumb ? `<img src="${sample.thumb}" style="width:100px; height:100px; object-fit:cover; border-radius:12px; border:3px solid var(--primary-color);" />` : ''}
                                <div style="margin-top:10px; font-weight:500;">Person zuweisen</div>
                            </div>
                            <div style="display:flex; flex-direction:column; gap:8px; max-height:200px; overflow-y:auto;">
                                ${people.map(p => `
                                    <div style="display:flex; gap:4px;">
                                        <button class="quick-assign-btn" data-person-id="${p.id}" style="flex:1; padding:10px; background:#333; border:none; border-radius:8px 0 0 8px; color:#fff; cursor:pointer; text-align:left; display:flex; align-items:center; gap:10px;">
                                            ${p.recent_thumbs && p.recent_thumbs[0] ? `<img src="${p.recent_thumbs[0]}" style="width:36px; height:36px; object-fit:cover; border-radius:6px;" />` : '<div style="width:36px; height:36px; background:#444; border-radius:6px; display:flex; align-items:center; justify-content:center;">👤</div>'}
                                            <div>
                                                <div style="font-weight:500;">${p.name}</div>
                                                <div style="font-size:0.75em; color:#888;">${p.embeddings_count} Samples</div>
                                            </div>
                                        </button>
                                        <button class="negative-sample-btn" data-person-id="${p.id}" data-person-name="${p.name}" style="padding:10px 12px; background:#663333; border:none; border-radius:0 8px 8px 0; color:#fff; cursor:pointer; font-size:0.9em;" title="Das ist NICHT ${p.name}">
                                            ❌
                                        </button>
                                    </div>
                                `).join('')}
                            </div>
                            <div style="margin-top:12px; padding:10px; background:#333; border-radius:8px; font-size:0.8em; color:#aaa;">
                                💡 <strong>Zuweisen:</strong> Links klicken<br>
                                ❌ <strong>Ausschließen:</strong> Rechts klicken (Negativ-Sample)
                            </div>
                            <button class="close-popup-btn" style="margin-top:12px; width:100%; padding:10px; background:#555; border:none; border-radius:8px; color:#fff; cursor:pointer;">Abbrechen</button>
                        </div>
                    `;
                    
                    document.body.appendChild(popup);
                    
                    // Event-Handler für Schnellauswahl (Positiv)
                    popup.querySelectorAll('.quick-assign-btn').forEach(btn => {
                        btn.onclick = async () => {
                            const selectedId = btn.getAttribute('data-person-id');
                            document.body.removeChild(popup);
                            if (sample.embedding) {
                                await this.addEmbeddingToPerson(selectedId, sample.embedding, sample.thumb || null);
                            } else {
                                this.showToast('Kein Embedding im Sample vorhanden', 'warning');
                            }
                        };
                        btn.onmouseover = () => btn.style.background = '#444';
                        btn.onmouseout = () => btn.style.background = '#333';
                    });
                    
                    // Event-Handler für Negativ-Samples
                    popup.querySelectorAll('.negative-sample-btn').forEach(btn => {
                        btn.onclick = async () => {
                            const personId = btn.getAttribute('data-person-id');
                            const personName = btn.getAttribute('data-person-name');
                            document.body.removeChild(popup);
                            if (sample.embedding) {
                                await this.addNegativeSample(personId, personName, sample.embedding, sample.thumb || null);
                            } else {
                                this.showToast('Kein Embedding im Sample vorhanden', 'warning');
                            }
                        };
                        btn.onmouseover = () => btn.style.background = '#884444';
                        btn.onmouseout = () => btn.style.background = '#663333';
                    });
                    
                    popup.querySelector('.close-popup-btn').onclick = () => document.body.removeChild(popup);
                    popup.onclick = (e) => { if (e.target === popup) document.body.removeChild(popup); };
                    return;
                }
                
                const sample = this._analysisFaceSamples[idx];
                if (!sample || !sample.embedding) {
                    this.showToast('Kein Embedding im Sample vorhanden', 'warning');
                    return;
                }
                await this.addEmbeddingToPerson(personId, sample.embedding, sample.thumb || null);
            };
        });
    }

    async refreshPeople() {
        try {
            const data = await this._hass.callWS({ type: 'rtsp_recorder/get_people' });
            const peopleRaw = (data && data.people) ? data.people : [];
            this._people = peopleRaw.map(p => ({
                ...p,
                id: String(p.id),
                embeddings_count: (p.embeddings_count != null) ? p.embeddings_count : (p.embeddings ? p.embeddings.length : 0),
                recent_thumbs: p.recent_thumbs || []
            }));
            this._peopleLoaded = true;
        } catch (e) {
            this._people = [];
            this._peopleLoaded = true;
        }
    }

    async addPerson(name) {
        try {
            await this._hass.callWS({ type: 'rtsp_recorder/add_person', name });
            await this.refreshPeople();
            this.showToast('Person hinzugefuegt', 'success');
            if (this._activeTab === 'people') {
                this.renderPeopleTab(this.shadowRoot.querySelector('#menu-content'));
            }
        } catch (e) {
            this.showToast('Fehler beim Hinzufuegen: ' + (e.message || e), 'error');
        }
    }

    async renamePerson(id, name) {
        try {
            await this._hass.callWS({ type: 'rtsp_recorder/rename_person', id: String(id), name });
            await this.refreshPeople();
            this.showToast('Person umbenannt', 'success');
            if (this._activeTab === 'people') {
                this.renderPeopleTab(this.shadowRoot.querySelector('#menu-content'));
            }
        } catch (e) {
            this.showToast('Fehler beim Umbenennen: ' + (e.message || e), 'error');
        }
    }

    async deletePerson(personOrId) {
        try {
            const payload = (personOrId && typeof personOrId === 'object')
                ? {
                    type: 'rtsp_recorder/delete_person',
                    id: String(personOrId.id),
                    name: personOrId.name || null,
                    created_utc: personOrId.created_utc || null,
                }
                : { type: 'rtsp_recorder/delete_person', id: String(personOrId) };
            await this._hass.callWS(payload);
            await this.refreshPeople();
            this.showToast('Person geloescht', 'success');
            if (this._activeTab === 'people') {
                this.renderPeopleTab(this.shadowRoot.querySelector('#menu-content'));
            }
        } catch (e) {
            this.showToast('Fehler beim Loeschen: ' + (e.message || e), 'error');
        }
    }

    async addEmbeddingToPerson(personId, embedding, thumb = null) {
        try {
            const person = (this._people || []).find(p => String(p.id) === String(personId));
            const payload = {
                type: 'rtsp_recorder/add_person_embedding',
                person_id: String(personId),
                embedding,
                source: 'analysis',
                thumb
            };
            if (person) {
                payload.name = person.name || null;
                payload.created_utc = person.created_utc || null;
            }
            await this._hass.callWS(payload);
            if (this._analysisFaceSamples) {
                const sample = this._analysisFaceSamples.find(s => s.embedding === embedding && s.thumb === thumb);
                if (sample) {
                    const key = `${sample.time_s}|${sample.thumb || ''}`;
                    if (!this._enrolledSampleKeys) this._enrolledSampleKeys = new Set();
                    this._enrolledSampleKeys.add(key);
                }
            }
            await this.refreshPeople();
            this.showToast('Embedding hinzugefuegt', 'success');
            if (this._activeTab === 'people') {
                this.renderPeopleTab(this.shadowRoot.querySelector('#menu-content'));
            }
        } catch (e) {
            this.showToast('Fehler beim Embedding: ' + (e.message || e), 'error');
        }
    }

    async addNegativeSample(personId, personName, embedding, thumb = null) {
        // Fügt ein Negativ-Sample hinzu: "Das ist NICHT diese Person"
        try {
            const payload = {
                type: 'rtsp_recorder/add_negative_sample',
                person_id: String(personId),
                embedding,
                thumb
            };
            await this._hass.callWS(payload);
            
            // Markiere das Sample als bearbeitet
            if (this._analysisFaceSamples) {
                const sample = this._analysisFaceSamples.find(s => s.embedding === embedding && s.thumb === thumb);
                if (sample) {
                    const key = `${sample.time_s}|${sample.thumb || ''}`;
                    if (!this._enrolledSampleKeys) this._enrolledSampleKeys = new Set();
                    this._enrolledSampleKeys.add(key);
                }
            }
            
            await this.refreshPeople();
            this.showToast(`Negativ-Sample fuer "${personName}" gespeichert`, 'success');
            if (this._activeTab === 'people') {
                this.renderPeopleTab(this.shadowRoot.querySelector('#menu-content'));
            }
        } catch (e) {
            this.showToast('Fehler beim Negativ-Sample: ' + (e.message || e), 'error');
        }
    }

    async loadFaceSamplesForCurrent() {
        this._analysisFaceSamples = [];
        this._enrolledSampleKeys = new Set();
        if (!this._currentEvent) {
            this.showToast('Bitte zuerst eine Aufnahme waehlen', 'warning');
            return;
        }
        this._loadingFaceSamples = true;
        try {
            const data = await this._hass.callWS({
                type: 'rtsp_recorder/get_analysis_result',
                media_id: this._currentEvent.id
            });
            const detections = (data && data.detections) ? data.detections : [];
            const samples = [];
            detections.forEach(d => {
                const time_s = d.time_s;
                const faces = d.faces || [];
                faces.forEach(f => {
                    if (f.embedding) {
                        samples.push({
                            time_s,
                            embedding: f.embedding,
                            match: f.match || null,
                            thumb: f.thumb || null
                        });
                    }
                });
            });
            this._analysisFaceSamples = samples;
            if (!samples.length) {
                this.showToast('Keine Face-Samples gefunden', 'warning');
            } else {
                this.showToast(`Face-Samples geladen: ${samples.length}`, 'success');
            }
        } catch (e) {
            this._analysisFaceSamples = [];
            this.showToast('Analyse konnte nicht geladen werden', 'warning');
        } finally {
            this._loadingFaceSamples = false;
        }
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
        if (!frame || (!frame.objects && !frame.faces)) return;

        ctx.strokeStyle = '#00e5ff';
        ctx.lineWidth = 2;
        ctx.font = '12px sans-serif';
        ctx.fillStyle = '#00e5ff';

        (frame.objects || []).forEach(obj => {
            const box = obj.box;
            const x = offsetX + box.x * scaleX;
            const y = offsetY + box.y * scaleY;
            const w = box.w * scaleX;
            const h = box.h * scaleY;
            ctx.strokeStyle = '#00e5ff';
            ctx.fillStyle = '#00e5ff';
            ctx.strokeRect(x, y, w, h);
            const label = `${obj.label} ${Math.round(obj.score * 100)}%`;
            ctx.fillText(label, x + 2, y - 4);
        });

        (frame.faces || []).forEach(face => {
            const box = face.box;
            const x = offsetX + box.x * scaleX;
            const y = offsetY + box.y * scaleY;
            const w = box.w * scaleX;
            const h = box.h * scaleY;
            ctx.strokeStyle = '#ff9800';
            ctx.fillStyle = '#ff9800';
            ctx.strokeRect(x, y, w, h);
            // Fix: Use match.similarity for recognized faces, face.score for unknown
            const matchName = face.match && face.match.name ? face.match.name : 'Unbekannt';
            const score = face.match && face.match.similarity != null 
                ? Math.round(face.match.similarity * 100) + '%' 
                : (face.score != null ? Math.round(face.score * 100) + '%' : '');
            const label = score ? `${matchName} ${score}` : matchName;
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
                
                <!-- Lösch-Bereich -->
                <div style="margin-top:30px;padding-top:20px;border-top:1px solid #444;">
                    <div style="font-weight:500;margin-bottom:15px;color:#e74c3c;">🗑️ Aufnahmen löschen</div>
                    
                    <div style="display:flex;flex-direction:column;gap:12px;">
                        <div style="display:flex;align-items:center;gap:10px;">
                            <label style="min-width:120px;">Kamera:</label>
                            <select id="delete-camera" style="flex:1;padding:8px;background:#333;color:#fff;border:1px solid #555;border-radius:4px;">
                                <option value="">Alle Kameras</option>
                                ${Object.keys(camCounts).map(cam => `<option value="${cam}">${cam.replace(/_/g, ' ')}</option>`).join('')}
                            </select>
                        </div>
                        
                        <div style="display:flex;align-items:center;gap:10px;">
                            <label style="min-width:120px;">Älter als:</label>
                            <select id="delete-age" style="flex:1;padding:8px;background:#333;color:#fff;border:1px solid #555;border-radius:4px;">
                                <option value="0">Alle (kein Filter)</option>
                                <option value="1">Älter als 1 Tag</option>
                                <option value="3">Älter als 3 Tage</option>
                                <option value="7">Älter als 1 Woche</option>
                                <option value="14">Älter als 2 Wochen</option>
                                <option value="30">Älter als 1 Monat</option>
                                <option value="90">Älter als 3 Monate</option>
                            </select>
                        </div>
                        
                        <div style="display:flex;align-items:center;gap:10px;">
                            <label style="min-width:120px;"></label>
                            <label style="display:flex;align-items:center;gap:8px;cursor:pointer;">
                                <input type="checkbox" id="delete-analysis" style="width:18px;height:18px;">
                                <span>Auch Analysen löschen</span>
                            </label>
                        </div>
                    </div>
                    
                    <div style="margin-top:20px;display:flex;gap:10px;">
                        <button class="fm-btn-danger" id="btn-delete-preview" style="flex:1;background:#555;">
                            👁️ Vorschau
                        </button>
                        <button class="fm-btn-danger" id="btn-delete-all" style="flex:1;background:#c0392b;">
                            🗑️ Löschen
                        </button>
                    </div>
                    
                    <div id="delete-result" style="margin-top:15px;padding:10px;border-radius:4px;display:none;"></div>
                </div>
            </div>
        `;
        
        container.querySelector('#btn-refresh-storage').onclick = () => {
            this.loadData();
            this.renderStorageTab(container);
        };
        
        // Delete Preview Button
        container.querySelector('#btn-delete-preview').onclick = async () => {
            const camera = container.querySelector('#delete-camera').value;
            const age = parseInt(container.querySelector('#delete-age').value);
            const includeAnalysis = container.querySelector('#delete-analysis').checked;
            const resultDiv = container.querySelector('#delete-result');
            
            // Count affected files
            let affectedCount = 0;
            const cutoffDate = age > 0 ? new Date(Date.now() - age * 24 * 60 * 60 * 1000) : null;
            
            if (this._events) {
                this._events.forEach(e => {
                    if (camera && e.cam !== camera) return;
                    if (cutoffDate && e.date >= cutoffDate) return;
                    affectedCount++;
                });
            }
            
            resultDiv.style.display = 'block';
            resultDiv.style.background = '#2c3e50';
            resultDiv.innerHTML = `
                <div style="font-weight:500;margin-bottom:5px;">📊 Vorschau:</div>
                <div>• ${affectedCount} Aufnahme(n) würden gelöscht</div>
                ${includeAnalysis ? '<div>• Zugehörige Analysen würden auch gelöscht</div>' : ''}
                ${camera ? `<div>• Nur Kamera: ${camera.replace(/_/g, ' ')}</div>` : '<div>• Alle Kameras</div>'}
                ${age > 0 ? `<div>• Älter als ${age} Tag(e)</div>` : '<div>• Alle Aufnahmen (kein Altersfilter!)</div>'}
            `;
        };
        
        // Delete Button
        container.querySelector('#btn-delete-all').onclick = async () => {
            const camera = container.querySelector('#delete-camera').value;
            const age = parseInt(container.querySelector('#delete-age').value);
            const includeAnalysis = container.querySelector('#delete-analysis').checked;
            const resultDiv = container.querySelector('#delete-result');
            
            // Confirmation dialog
            const msg = camera 
                ? `Wirklich alle Aufnahmen von "${camera.replace(/_/g, ' ')}" löschen?`
                : 'Wirklich ALLE Aufnahmen löschen?';
            
            if (!confirm(msg + (age === 0 ? '\n\n⚠️ ACHTUNG: Kein Altersfilter gesetzt!' : ''))) {
                return;
            }
            
            resultDiv.style.display = 'block';
            resultDiv.style.background = '#2c3e50';
            resultDiv.innerHTML = '<div style="text-align:center;">🔄 Lösche Aufnahmen...</div>';
            
            try {
                await this._hass.callService('rtsp_recorder', 'delete_all_recordings', {
                    camera: camera || undefined,
                    older_than_days: age,
                    include_analysis: includeAnalysis,
                    confirm: true
                });
                
                resultDiv.style.background = '#27ae60';
                resultDiv.innerHTML = `
                    <div style="font-weight:500;">✅ Erfolgreich gelöscht!</div>
                    <div style="margin-top:5px;">Aktualisiere Ansicht...</div>
                `;
                
                // Reload data after 1 second
                setTimeout(() => {
                    this.loadData();
                    this.renderStorageTab(container);
                }, 1000);
                
            } catch (e) {
                resultDiv.style.background = '#c0392b';
                resultDiv.innerHTML = `
                    <div style="font-weight:500;">❌ Fehler:</div>
                    <div>${e.message || 'Unbekannter Fehler'}</div>
                `;
            }
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
            // MED-010 Fix: Detailed error messages with troubleshooting hints
            let errorDetail = e.message || 'Unbekannter Fehler';
            let hint = '';
            
            if (errorDetail.includes('not found') || errorDetail.includes('404')) {
                hint = '<br><small>💡 Prüfe ob der Pfad existiert und die Integration korrekt konfiguriert ist.</small>';
            } else if (errorDetail.includes('permission') || errorDetail.includes('403')) {
                hint = '<br><small>💡 Berechtigungsfehler - prüfe die Dateiberechtigungen.</small>';
            } else if (errorDetail.includes('timeout') || errorDetail.includes('network')) {
                hint = '<br><small>💡 Netzwerkfehler - prüfe die Verbindung zu Home Assistant.</small>';
            } else if (errorDetail.includes('media_source')) {
                hint = '<br><small>💡 Media Source nicht verfügbar - stelle sicher dass die Integration geladen ist.</small>';
            }
            
            rtspError('loadData failed:', e);
            this.shadowRoot.querySelector('#list').innerHTML = `<div style="padding:20px;color:red;">Fehler beim Laden: ${errorDetail}${hint}<br><small style="color:#666;">Pfad: ${this._basePath}</small></div>`;
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
