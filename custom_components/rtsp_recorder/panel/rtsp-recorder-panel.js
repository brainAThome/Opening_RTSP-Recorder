// Opening RTSP Recorder — Sidebar Panel (v1.4.0)
// =============================================================================
// Thin host: the sidebar panel shows the SAME dashboard card (rtsp-recorder-card)
// so there is exactly ONE settings/recordings UI to maintain. All settings live
// in the card's own menu. This panel only embeds the card (with the integration's
// storage_path as base_path) and forwards `hass`.
//
// Registration of this panel is gated by the `sidebar_panel_enabled` setting in
// the integration (see __init__.py); the toggle lives in the card menu (Allgemein).
// =============================================================================

class RtspRecorderPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    const style = document.createElement("style");
    style.textContent =
      ":host{display:block;height:100%;overflow:auto;background:var(--primary-background-color);}";
    this.shadowRoot.appendChild(style);
  }

  set hass(hass) {
    this._hass = hass;
    if (this._card) {
      this._card.hass = hass;
    } else {
      this._build();
    }
  }
  set narrow(v) { this._narrow = v; }
  set route(v) { this._route = v; }
  set panel(v) { this._panel = v; }

  connectedCallback() {
    if (this._hass && !this._card) this._build();
  }

  async _build() {
    if (this._building || !this._hass) return;
    this._building = true;
    // Ensure the card element is defined (it is normally loaded globally via
    // add_extra_js_url; import as a fallback so the panel works standalone).
    if (!customElements.get("rtsp-recorder-card")) {
      try { await import("/local/rtsp-recorder-card.js"); } catch (e) { /* ignore */ }
    }
    // Use the integration's configured storage_path as the card's base_path.
    let base = "/media/rtsp_recordings";
    try {
      const g = await this._hass.callWS({ type: "rtsp_recorder/get_global_settings" });
      if (g && g.settings && g.settings.storage_path) base = g.settings.storage_path;
    } catch (e) { /* keep default */ }

    const card = document.createElement("rtsp-recorder-card");
    try { card.setConfig({ base_path: base }); } catch (e) { /* card uses defaults */ }
    card.hass = this._hass;
    this.shadowRoot.appendChild(card);
    this._card = card;
  }
}

if (!customElements.get("rtsp-recorder-panel")) {
  customElements.define("rtsp-recorder-panel", RtspRecorderPanel);
}
