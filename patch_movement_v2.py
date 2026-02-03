#!/usr/bin/env python3
import re

# Read file
with open('/config/www/rtsp-recorder-card.js', 'r', encoding='utf-8') as f:
    content = f.read()

changes_made = 0

# === Change 1: Add tab handler for "movement" ===
old_handler = """} else if (this._activeTab === 'people') {
            // People Tab
            this.renderPeopleTab(container);
        } else if (this._activeTab === 'performance') {"""

new_handler = """} else if (this._activeTab === 'people') {
            // People Tab
            this.renderPeopleTab(container);
        } else if (this._activeTab === 'movement') {
            // Movement Profile Tab
            this.renderMovementTab(container);
        } else if (this._activeTab === 'performance') {"""

if old_handler in content:
    content = content.replace(old_handler, new_handler)
    print("1. Added movement tab handler")
    changes_made += 1
else:
    print("1. SKIP: Tab handler pattern not found")

# === Change 2: Add renderMovementTab function before renderPeopleTab ===
insert_before = """    renderPeopleTab(container) {
        if (!this._peopleLoaded) {"""

movement_tab_function = '''    renderMovementTab(container) {
        container.innerHTML = `
            <div style="padding:20px;">
                <h3 style="margin:0 0 20px 0; color:var(--primary-text-color);">Bewegungsprofil</h3>
                <div style="margin-bottom:20px; display:flex; gap:10px; flex-wrap:wrap;">
                    <select id="movement-hours" style="padding:8px 12px; border-radius:8px; border:1px solid var(--divider-color); background:var(--card-background-color); color:var(--primary-text-color);">
                        <option value="1">Letzte Stunde</option>
                        <option value="6">Letzte 6 Stunden</option>
                        <option value="24" selected>Letzte 24 Stunden</option>
                        <option value="168">Letzte 7 Tage</option>
                    </select>
                    <button id="movement-refresh" style="padding:8px 16px; border-radius:8px; border:none; background:var(--primary-color); color:white; cursor:pointer;">Aktualisieren</button>
                </div>
                <div id="movement-content" style="color:#888;">Lade Bewegungsprofil...</div>
            </div>
        `;
        
        const hoursSelect = container.querySelector('#movement-hours');
        const refreshBtn = container.querySelector('#movement-refresh');
        const contentDiv = container.querySelector('#movement-content');
        
        const loadProfile = () => this._loadMovementProfile(contentDiv, parseInt(hoursSelect.value));
        
        hoursSelect.addEventListener('change', loadProfile);
        refreshBtn.addEventListener('click', loadProfile);
        
        loadProfile();
    }
    
    async _loadMovementProfile(container, hours) {
        container.textContent = 'Lade...';
        
        try {
            const result = await this._hass.callWS({
                type: 'rtsp_recorder/get_movement_profile',
                hours: hours
            });
            
            if (!result.movements || result.movements.length === 0) {
                container.innerHTML = '<div style="padding:20px; color:#888; text-align:center;">Keine Bewegungen im ausgewählten Zeitraum gefunden.</div>';
                return;
            }
            
            // Group by person
            const byPerson = {};
            result.movements.forEach(m => {
                if (!byPerson[m.name]) byPerson[m.name] = [];
                byPerson[m.name].push(m);
            });
            
            let html = '<div style="display:flex; flex-direction:column; gap:20px;">';
            
            for (const [name, movements] of Object.entries(byPerson)) {
                html += `
                    <div style="background:var(--card-background-color); border-radius:12px; padding:16px; border:1px solid var(--divider-color);">
                        <h4 style="margin:0 0 12px 0; color:var(--primary-color);">${this._escapeHtml(name)}</h4>
                        <div style="display:flex; flex-direction:column; gap:8px;">
                `;
                
                movements.slice(0, 20).forEach(m => {
                    const time = new Date(m.timestamp).toLocaleString('de-DE');
                    const confidence = Math.round(m.confidence * 100);
                    html += `
                        <div style="display:flex; align-items:center; gap:12px; padding:8px; background:var(--secondary-background-color); border-radius:8px;">
                            <span style="font-size:20px;">📍</span>
                            <div style="flex:1;">
                                <div style="font-weight:500; color:var(--primary-text-color);">${this._escapeHtml(m.camera)}</div>
                                <div style="font-size:12px; color:#888;">${time} • ${confidence}%</div>
                            </div>
                        </div>
                    `;
                });
                
                if (movements.length > 20) {
                    html += `<div style="text-align:center; color:#888; padding:8px;">... und ${movements.length - 20} weitere</div>`;
                }
                
                html += '</div></div>';
            }
            
            html += '</div>';
            container.innerHTML = html;
            
        } catch (e) {
            container.innerHTML = '<div style="padding:20px; color:#f44336; text-align:center;">Fehler beim Laden: ' + this._escapeHtml(e.message) + '</div>';
        }
    }

    ''' + insert_before

if insert_before in content:
    content = content.replace(insert_before, movement_tab_function)
    print("2. Added renderMovementTab function")
    changes_made += 1
else:
    print("2. SKIP: Function insertion point not found")

# Write
with open('/config/www/rtsp-recorder-card.js', 'w', encoding='utf-8') as f:
    f.write(content)

print(f"\nTotal changes: {changes_made}")
