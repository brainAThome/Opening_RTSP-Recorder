#!/usr/bin/with-contenv bashio
set -e

DEVICE=$(bashio::config 'device')
CONFIDENCE=$(bashio::config 'confidence')

export DETECTOR_DEVICE=${DEVICE}
export DETECTOR_CONFIDENCE=${CONFIDENCE}

exec python3 -m uvicorn app:app --host 0.0.0.0 --port 5000
