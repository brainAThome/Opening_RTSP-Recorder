#!/usr/bin/env python3
"""Add person chart - using exact pattern from file"""

with open('/config/www/rtsp-recorder-card.js', 'r', encoding='utf-8') as f:
    content = f.read()

# Find the exact pattern with potential whitespace variations
old_pattern = """cameraHtml += '</div>';
        
        // Hour distribution chart (24h)"""

new_pattern = """cameraHtml += '</div>';

        // Person bar chart
        const personCounts = {};
        for (const [name, movements] of Object.entries(byPerson)) {
            personCounts[name] = movements.length;
        }
        const maxPersonCount = Math.max(...Object.values(personCounts), 1);
        
        let personHtml = '<div style="margin-bottom:30px;"><h4 style="margin:0 0 16px 0; color:var(--primary-text-color);">👤 Erkennungen pro Person</h4>';
        for (const [person, count] of Object.entries(personCounts).sort((a, b) => b[1] - a[1])) {
            const pct = (count / maxPersonCount) * 100;
            personHtml += `
                <div style="margin-bottom:8px;">
                    <div style="display:flex; justify-content:space-between; margin-bottom:4px;">
                        <span style="color:var(--primary-text-color);">${this._escapeHtml(person)}</span>
                        <span style="color:#888;">${count}x</span>
                    </div>
                    <div style="background:var(--divider-color); border-radius:4px; height:24px; overflow:hidden;">
                        <div style="background:linear-gradient(90deg, #9c27b0, #e91e63); width:${pct}%; height:100%; border-radius:4px; transition:width 0.5s;"></div>
                    </div>
                </div>
            `;
        }
        personHtml += '</div>';
        
        // Hour distribution chart (24h)"""

if old_pattern in content:
    content = content.replace(old_pattern, new_pattern)
    with open('/config/www/rtsp-recorder-card.js', 'w', encoding='utf-8') as f:
        f.write(content)
    print("SUCCESS: Added person chart")
else:
    print("Pattern not found, trying alternative...")
    # Try with different whitespace
    import re
    pattern = r"cameraHtml \+= '</div>';\s*\n\s*// Hour distribution chart"
    if re.search(pattern, content):
        content = re.sub(pattern, """cameraHtml += '</div>';

        // Person bar chart
        const personCounts = {};
        for (const [name, movements] of Object.entries(byPerson)) {
            personCounts[name] = movements.length;
        }
        const maxPersonCount = Math.max(...Object.values(personCounts), 1);
        
        let personHtml = '<div style="margin-bottom:30px;"><h4 style="margin:0 0 16px 0; color:var(--primary-text-color);">👤 Erkennungen pro Person</h4>';
        for (const [person, count] of Object.entries(personCounts).sort((a, b) => b[1] - a[1])) {
            const pct = (count / maxPersonCount) * 100;
            personHtml += `
                <div style="margin-bottom:8px;">
                    <div style="display:flex; justify-content:space-between; margin-bottom:4px;">
                        <span style="color:var(--primary-text-color);">${this._escapeHtml(person)}</span>
                        <span style="color:#888;">${count}x</span>
                    </div>
                    <div style="background:var(--divider-color); border-radius:4px; height:24px; overflow:hidden;">
                        <div style="background:linear-gradient(90deg, #9c27b0, #e91e63); width:${pct}%; height:100%; border-radius:4px; transition:width 0.5s;"></div>
                    </div>
                </div>
            `;
        }
        personHtml += '</div>';

        // Hour distribution chart""", content)
        with open('/config/www/rtsp-recorder-card.js', 'w', encoding='utf-8') as f:
            f.write(content)
        print("SUCCESS: Added person chart (regex)")
    else:
        print("ERROR: Could not find pattern")
