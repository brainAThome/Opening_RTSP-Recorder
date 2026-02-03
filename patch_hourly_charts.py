#!/usr/bin/env python3
"""Add separate hourly activity charts for cameras and persons"""

with open('/config/www/rtsp-recorder-card.js', 'r', encoding='utf-8') as f:
    content = f.read()

changes = 0

# 1. Update data processing to include hourly data per camera and per person
old_processing = """// Group by person (field name from backend is "person")
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

                // Parse time (field name from backend is "time")
                const date = new Date(m.time);
                if (!isNaN(date.getTime())) {
                    const hourKey = date.getHours();
                    if (!byHour[hourKey]) byHour[hourKey] = 0;
                    byHour[hourKey]++;
                }
            });

            if (viewMode === 'chart') {
                this._renderMovementChart(container, byPerson, byCamera, byHour, result.total);"""

new_processing = """// Group by person (field name from backend is "person")
            const byPerson = {};
            const byCamera = {};
            const byHour = {};
            const byHourPerCamera = {};
            const byHourPerPerson = {};

            result.movements.forEach(m => {
                const personName = m.person || 'Unbekannt';
                const cameraName = m.camera || 'Unbekannt';

                if (!byPerson[personName]) byPerson[personName] = [];
                byPerson[personName].push(m);

                if (!byCamera[cameraName]) byCamera[cameraName] = 0;
                byCamera[cameraName]++;

                // Parse time (field name from backend is "time")
                const date = new Date(m.time);
                if (!isNaN(date.getTime())) {
                    const hourKey = date.getHours();
                    if (!byHour[hourKey]) byHour[hourKey] = 0;
                    byHour[hourKey]++;
                    
                    // Per camera hourly
                    if (!byHourPerCamera[cameraName]) byHourPerCamera[cameraName] = {};
                    if (!byHourPerCamera[cameraName][hourKey]) byHourPerCamera[cameraName][hourKey] = 0;
                    byHourPerCamera[cameraName][hourKey]++;
                    
                    // Per person hourly
                    if (!byHourPerPerson[personName]) byHourPerPerson[personName] = {};
                    if (!byHourPerPerson[personName][hourKey]) byHourPerPerson[personName][hourKey] = 0;
                    byHourPerPerson[personName][hourKey]++;
                }
            });

            if (viewMode === 'chart') {
                this._renderMovementChart(container, byPerson, byCamera, byHour, byHourPerCamera, byHourPerPerson, result.total);"""

if old_processing in content:
    content = content.replace(old_processing, new_processing)
    print("1. Updated data processing with per-camera and per-person hourly stats")
    changes += 1

# 2. Update function signature
old_sig = "_renderMovementChart(container, byPerson, byCamera, byHour, total) {"
new_sig = "_renderMovementChart(container, byPerson, byCamera, byHour, byHourPerCamera, byHourPerPerson, total) {"

if old_sig in content:
    content = content.replace(old_sig, new_sig)
    print("2. Updated function signature")
    changes += 1

# 3. Replace the simple hour chart with expanded camera/person hourly charts
old_hour_chart = """// Hour distribution chart (24h)
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
        hourHtml += '</div></div>';"""

