/**
 * RTSP Recorder - Overlay Performance Test Script
 * 
 * ANWENDUNG:
 * 1. Öffne Home Assistant Dashboard mit RTSP Recorder Card
 * 2. Öffne Browser DevTools (F12)
 * 3. Kopiere diesen gesamten Code in die Console
 * 4. Drücke Enter
 * 5. Starte ein Video mit Overlay
 * 6. Nach 10 Sekunden erscheint der Performance-Report
 * 
 * Der Test misst:
 * - FPS (Frames pro Sekunde)
 * - Frame-Zeit (wie lange jedes Frame dauert)
 * - Jank-Events (Frames > 16.67ms = dropped frames)
 * - Canvas-Größe und Pixel-Durchsatz
 */

(function() {
    'use strict';
    
    console.log('%c[Overlay-Perf-Test] Starte Performance-Messung...', 'color: #00ff00; font-weight: bold');
    
    // Performance-Daten
    const perfData = {
        startTime: performance.now(),
        frameCount: 0,
        frameTimes: [],
        jankCount: 0,
        lastFrameTime: performance.now(),
        canvasDraws: 0,
        canvasPixels: 0,
        reportInterval: 10000, // 10 Sekunden
        isRunning: true
    };
    
    // Finde das Overlay-Canvas
    function findOverlayCanvas() {
        // Suche nach Canvas mit overlay-bezogenen Eigenschaften
        const allCanvas = document.querySelectorAll('canvas');
        for (const canvas of allCanvas) {
            // RTSP Recorder Overlay hat typischerweise pointer-events: none
            const style = getComputedStyle(canvas);
            if (style.pointerEvents === 'none' && style.position === 'absolute') {
                return canvas;
            }
        }
        // Fallback: erstes Canvas im rtsp-recorder-card
        const card = document.querySelector('rtsp-recorder-card');
        if (card && card.shadowRoot) {
            return card.shadowRoot.querySelector('canvas');
        }
        return allCanvas[0];
    }
    
    const overlayCanvas = findOverlayCanvas();
    if (overlayCanvas) {
        console.log('%c[Overlay-Perf-Test] Overlay-Canvas gefunden:', 'color: #00ff00', 
            overlayCanvas.width + 'x' + overlayCanvas.height);
    } else {
        console.warn('%c[Overlay-Perf-Test] Kein Overlay-Canvas gefunden!', 'color: #ff0000');
    }
    
    // Hook requestAnimationFrame um Frame-Timing zu messen
    const originalRAF = window.requestAnimationFrame;
    let rafCallCount = 0;
    
    window.requestAnimationFrame = function(callback) {
        rafCallCount++;
        return originalRAF.call(window, function(timestamp) {
            const now = performance.now();
            const frameDelta = now - perfData.lastFrameTime;
            
            if (perfData.isRunning && frameDelta > 0) {
                perfData.frameCount++;
                perfData.frameTimes.push(frameDelta);
                
                // Jank = Frame dauert länger als 16.67ms (60fps Ziel)
                if (frameDelta > 16.67) {
                    perfData.jankCount++;
                }
                
                perfData.lastFrameTime = now;
            }
            
            callback(timestamp);
        });
    };
    
    // Canvas-Draw-Tracking via MutationObserver (für Canvas-Änderungen)
    let lastImageData = null;
    function checkCanvasChanged() {
        if (!overlayCanvas || !perfData.isRunning) return;
        
        try {
            const ctx = overlayCanvas.getContext('2d');
            if (!ctx) return;
            
            // Nur ein kleiner Sample-Bereich um Performance nicht zu beeinflussen
            const sampleSize = Math.min(10, overlayCanvas.width, overlayCanvas.height);
            if (sampleSize <= 0) return;
            
            const imageData = ctx.getImageData(0, 0, sampleSize, sampleSize);
            const dataStr = Array.from(imageData.data.slice(0, 100)).join(',');
            
            if (lastImageData !== dataStr) {
                perfData.canvasDraws++;
                perfData.canvasPixels += overlayCanvas.width * overlayCanvas.height;
                lastImageData = dataStr;
            }
        } catch (e) {
            // Canvas möglicherweise cross-origin
        }
    }
    
    // Polling für Canvas-Änderungen (alle 100ms)
    const canvasCheckInterval = setInterval(checkCanvasChanged, 100);
    
    // Performance-Report generieren
    function generateReport() {
        perfData.isRunning = false;
        clearInterval(canvasCheckInterval);
        
        // Restore original RAF
        window.requestAnimationFrame = originalRAF;
        
        const elapsed = (performance.now() - perfData.startTime) / 1000;
        const avgFPS = perfData.frameCount / elapsed;
        
        // Frame-Zeit-Statistiken
        const frameTimes = perfData.frameTimes;
        const avgFrameTime = frameTimes.length > 0 
            ? frameTimes.reduce((a, b) => a + b, 0) / frameTimes.length 
            : 0;
        const maxFrameTime = frameTimes.length > 0 ? Math.max(...frameTimes) : 0;
        const minFrameTime = frameTimes.length > 0 ? Math.min(...frameTimes) : 0;
        
        // Percentile berechnen
        const sorted = [...frameTimes].sort((a, b) => a - b);
        const p50 = sorted[Math.floor(sorted.length * 0.50)] || 0;
        const p95 = sorted[Math.floor(sorted.length * 0.95)] || 0;
        const p99 = sorted[Math.floor(sorted.length * 0.99)] || 0;
        
        // Jank-Rate
        const jankRate = perfData.frameCount > 0 
            ? (perfData.jankCount / perfData.frameCount * 100).toFixed(1) 
            : 0;
        
        // Report ausgeben
        console.log('\n');
        console.log('%c╔══════════════════════════════════════════════════════════════╗', 'color: #00ff00');
        console.log('%c║           RTSP RECORDER - OVERLAY PERFORMANCE REPORT          ║', 'color: #00ff00; font-weight: bold');
        console.log('%c╠══════════════════════════════════════════════════════════════╣', 'color: #00ff00');
        console.log('%c║ Messzeit:              ' + elapsed.toFixed(1).padStart(10) + ' Sekunden                    ║', 'color: #ffffff');
        console.log('%c║ Gesamt-Frames:         ' + perfData.frameCount.toString().padStart(10) + '                             ║', 'color: #ffffff');
        console.log('%c╠══════════════════════════════════════════════════════════════╣', 'color: #00ff00');
        console.log('%c║ FRAMES PER SECOND (FPS)                                       ║', 'color: #ffff00; font-weight: bold');
        console.log('%c║ Durchschnitt:          ' + avgFPS.toFixed(1).padStart(10) + ' FPS                          ║', 'color: #ffffff');
        console.log('%c╠══════════════════════════════════════════════════════════════╣', 'color: #00ff00');
        console.log('%c║ FRAME-ZEIT (ms)                                               ║', 'color: #ffff00; font-weight: bold');
        console.log('%c║ Durchschnitt:          ' + avgFrameTime.toFixed(2).padStart(10) + ' ms                           ║', 'color: #ffffff');
        console.log('%c║ Minimum:               ' + minFrameTime.toFixed(2).padStart(10) + ' ms                           ║', 'color: #ffffff');
        console.log('%c║ Maximum:               ' + maxFrameTime.toFixed(2).padStart(10) + ' ms                           ║', 'color: #ffffff');
        console.log('%c║ P50 (Median):          ' + p50.toFixed(2).padStart(10) + ' ms                           ║', 'color: #ffffff');
        console.log('%c║ P95:                   ' + p95.toFixed(2).padStart(10) + ' ms                           ║', 'color: #ffffff');
        console.log('%c║ P99:                   ' + p99.toFixed(2).padStart(10) + ' ms                           ║', 'color: #ffffff');
        console.log('%c╠══════════════════════════════════════════════════════════════╣', 'color: #00ff00');
        console.log('%c║ JANK-ANALYSE (Frames > 16.67ms)                               ║', 'color: #ffff00; font-weight: bold');
        console.log('%c║ Jank-Events:           ' + perfData.jankCount.toString().padStart(10) + '                             ║', 'color: #ffffff');
        console.log('%c║ Jank-Rate:             ' + (jankRate + '%').padStart(10) + '                             ║', 
            parseFloat(jankRate) > 10 ? 'color: #ff0000' : 'color: #00ff00');
        console.log('%c╠══════════════════════════════════════════════════════════════╣', 'color: #00ff00');
        console.log('%c║ CANVAS-STATISTIK                                              ║', 'color: #ffff00; font-weight: bold');
        console.log('%c║ Canvas-Updates:        ' + perfData.canvasDraws.toString().padStart(10) + '                             ║', 'color: #ffffff');
        console.log('%c║ Megapixel gezeichnet:  ' + (perfData.canvasPixels / 1000000).toFixed(2).padStart(10) + ' MP                          ║', 'color: #ffffff');
        console.log('%c╠══════════════════════════════════════════════════════════════╣', 'color: #00ff00');
        console.log('%c║ BEWERTUNG                                                     ║', 'color: #ffff00; font-weight: bold');
        
        let rating, ratingColor;
        if (avgFPS >= 55 && parseFloat(jankRate) < 5) {
            rating = '★★★★★ EXZELLENT';
            ratingColor = 'color: #00ff00; font-weight: bold';
        } else if (avgFPS >= 45 && parseFloat(jankRate) < 10) {
            rating = '★★★★☆ GUT';
            ratingColor = 'color: #88ff00; font-weight: bold';
        } else if (avgFPS >= 30 && parseFloat(jankRate) < 20) {
            rating = '★★★☆☆ AKZEPTABEL';
            ratingColor = 'color: #ffff00; font-weight: bold';
        } else if (avgFPS >= 20) {
            rating = '★★☆☆☆ TRÄGE';
            ratingColor = 'color: #ff8800; font-weight: bold';
        } else {
            rating = '★☆☆☆☆ SCHLECHT';
            ratingColor = 'color: #ff0000; font-weight: bold';
        }
        
        console.log('%c║ ' + rating.padEnd(62) + '║', ratingColor);
        console.log('%c╚══════════════════════════════════════════════════════════════╝', 'color: #00ff00');
        console.log('\n');
        
        // Auch als Objekt für programmatische Nutzung
        const result = {
            elapsed,
            frameCount: perfData.frameCount,
            avgFPS,
            avgFrameTime,
            minFrameTime,
            maxFrameTime,
            p50, p95, p99,
            jankCount: perfData.jankCount,
            jankRate: parseFloat(jankRate),
            canvasDraws: perfData.canvasDraws,
            rating
        };
        
        console.log('%c[Overlay-Perf-Test] Rohdaten:', 'color: #888888', result);
        
        // Global verfügbar machen
        window.RTSP_OVERLAY_PERF_RESULT = result;
        console.log('%c[Overlay-Perf-Test] Ergebnis verfügbar unter: window.RTSP_OVERLAY_PERF_RESULT', 'color: #888888');
        
        return result;
    }
    
    // Countdown anzeigen
    let secondsLeft = perfData.reportInterval / 1000;
    const countdownInterval = setInterval(() => {
        secondsLeft--;
        if (secondsLeft > 0 && secondsLeft % 5 === 0) {
            console.log('%c[Overlay-Perf-Test] ' + secondsLeft + ' Sekunden verbleibend...', 'color: #888888');
        }
        if (secondsLeft <= 0) {
            clearInterval(countdownInterval);
        }
    }, 1000);
    
    // Report nach Ablauf generieren
    setTimeout(generateReport, perfData.reportInterval);
    
    console.log('%c[Overlay-Perf-Test] Messung läuft 10 Sekunden...', 'color: #00ff00');
    console.log('%c[Overlay-Perf-Test] Starte jetzt ein Video mit Overlay!', 'color: #ffff00; font-weight: bold');
    
    // Manueller Stop möglich
    window.RTSP_STOP_PERF_TEST = function() {
        console.log('%c[Overlay-Perf-Test] Manuell gestoppt', 'color: #ff8800');
        return generateReport();
    };
    console.log('%c[Overlay-Perf-Test] Manuell stoppen: RTSP_STOP_PERF_TEST()', 'color: #888888');
    
})();
