#!/usr/bin/env python3
"""
RTSP Recorder Live Monitoring Script
=====================================
Monitors all RTSP Recorder activities for a specified duration.
Collects: detections, faces, MoveNet, TPU metrics, errors, analysis results.
"""

import os
import sys
import json
import time
import subprocess
import threading
from datetime import datetime
from collections import defaultdict
from pathlib import Path

# === CONFIGURATION ===
DURATION_MINUTES = 60  # How long to monitor
POLL_INTERVAL = 10     # Seconds between metric polls
ANALYSIS_PATH = "/media/rtsp_recorder/ring_recordings/_analysis"
DETECTOR_URL = "http://localhost:5000"
LOG_FILE = f"/tmp/rtsp_monitor_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
REPORT_FILE = f"/tmp/rtsp_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"

# === GLOBAL STATS ===
stats = {
    "start_time": None,
    "end_time": None,
    "persons_detected": 0,
    "faces_detected": 0,
    "movenet_fallbacks": 0,
    "no_head_detected": 0,
    "objects_by_type": defaultdict(int),
    "detections_by_camera": defaultdict(lambda: {"persons": 0, "faces": 0, "movenet": 0}),
    "tpu_inferences": 0,
    "cpu_fallbacks": 0,
    "errors": [],
    "errors_by_type": defaultdict(list),  # NEW: Grouped errors
    "retries": 0,
    "analysis_files_created": 0,
    "inference_times": [],
    "recordings_saved": 0,
    "metrics_snapshots": [],
    # NEW: Face Embedding Stats
    "face_embed_success": 0,
    "face_embed_failed": 0,
    "face_embed_errors": [],
    # NEW: Endpoint Stats
    "endpoint_stats": defaultdict(lambda: {"success": 0, "failed": 0, "times": []}),
    # NEW: Model Downloads
    "model_downloads": [],
}

log_lock = threading.Lock()

