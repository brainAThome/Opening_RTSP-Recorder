#!/usr/bin/with-contenv bashio
set -e

DEVICE=$(bashio::config 'device')
CONFIDENCE=$(bashio::config 'confidence')

# SEC-002 Fix: Read CORS origins from config
CORS_ORIGINS=$(bashio::config 'cors_origins' || echo "")

export DETECTOR_DEVICE=${DEVICE}
export DETECTOR_CONFIDENCE=${CONFIDENCE}
export CORS_ORIGINS=${CORS_ORIGINS}

bashio::log.info "Starting RTSP Recorder Detector..."
bashio::log.info "  Device: ${DEVICE}"
bashio::log.info "  Confidence: ${CONFIDENCE}"
if [ -n "${CORS_ORIGINS}" ]; then
    bashio::log.info "  CORS Origins: ${CORS_ORIGINS}"
else
    bashio::log.info "  CORS Origins: default (local HA instances)"
fi

exec python3 -m uvicorn app:app --host 0.0.0.0 --port 5000
