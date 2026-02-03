#!/usr/bin/env python3
"""Patch: Fix movement profile field names and add timeline chart visualization"""

with open('/config/www/rtsp-recorder-card.js', 'r', encoding='utf-8') as f:
    content = f.read()

# Find and replace the renderMovementTab and _loadMovementProfile functions
old_movement_tab = '''    renderMovementTab(container) {
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

    renderPeopleTab(container) {'''

new_movement_tab = '''    renderMovementTab(container) {
        container.innerHTML = `
            <div style="padding:20px;">
                <h3 style="margin:0 0 20px 0; color:var(--primary-text-color);">Bewegungsprofil</h3>
                <div style="margin-bottom:20px; display:flex; gap:10px; flex-wrap:wrap; align-items:center;">
                    <select id="movement-hours" style="padding:8px 12px; border-radius:8px; border:1px solid var(--divider-color); background:var(--card-background-color); color:var(--primary-text-color);">
                        <option value="1">Letzte Stunde</option>
                        <option value="6">Letzte 6 Stunden</option>
                        <option value="24" selected>Letzte 24 Stunden</option>
                        <option value="168">Letzte 7 Tage</option>
                    </select>
                    <select id="movement-view" style="padding:8px 12px; border-radius:8px; border:1px solid var(--divider-color); background:var(--card-background-color); color:var(--primary-text-color);">
                        <option value="timeline" selected>Timeline</option>
                        <option value="chart">Diagramm</option>
                        <option value="list">Liste</option>
                    </select>
                    <button id="movement-refresh" style="padding:8px 16px; border-radius:8px; border:none; background:var(--primary-color); color:white; cursor:pointer;">⟳ Aktualisieren</button>
                </div>
                <div id="movement-content" style="color:#888;">Lade Bewegungsprofil...</div>
            </div>
        `;
        
        const hoursSelect = container.querySelector('#movement-hours');
        const viewSelect = container.querySelector('#movement-view');
        const refreshBtn = container.querySelector('#movement-refresh');
        const contentDiv = container.querySelector('#movement-content');
        
        const loadProfile = () => this._loadMovementProfile(contentDiv, parseInt(hoursSelect.value), viewSelect.value);
        
        hoursSelect.addEventListener('change', loadProfile);
        viewSelect.addEventListener('change', loadProfile);
        refreshBtn.addEventListener('click', loadProfile);
        
        loadProfile();
    }
    
    async _loadMovementProfile(container, hours, viewMode = 'timeline') {
        container.textContent = 'Lade...';
        
        try {
            const result = await this._hass.callWS({
                type: 'rtsp_recorder/get_movement_profile',
                hours: hours
            });
            
            if (!result.movements || result.movements.length === 0) {
                container.innerHTML = '<div style="padding:40px; color:#888; text-align:center;"><div style="font-size:48px; margin-bottom:16px;">📭</div>Keine Bewegungen im ausgewählten Zeitraum gefunden.</div>';
                return;
            }
            
            // Group by person (use correct field name from backend: "person" not "name")
            const byPerson = {};
            const byCamera = {};
            const byHour = {};
            
            result.movements.forEach(m => {
                const personName = m.person || 'Unbekannt';
                const cameraName = m.camera || 'Unbekannt';
                
                if (!byPerson[personName]) byPerson[personName] = [];
                byPerson[personName].push(m);
                
                if (!byCamera[cameraName]) byCamera[cameraName] = 0;
                byCamera[cameraName]++;
                
                // Parse time (use correct field name: "time" not "timestamp")
                const date = new Date(m.time);
                if (!isNaN(date.getTime())) {
                    const hourKey = date.getHours();
                    if (!byHour[hourKey]) byHour[hourKey] = 0;
                    byHour[hourKey]++;
                }
            });
            
            if (viewMode === 'chart') {
                this._renderMovementChart(container, byCamera, byHour, result.total);
            } else if (viewMode === 'list') {
                this._renderMovementList(container, byPerson);
            } else {
                this._renderMovementTimeline(container, byPerson, result.movements);
            }
            
        } catch (e) {
            container.innerHTML = '<div style="padding:20px; color:#f44336; text-align:center;">Fehler beim Laden: ' + this._escapeHtml(e.message || String(e)) + '</div>';
        }
    }
    
    _renderMovementChart(container, byCamera, byHour, total) {
        const maxCameraCount = Math.max(...Object.values(byCamera), 1);
        const maxHourCount = Math.max(...Object.values(byHour), 1);
        
        // Camera bar chart
        let cameraHtml = '<div style="margin-bottom:30px;"><h4 style="margin:0 0 16px 0; color:var(--primary-text-color);">📷 Erkennungen pro Kamera</h4>';
        for (const [camera, count] of Object.entries(byCamera).sort((a, b) => b[1] - a[1])) {
            const pct = (count / maxCameraCount) * 100;
            cameraHtml += `
                <div style="margin-bottom:8px;">
                    <div style="display:flex; justify-content:space-between; margin-bottom:4px;">
                        <span style="color:var(--primary-text-color);">${this._escapeHtml(camera)}</span>
                        <span style="color:#888;">${count}x</span>
                    </div>
                    <div style="background:var(--divider-color); border-radius:4px; height:24px; overflow:hidden;">
                        <div style="background:linear-gradient(90deg, #03a9f4, #00bcd4); width:${pct}%; height:100%; border-radius:4px; transition:width 0.5s;"></div>
                    </div>
                </div>
            `;
        }
        cameraHtml += '</div>';
        
        // Hour distribution chart (24h)
        let hourHtml = '<div><h4 style="margin:0 0 16px 0; color:var(--primary-text-color);">🕐 Aktivität nach Uhrzeit</h4>';
        hourHtml += '<div style="display:flex; align-items:flex-end; gap:4px; height:120px; padding:10px 0;">';
        for (let h = 0; h < 24; h++) {
            const count = byHour[h] || 0;
            const pct = maxHourCount > 0 ? (count / maxHourCount) * 100 : 0;
            const barColor = count > 0 ? 'linear-gradient(180deg, #4caf50, #8bc34a)' : 'var(--divider-color)';
            hourHtml += `
                <div style="flex:1; display:flex; flex-direction:column; align-items:center; gap:4px;">
                    <div style="width:100%; background:${barColor}; height:${Math.max(pct, 2)}%; border-radius:2px 2px 0 0; min-height:4px;" title="${count} Erkennungen um ${h}:00"></div>
                    <span style="font-size:9px; color:#888;">${h}</span>
                </div>
            `;
        }
        hourHtml += '</div></div>';
        
        // Summary stats
        const statsHtml = `
            <div style="display:grid; grid-template-columns:repeat(3, 1fr); gap:16px; margin-bottom:24px;">
                <div style="background:var(--card-background-color); border-radius:12px; padding:16px; text-align:center; border:1px solid var(--divider-color);">
                    <div style="font-size:32px; font-weight:bold; color:var(--primary-color);">${total}</div>
                    <div style="color:#888; font-size:12px;">Gesamt</div>
                </div>
                <div style="background:var(--card-background-color); border-radius:12px; padding:16px; text-align:center; border:1px solid var(--divider-color);">
                    <div style="font-size:32px; font-weight:bold; color:#4caf50;">${Object.keys(byCamera).length}</div>
                    <div style="color:#888; font-size:12px;">Kameras</div>
                </div>
                <div style="background:var(--card-background-color); border-radius:12px; padding:16px; text-align:center; border:1px solid var(--divider-color);">
                    <div style="font-size:32px; font-weight:bold; color:#ff9800;">${Object.keys(byHour).length}</div>
                    <div style="color:#888; font-size:12px;">Aktive Stunden</div>
                </div>
            </div>
        `;
        
        container.innerHTML = statsHtml + cameraHtml + hourHtml;
    }
    
    _renderMovementTimeline(container, byPerson, movements) {
        let html = '<div style="display:flex; flex-direction:column; gap:24px;">';
        
        for (const [name, personMovements] of Object.entries(byPerson)) {
            // Get unique cameras for this person
            const cameras = [...new Set(personMovements.map(m => m.camera))];
            const lastSeen = personMovements[0];
            const lastTime = new Date(lastSeen.time);
            const lastTimeStr = !isNaN(lastTime.getTime()) ? lastTime.toLocaleString('de-DE') : 'Unbekannt';
            
            html += `
                <div style="background:var(--card-background-color); border-radius:12px; padding:16px; border:1px solid var(--divider-color);">
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:16px;">
                        <h4 style="margin:0; color:var(--primary-color); display:flex; align-items:center; gap:8px;">
                            <span style="font-size:24px;">👤</span>
                            ${this._escapeHtml(name)}
                        </h4>
                        <span style="color:#888; font-size:12px;">${personMovements.length} Erkennungen</span>
                    </div>
                    
                    <div style="display:flex; flex-wrap:wrap; gap:8px; margin-bottom:16px;">
                        ${cameras.map(c => `<span style="background:var(--primary-color); color:white; padding:4px 12px; border-radius:16px; font-size:12px;">📷 ${this._escapeHtml(c)}</span>`).join('')}
                    </div>
                    
                    <div style="position:relative; padding-left:20px; border-left:2px solid var(--divider-color);">
            `;
            
            // Show last 10 movements as timeline
            personMovements.slice(0, 10).forEach((m, i) => {
                const time = new Date(m.time);
                const timeStr = !isNaN(time.getTime()) ? time.toLocaleString('de-DE') : 'Unbekannt';
                const confidence = m.confidence ? Math.round(m.confidence * 100) : 0;
                const isRecent = i === 0;
                
                html += `
                    <div style="position:relative; padding:8px 0 8px 16px; ${isRecent ? 'opacity:1;' : 'opacity:0.7;'}">
                        <div style="position:absolute; left:-7px; top:12px; width:12px; height:12px; border-radius:50%; background:${isRecent ? '#4caf50' : 'var(--divider-color)'}; border:2px solid var(--card-background-color);"></div>
                        <div style="font-weight:${isRecent ? '600' : '400'}; color:var(--primary-text-color);">${this._escapeHtml(m.camera)}</div>
                        <div style="font-size:12px; color:#888;">${timeStr} • ${confidence}%</div>
                    </div>
                `;
            });
            
            if (personMovements.length > 10) {
                html += `<div style="padding:8px 0 0 16px; color:#888; font-size:12px;">... und ${personMovements.length - 10} weitere</div>`;
            }
            
            html += '</div></div>';
        }
        
        html += '</div>';
        container.innerHTML = html;
    }
    
    _renderMovementList(container, byPerson) {
        let html = '<div style="display:flex; flex-direction:column; gap:16px;">';
        
        for (const [name, movements] of Object.entries(byPerson)) {
            html += `
                <div style="background:var(--card-background-color); border-radius:12px; padding:16px; border:1px solid var(--divider-color);">
                    <h4 style="margin:0 0 12px 0; color:var(--primary-color);">👤 ${this._escapeHtml(name)}</h4>
                    <div style="display:flex; flex-direction:column; gap:8px; max-height:300px; overflow-y:auto;">
            `;
            
            movements.slice(0, 30).forEach(m => {
                const time = new Date(m.time);
                const timeStr = !isNaN(time.getTime()) ? time.toLocaleString('de-DE') : 'Unbekannt';
                const confidence = m.confidence ? Math.round(m.confidence * 100) : 0;
                html += `
                    <div style="display:flex; align-items:center; gap:12px; padding:10px; background:var(--secondary-background-color); border-radius:8px;">
                        <span style="font-size:20px;">📍</span>
                        <div style="flex:1;">
                            <div style="font-weight:500; color:var(--primary-text-color);">${this._escapeHtml(m.camera)}</div>
                            <div style="font-size:12px; color:#888;">${timeStr} • ${confidence}%</div>
                        </div>
                    </div>
                `;
            });
            
            if (movements.length > 30) {
                html += `<div style="text-align:center; color:#888; padding:8px;">... und ${movements.length - 30} weitere</div>`;
            }
            
            html += '</div></div>';
        }
        
        html += '</div>';
        container.innerHTML = html;
    }

    renderPeopleTab(container) {'''

if old_movement_tab in content:
    content = content.replace(old_movement_tab, new_movement_tab)
    with open('/config/www/rtsp-recorder-card.js', 'w', encoding='utf-8') as f:
        f.write(content)
    print('SUCCESS: Movement profile updated with charts and fixed field names')
else:
    print('ERROR: Old movement tab pattern not found')
    # Try to find what we have
    if 'renderMovementTab' in content:
        print('renderMovementTab exists but pattern differs')
    else:
        print('renderMovementTab not found at all')
