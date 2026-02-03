#!/usr/bin/env python3
"""Add person chart to movement profile"""

with open('/config/www/rtsp-recorder-card.js', 'r', encoding='utf-8') as f:
    content = f.read()

changes = 0

# 1. Update function call to include byPerson
old_call = "this._renderMovementChart(container, byCamera, byHour, result.total);"
new_call = "this._renderMovementChart(container, byPerson, byCamera, byHour, result.total);"

if old_call in content:
    content = content.replace(old_call, new_call)
    print("1. Updated function call to include byPerson")
    changes += 1

# 2. Update function signature
old_sig = "_renderMovementChart(container, byCamera, byHour, total) {"
new_sig = "_renderMovementChart(container, byPerson, byCamera, byHour, total) {"

if old_sig in content:
    content = content.replace(old_sig, new_sig)
    print("2. Updated function signature")
    changes += 1

# 3. Add person chart after camera chart - find the right spot
old_chart_end = """cameraHtml += '</div>';

        // Hour distribution chart (24h)"""

# Create person count from byPerson
new_chart = """cameraHtml += '</div>';

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

if old_chart_end in content:
    content = content.replace(old_chart_end, new_chart)
    print("3. Added person bar chart")
    changes += 1

# 4. Update stats to include persons count and update final HTML output
old_stats = """// Summary stats
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
        
        container.innerHTML = statsHtml + cameraHtml + hourHtml;"""

new_stats = """// Summary stats
        const statsHtml = `
            <div style="display:grid; grid-template-columns:repeat(4, 1fr); gap:12px; margin-bottom:24px;">
                <div style="background:var(--card-background-color); border-radius:12px; padding:16px; text-align:center; border:1px solid var(--divider-color);">
                    <div style="font-size:28px; font-weight:bold; color:var(--primary-color);">${total}</div>
                    <div style="color:#888; font-size:11px;">Gesamt</div>
                </div>
                <div style="background:var(--card-background-color); border-radius:12px; padding:16px; text-align:center; border:1px solid var(--divider-color);">
                    <div style="font-size:28px; font-weight:bold; color:#9c27b0;">${Object.keys(byPerson).length}</div>
                    <div style="color:#888; font-size:11px;">Personen</div>
                </div>
                <div style="background:var(--card-background-color); border-radius:12px; padding:16px; text-align:center; border:1px solid var(--divider-color);">
                    <div style="font-size:28px; font-weight:bold; color:#4caf50;">${Object.keys(byCamera).length}</div>
                    <div style="color:#888; font-size:11px;">Kameras</div>
                </div>
                <div style="background:var(--card-background-color); border-radius:12px; padding:16px; text-align:center; border:1px solid var(--divider-color);">
                    <div style="font-size:28px; font-weight:bold; color:#ff9800;">${Object.keys(byHour).length}</div>
                    <div style="color:#888; font-size:11px;">Aktive Std.</div>
                </div>
            </div>
        `;
        
        container.innerHTML = statsHtml + personHtml + cameraHtml + hourHtml;"""

if old_stats in content:
    content = content.replace(old_stats, new_stats)
    print("4. Updated stats grid and added personHtml to output")
    changes += 1

with open('/config/www/rtsp-recorder-card.js', 'w', encoding='utf-8') as f:
    f.write(content)

print(f"\nTotal changes: {changes}")