def log(msg, level="INFO"):
    """Thread-safe logging."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] [{level}] {msg}"
    with log_lock:
        print(line)
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")

def run_cmd(cmd, timeout=30):
    """Run shell command and return output."""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return result.stdout.strip()
    except Exception as e:
        return f"ERROR: {e}"

def get_metrics():
    """Fetch metrics from detector API."""
    try:
        import urllib.request
        with urllib.request.urlopen(f"{DETECTOR_URL}/metrics", timeout=5) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        return {"error": str(e)}

def get_health():
    """Fetch health from detector API."""
    try:
        import urllib.request
        with urllib.request.urlopen(f"{DETECTOR_URL}/health", timeout=5) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        return {"error": str(e)}

def monitor_ha_logs():
    """Monitor Home Assistant logs for rtsp_recorder events."""
    log("Starting HA log monitor...")
    cmd = "journalctl -u homeassistant -f --no-pager 2>/dev/null || tail -f /config/home-assistant.log 2>/dev/null || docker logs -f homeassistant 2>/dev/null"
    
    try:
        process = subprocess.Popen(
            cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        
        while monitoring_active:
            line = process.stdout.readline()
            if not line:
                time.sleep(0.1)
                continue
            
            line = line.strip()
            if "rtsp_recorder" in line.lower() or "rtsp" in line.lower():
                log(f"HA: {line[:200]}", "HA")
                
                # Parse events
                if "save_recording" in line.lower() or "recording saved" in line.lower():
                    stats["recordings_saved"] += 1
                if "error" in line.lower():
                    stats["errors"].append(line[:200])
                if "analysis" in line.lower() and "completed" in line.lower():
                    stats["analysis_files_created"] += 1
                    
    except Exception as e:
        log(f"HA log monitor error: {e}", "ERROR")

def monitor_detector_logs():
    """Monitor Docker detector container logs."""
    log("Starting Detector log monitor...")
    container_name = "addon_local_rtsp_recorder_detector"
    cmd = f"docker logs -f {container_name} 2>&1"
    
    try:
        process = subprocess.Popen(
            cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        
        while monitoring_active:
            line = process.stdout.readline()
            if not line:
                time.sleep(0.1)
                continue
            
            line = line.strip()
            if line:
                log(f"DET: {line[:200]}", "DET")
                
                # Parse detection events
                line_lower = line.lower()
                
                # NEW: Parse HTTP endpoints and status codes
                import re
                http_match = re.search(r'"(POST|GET) /(\w+).*" (\d+)', line)
                if http_match:
                    method, endpoint, status = http_match.groups()
                    status = int(status)
                    if status == 200:
                        stats["endpoint_stats"][endpoint]["success"] += 1
                    else:
                        stats["endpoint_stats"][endpoint]["failed"] += 1
                    
                    # Track face embedding specifically
                    if endpoint == "embed_face":
                        if status == 200:
                            stats["face_embed_success"] += 1
                        else:
                            stats["face_embed_failed"] += 1
                            stats["face_embed_errors"].append(f"HTTP {status}: {line[:100]}")
                
                # NEW: Parse timing from log lines like "[detect] OK device=coral_usb time=45.2ms"
                time_match = re.search(r'\[(\w+)\] OK.*time=(\d+\.?\d*)ms', line)
                if time_match:
                    endpoint, time_ms = time_match.groups()
                    stats["endpoint_stats"][endpoint]["times"].append(float(time_ms))
                
                # NEW: Track model downloads
                if "downloading" in line_lower or "download" in line_lower:
                    stats["model_downloads"].append({
                        "time": datetime.now().isoformat(),
                        "message": line[:200]
                    })
                    log(f"MODEL DOWNLOAD: {line[:150]}", "DOWNLOAD")
                
                if "person" in line_lower and ("detect" in line_lower or "found" in line_lower):
                    stats["persons_detected"] += 1
                if "face" in line_lower and ("detect" in line_lower or "found" in line_lower):
                    stats["faces_detected"] += 1
                if "movenet" in line_lower:
                    stats["movenet_fallbacks"] += 1
                if "retry" in line_lower:
                    stats["retries"] += 1
                if "tpu" in line_lower and "fallback" in line_lower:
                    stats["cpu_fallbacks"] += 1
                    
                # NEW: Categorize errors
                if "error" in line_lower or "exception" in line_lower:
                    stats["errors"].append(line[:200])
                    # Categorize
                    if "404" in line:
                        stats["errors_by_type"]["HTTP 404"].append(line[:150])
                    elif "timeout" in line_lower:
                        stats["errors_by_type"]["Timeout"].append(line[:150])
                    elif "connection" in line_lower:
                        stats["errors_by_type"]["Connection"].append(line[:150])
                    elif "tpu" in line_lower or "coral" in line_lower:
                        stats["errors_by_type"]["TPU/Coral"].append(line[:150])
                    elif "face" in line_lower or "embed" in line_lower:
                        stats["errors_by_type"]["Face Embedding"].append(line[:150])
                    else:
                        stats["errors_by_type"]["Other"].append(line[:150])
                    
                # Extract inference time (legacy)
                if "ms" in line and ("inference" in line_lower or "detect" in line_lower):
                    try:
                        match = re.search(r'(\d+\.?\d*)\s*ms', line)
                        if match:
                            stats["inference_times"].append(float(match.group(1)))
                    except:
                        pass
                        
    except Exception as e:
        log(f"Detector log monitor error: {e}", "ERROR")

def monitor_analysis_folder():
    """Watch for new analysis JSON files."""
    log("Starting analysis folder monitor...")
    seen_files = set()
    
    # Get initial files
    try:
        for root, dirs, files in os.walk(ANALYSIS_PATH):
            for f in files:
                if f.endswith(".json"):
                    seen_files.add(os.path.join(root, f))
    except:
        pass
    
    while monitoring_active:
        try:
            for root, dirs, files in os.walk(ANALYSIS_PATH):
                for f in files:
                    if f.endswith(".json"):
                        full_path = os.path.join(root, f)
                        if full_path not in seen_files:
                            seen_files.add(full_path)
                            stats["analysis_files_created"] += 1
                            log(f"NEW ANALYSIS: {full_path}", "ANALYSIS")
                            
                            # Parse the analysis file
                            try:
                                with open(full_path, "r") as af:
                                    data = json.load(af)
                                    
                                # Extract camera from video_path (more reliable)
                                camera = "unknown"
                                video_path = data.get("video_path", "")
                                if video_path:
                                    vparts = video_path.split("/")
                                    if len(vparts) >= 2:
                                        camera = vparts[-2]  # Second to last is camera name
                                
                                # Count detections - NEW FORMAT
                                # objects is a list of label strings (not nested frames)
                                objects_list = data.get("objects", [])
                                if isinstance(objects_list, list):
                                    for obj in objects_list:
                                        if isinstance(obj, str):
                                            stats["objects_by_type"][obj] += 1
                                            if obj == "person":
                                                stats["detections_by_camera"][camera]["persons"] += 1
                                                
                            except Exception as e:
                                log(f"Error parsing analysis: {e}", "WARN")
                                
        except Exception as e:
            log(f"Analysis folder error: {e}", "WARN")
            
        time.sleep(5)

def poll_metrics():
    """Periodically poll detector metrics."""
    log("Starting metrics poller...")
    
    while monitoring_active:
        metrics = get_metrics()
        health = get_health()
        
        if "error" not in metrics:
            stats["metrics_snapshots"].append({
                "time": datetime.now().isoformat(),
                "metrics": metrics,
                "health": health
            })
            
            # Update stats from metrics
            if "total_inferences" in metrics:
                stats["tpu_inferences"] = metrics.get("coral_inferences", 0)
                stats["cpu_fallbacks"] = metrics.get("cpu_fallbacks", 0)
                
            log(f"METRICS: inferences={metrics.get('total_inferences', 0)}, "
                f"coral={metrics.get('coral_inferences', 0)}, "
                f"tpu_healthy={health.get('tpu_healthy', 'unknown')}", "METRICS")
        else:
            log(f"Metrics error: {metrics['error']}", "WARN")
            
        time.sleep(POLL_INTERVAL)

def generate_report():
    """Generate final monitoring report."""
    duration_min = (stats["end_time"] - stats["start_time"]).total_seconds() / 60
    
    # Calculate inference time statistics
    def calc_percentile(data, p):
        if not data:
            return 0
        sorted_data = sorted(data)
        idx = int(len(sorted_data) * p / 100)
        return sorted_data[min(idx, len(sorted_data)-1)]
    
    avg_inference = sum(stats["inference_times"]) / len(stats["inference_times"]) if stats["inference_times"] else 0
    min_inference = min(stats["inference_times"]) if stats["inference_times"] else 0
    max_inference = max(stats["inference_times"]) if stats["inference_times"] else 0
    p95_inference = calc_percentile(stats["inference_times"], 95)
    p99_inference = calc_percentile(stats["inference_times"], 99)
    
    total_persons = sum(c["persons"] for c in stats["detections_by_camera"].values())
    total_faces = sum(c["faces"] for c in stats["detections_by_camera"].values())
    total_movenet = sum(c["movenet"] for c in stats["detections_by_camera"].values())
    
    face_rate = (total_faces / total_persons * 100) if total_persons > 0 else 0
    movenet_rate = (total_movenet / total_persons * 100) if total_persons > 0 else 0
    
    # Face embedding rate
    total_embed = stats["face_embed_success"] + stats["face_embed_failed"]
    embed_success_rate = (stats["face_embed_success"] / total_embed * 100) if total_embed > 0 else 100
    
    # Get last TPU health
    tpu_healthy = "unknown"
    if stats["metrics_snapshots"]:
        last = stats["metrics_snapshots"][-1]
        tpu_healthy = last.get("health", {}).get("tpu_healthy", "unknown")
    
    report = f"""
