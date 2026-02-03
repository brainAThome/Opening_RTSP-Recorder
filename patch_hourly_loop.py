#!/usr/bin/env python3
"""Add hourly data collection per camera/person in forEach loop"""

with open('/config/www/rtsp-recorder-card.js', 'r', encoding='utf-8') as f:
    content = f.read()

old_loop = """// Parse time (field name from backend is "time")
                const date = new Date(m.time);
                if (!isNaN(date.getTime())) {
                    const hourKey = date.getHours();
                    if (!byHour[hourKey]) byHour[hourKey] = 0;
                    byHour[hourKey]++;
                }
            });"""

new_loop = """// Parse time (field name from backend is "time")
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
            });"""

if old_loop in content:
    content = content.replace(old_loop, new_loop)
    with open('/config/www/rtsp-recorder-card.js', 'w', encoding='utf-8') as f:
        f.write(content)
    print("SUCCESS: Added hourly data collection per camera/person")
else:
    print("Pattern not found")
