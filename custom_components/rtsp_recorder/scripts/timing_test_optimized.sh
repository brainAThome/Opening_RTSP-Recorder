#!/bin/bash
# RTSP Recorder v1.1.0 - Optimized Flow Timing Test
# Tests the callback-based recording completion and parallel snapshot
# 
# Expected improvements:
# - Recording completion detected via callback (not polling)
# - Snapshot runs parallel to recording (saves snapshot_delay time)
# - Total time: ~duration + callback_overhead (vs duration + 32s + snapshot_delay before)

DURATION=30
LOG_FILE="/config/rtsp_debug.log"
TESTCAM="Testcam"

echo "==========================================="
echo "RTSP Recorder v1.1.0 Optimized Flow Test"
echo "==========================================="
echo "Test camera: $TESTCAM"
echo "Duration: ${DURATION}s"
echo ""
echo "Expected timeline (OLD vs NEW):"
echo "OLD: duration(${DURATION}s) + sleep(2s) + polling(~5s) + snapshot(7s) = ~${((DURATION+14))}s"
echo "NEW: duration(${DURATION}s) + callback(instant) + snapshot(parallel) = ~${DURATION}s"
echo "==========================================="
echo ""

# Clear log
> "$LOG_FILE"

# Start time
START=$(date +%s.%N)

# Trigger recording
echo "[$(date +%H:%M:%S)] Triggering recording for $TESTCAM (${DURATION}s)..."
curl -s -X POST "http://localhost:8123/api/services/rtsp_recorder/save_recording" \
  -H "Authorization: Bearer $SUPERVISOR_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"entity_id\": \"camera.$TESTCAM\", \"duration\": $DURATION}" > /dev/null

# Monitor log for key events
echo "[$(date +%H:%M:%S)] Monitoring log for key events..."
echo ""

CALLBACK_TIME=""
SNAPSHOT_PARALLEL_TIME=""
SNAPSHOT_COMPLETE_TIME=""
RECORDING_SAVED_TIME=""

# Monitor for up to 2 minutes
timeout 120 tail -f "$LOG_FILE" 2>/dev/null | while read line; do
    NOW=$(date +%s.%N)
    ELAPSED=$(echo "$NOW - $START" | bc)
    
    if echo "$line" | grep -q "Recording started, waiting for completion via callback"; then
        echo "[+${ELAPSED}s] Recording STARTED (callback-based wait)"
    fi
    
    if echo "$line" | grep -q "Snapshot scheduled in"; then
        echo "[+${ELAPSED}s] Snapshot SCHEDULED (parallel to recording)"
    fi
    
    if echo "$line" | grep -q "Taking parallel snapshot"; then
        echo "[+${ELAPSED}s] Snapshot TAKING (parallel)"
    fi
    
    if echo "$line" | grep -q "Parallel snapshot complete"; then
        echo "[+${ELAPSED}s] Snapshot COMPLETE (parallel)"
        SNAPSHOT_COMPLETE_TIME=$ELAPSED
    fi
    
    if echo "$line" | grep -q "Recording callback: success=True"; then
        echo "[+${ELAPSED}s] Recording CALLBACK (success) ✓"
        CALLBACK_TIME=$ELAPSED
    fi
    
    if echo "$line" | grep -q "Recording callback: success=False"; then
        echo "[+${ELAPSED}s] Recording CALLBACK (failed) ✗"
        CALLBACK_TIME=$ELAPSED
    fi
    
    if echo "$line" | grep -q "Recording and snapshot complete"; then
        echo "[+${ELAPSED}s] Recording and Snapshot FINALIZED"
    fi
    
    if echo "$line" | grep -q "Fired rtsp_recorder_recording_saved"; then
        echo "[+${ELAPSED}s] EVENT FIRED: rtsp_recorder_recording_saved ✓"
        
        # Calculate final timing
        END=$(date +%s.%N)
        TOTAL=$(echo "$END - $START" | bc)
        echo ""
        echo "==========================================="
        echo "TIMING RESULTS"
        echo "==========================================="
        echo "Configured duration: ${DURATION}s"
        echo "Total time to event: ${TOTAL}s"
        echo "Overhead: $(echo "$TOTAL - $DURATION" | bc)s"
        echo ""
        if [ ! -z "$CALLBACK_TIME" ]; then
            echo "Callback received at: ${CALLBACK_TIME}s"
        fi
        echo "==========================================="
        
        exit 0
    fi
done

echo ""
echo "Test completed or timed out."