================================================================================
                     RTSP RECORDER MONITORING REPORT
================================================================================

ZEITRAUM:
  Start:    {stats["start_time"].strftime("%Y-%m-%d %H:%M:%S")}
  Ende:     {stats["end_time"].strftime("%Y-%m-%d %H:%M:%S")}
  Dauer:    {duration_min:.1f} Minuten

================================================================================
                              ERKENNUNGEN
================================================================================

PERSONEN-ERKENNUNG:
  Personen erkannt (gesamt):     {total_persons}
  Gesichter erkannt:             {total_faces} ({face_rate:.1f}%)
  MoveNet Fallback:              {total_movenet} ({movenet_rate:.1f}%)
  Keine Kopferkennung:           {max(0, total_persons - total_faces - total_movenet)}

================================================================================
                          FACE EMBEDDING
================================================================================

  Erfolgreiche Embeddings:       {stats["face_embed_success"]}
  Fehlgeschlagene Embeddings:    {stats["face_embed_failed"]}
  Erfolgsrate:                   {embed_success_rate:.1f}%
"""
    
    if stats["face_embed_errors"]:
        report += "\n  Letzte Fehler:\n"
        for err in stats["face_embed_errors"][-5:]:
            report += f"    - {err}\n"
    
    report += f"""
================================================================================
                         ENDPOINT STATISTIKEN
================================================================================
"""
    
    for endpoint, ep_stats in sorted(stats["endpoint_stats"].items()):
        total_req = ep_stats["success"] + ep_stats["failed"]
        success_rate = (ep_stats["success"] / total_req * 100) if total_req > 0 else 100
        
        # Calculate timing stats for this endpoint
        times = ep_stats["times"]
        if times:
            ep_avg = sum(times) / len(times)
            ep_min = min(times)
            ep_max = max(times)
            ep_p95 = calc_percentile(times, 95)
            timing_str = f"Avg={ep_avg:.1f}ms Min={ep_min:.1f}ms Max={ep_max:.1f}ms P95={ep_p95:.1f}ms"
        else:
            timing_str = "N/A"
        
        report += f"""
  /{endpoint}:
    Requests:     {total_req} (✓{ep_stats["success"]} ✗{ep_stats["failed"]}) = {success_rate:.1f}%
    Timing:       {timing_str}
"""
    
    report += f"""
