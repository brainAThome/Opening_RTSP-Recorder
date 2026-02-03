#!/usr/bin/env python3
"""Fix: Add hourly data per camera/person and update function call"""

with open('/config/www/rtsp-recorder-card.js', 'r', encoding='utf-8') as f:
    content = f.read()

changes = 0

# Fix the data processing - add per camera/person hourly tracking
old_code = """// Group by person (field name from backend is "person")
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

new_code = """// Group by person (field name from backend is "person")
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

if old_code in content:
    content = content.replace(old_code, new_code)
    print("1. Updated data processing and function call")
    changes += 1
else:
    print("1. Pattern not found - trying with more whitespace tolerance")
    # Check if partial match
    if "byHourPerCamera" in content:
        print("   Already contains byHourPerCamera - skipping")
    else:
        print("   ERROR: Could not find pattern")

with open('/config/www/rtsp-recorder-card.js', 'w', encoding='utf-8') as f:
    f.write(content)

print(f"\nTotal changes: {changes}")