new_hour_chart = """// Hourly activity per Camera
        let hourCameraHtml = '<div style="margin-bottom:30px;"><h4 style="margin:0 0 16px 0; color:var(--primary-text-color);">📷 Aktivität pro Kamera (24h)</h4>';
        for (const [camera, hourData] of Object.entries(byHourPerCamera)) {
            const maxH = Math.max(...Object.values(hourData), 1);
            hourCameraHtml += `<div style="margin-bottom:16px;"><div style="color:var(--primary-text-color); margin-bottom:8px; font-size:13px;">${this._escapeHtml(camera)}</div>`;
            hourCameraHtml += '<div style="display:flex; align-items:flex-end; gap:2px; height:60px;">';
            for (let h = 0; h < 24; h++) {
                const count = hourData[h] || 0;
                const pct = maxH > 0 ? (count / maxH) * 100 : 0;
                const barColor = count > 0 ? 'linear-gradient(180deg, #03a9f4, #00bcd4)' : 'var(--divider-color)';
                hourCameraHtml += `<div style="flex:1; background:${barColor}; height:${Math.max(pct, 3)}%; border-radius:2px 2px 0 0; min-height:3px;" title="${camera}: ${count}x um ${h}:00"></div>`;
            }
            hourCameraHtml += '</div>';
            hourCameraHtml += '<div style="display:flex; justify-content:space-between; font-size:8px; color:#666; margin-top:2px;"><span>0</span><span>6</span><span>12</span><span>18</span><span>23</span></div></div>';
        }
        hourCameraHtml += '</div>';

        // Hourly activity per Person
        let hourPersonHtml = '<div style="margin-bottom:30px;"><h4 style="margin:0 0 16px 0; color:var(--primary-text-color);">👤 Aktivität pro Person (24h)</h4>';
        for (const [person, hourData] of Object.entries(byHourPerPerson)) {
            const maxH = Math.max(...Object.values(hourData), 1);
            hourPersonHtml += `<div style="margin-bottom:16px;"><div style="color:var(--primary-text-color); margin-bottom:8px; font-size:13px;">${this._escapeHtml(person)}</div>`;
            hourPersonHtml += '<div style="display:flex; align-items:flex-end; gap:2px; height:60px;">';
            for (let h = 0; h < 24; h++) {
                const count = hourData[h] || 0;
                const pct = maxH > 0 ? (count / maxH) * 100 : 0;
                const barColor = count > 0 ? 'linear-gradient(180deg, #9c27b0, #e91e63)' : 'var(--divider-color)';
                hourPersonHtml += `<div style="flex:1; background:${barColor}; height:${Math.max(pct, 3)}%; border-radius:2px 2px 0 0; min-height:3px;" title="${person}: ${count}x um ${h}:00"></div>`;
            }
            hourPersonHtml += '</div>';
            hourPersonHtml += '<div style="display:flex; justify-content:space-between; font-size:8px; color:#666; margin-top:2px;"><span>0</span><span>6</span><span>12</span><span>18</span><span>23</span></div></div>';
        }
        hourPersonHtml += '</div>';

        // Combined hourly overview
        let hourHtml = '<div><h4 style="margin:0 0 16px 0; color:var(--primary-text-color);">🕐 Gesamt-Aktivität (24h)</h4>';
        hourHtml += '<div style="display:flex; align-items:flex-end; gap:4px; height:80px; padding:10px 0;">';
        for (let h = 0; h < 24; h++) {
            const count = byHour[h] || 0;
            const pct = maxHourCount > 0 ? (count / maxHourCount) * 100 : 0;
            const barColor = count > 0 ? 'linear-gradient(180deg, #4caf50, #8bc34a)' : 'var(--divider-color)';
            hourHtml += `
                <div style="flex:1; display:flex; flex-direction:column; align-items:center; gap:2px;">
                    <div style="width:100%; background:${barColor}; height:${Math.max(pct, 3)}%; border-radius:2px 2px 0 0; min-height:3px;" title="${count} Erkennungen um ${h}:00"></div>
                    <span style="font-size:8px; color:#888;">${h}</span>
                </div>
            `;
        }
        hourHtml += '</div></div>';"""

if old_hour_chart in content:
    content = content.replace(old_hour_chart, new_hour_chart)
    print("3. Replaced hour chart with per-camera and per-person charts")
    changes += 1

# 4. Update the final HTML output to include new charts
old_output = "container.innerHTML = statsHtml + personHtml + cameraHtml + hourHtml;"
new_output = "container.innerHTML = statsHtml + personHtml + cameraHtml + hourPersonHtml + hourCameraHtml + hourHtml;"

if old_output in content:
    content = content.replace(old_output, new_output)
    print("4. Updated HTML output to include new hourly charts")
    changes += 1

with open('/config/www/rtsp-recorder-card.js', 'w', encoding='utf-8') as f:
    f.write(content)

print(f"\nTotal changes: {changes}")