OBJEKTE NACH TYP:
"""
    
    for obj_type, count in sorted(stats["objects_by_type"].items(), key=lambda x: -x[1]):
        report += f"  {obj_type:20s}: {count}\n"
    
    report += f"""
================================================================================
                           KAMERAS
================================================================================
"""
    
    for camera, cam_stats in sorted(stats["detections_by_camera"].items()):
        cam_face_rate = (cam_stats["faces"] / cam_stats["persons"] * 100) if cam_stats["persons"] > 0 else 0
        report += f"""
{camera}:
  Personen:     {cam_stats["persons"]}
  Gesichter:    {cam_stats["faces"]} ({cam_face_rate:.1f}%)
  MoveNet:      {cam_stats["movenet"]}
"""
    
    report += f"""
================================================================================
                           PERFORMANCE
================================================================================

TPU / CORAL:
  TPU Status:                    {tpu_healthy}
  TPU Inferences:                {stats["tpu_inferences"]}
  CPU Fallbacks:                 {stats["cpu_fallbacks"]}
  Retries:                       {stats["retries"]}

INFERENCE TIMING (alle Endpoints):
  Samples:                       {len(stats["inference_times"])}
  Minimum:                       {min_inference:.1f}ms
  Maximum:                       {max_inference:.1f}ms
  Durchschnitt:                  {avg_inference:.1f}ms
  P95:                           {p95_inference:.1f}ms
  P99:                           {p99_inference:.1f}ms

AUFNAHMEN:
  Recordings gespeichert:        {stats["recordings_saved"]}
  Analyse-Dateien erstellt:      {stats["analysis_files_created"]}
"""
    
    # Model Downloads
    if stats["model_downloads"]:
        report += f"""
================================================================================
                         MODEL DOWNLOADS
================================================================================
"""
        for dl in stats["model_downloads"]:
            report += f"  [{dl['time']}] {dl['message'][:80]}\n"
    
    report += f"""
================================================================================
                        FEHLER (GRUPPIERT)
================================================================================

Gesamtanzahl Fehler: {len(stats["errors"])}
"""
    
    for error_type, errors in sorted(stats["errors_by_type"].items()):
        report += f"\n  {error_type}: {len(errors)} Fehler\n"
        for err in errors[:3]:  # Show max 3 per type
            report += f"    - {err[:100]}\n"
        if len(errors) > 3:
            report += f"    ... und {len(errors) - 3} weitere\n"
    
    report += f"""
================================================================================
                          LOG DATEIEN
================================================================================

Detail-Log:  {LOG_FILE}
Report:      {REPORT_FILE}

================================================================================
"""
    
    return report


# === MAIN ===
monitoring_active = True

def main():
    global monitoring_active
    
    print(f"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                    RTSP RECORDER LIVE MONITORING                            ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  Dauer:     {DURATION_MINUTES} Minuten                                                      ║
║  Log:       {LOG_FILE}                              ║
║  Report:    {REPORT_FILE}                          ║
╚══════════════════════════════════════════════════════════════════════════════╝
""")
    
    stats["start_time"] = datetime.now()
    log(f"=== MONITORING GESTARTET (Dauer: {DURATION_MINUTES} min) ===")
    
    # Start monitoring threads
    threads = [
        threading.Thread(target=monitor_ha_logs, daemon=True),
        threading.Thread(target=monitor_detector_logs, daemon=True),
        threading.Thread(target=monitor_analysis_folder, daemon=True),
        threading.Thread(target=poll_metrics, daemon=True),
    ]
    
    for t in threads:
        t.start()
    
    # Wait for duration
    try:
        end_time = time.time() + (DURATION_MINUTES * 60)
        while time.time() < end_time:
            remaining = int((end_time - time.time()) / 60)
            total_embed = stats["face_embed_success"] + stats["face_embed_failed"]
            embed_rate = (stats["face_embed_success"] / total_embed * 100) if total_embed > 0 else 100
            error_count = len(stats["errors"])
            
            log(f"--- Status: {remaining}min | "
                f"Personen: {sum(c['persons'] for c in stats['detections_by_camera'].values())} | "
                f"FaceEmbed: {stats['face_embed_success']}/{total_embed} ({embed_rate:.0f}%) | "
                f"Errors: {error_count} | "
                f"Analysen: {stats['analysis_files_created']} ---", "STATUS")
            time.sleep(60)
            
    except KeyboardInterrupt:
        log("Monitoring durch Benutzer beendet (Ctrl+C)")
    
    # Finish
    monitoring_active = False
    stats["end_time"] = datetime.now()
    log("=== MONITORING BEENDET ===")
    
    # Generate and save report
    report = generate_report()
    with open(REPORT_FILE, "w") as f:
        f.write(report)
    
    print(report)
    log(f"Report gespeichert: {REPORT_FILE}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
