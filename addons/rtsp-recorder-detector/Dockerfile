# Dockerfile for RTSP Recorder Detector Add-on
# With proper Coral USB EdgeTPU support (like Frigate uses)
# Uses libedgetpu-max for maximum performance

FROM ghcr.io/home-assistant/amd64-base-debian:bookworm

ENV PIP_BREAK_SYSTEM_PACKAGES=1
ENV PIP_NO_CACHE_DIR=1
ENV EDGETPU_DEVICE=usb
# SEC-002: CORS_ORIGINS can be set to restrict cross-origin requests
# Default allows local HA instances. Set to "*" only for development.
# Example: CORS_ORIGINS="http://homeassistant.local:8123,https://my-ha.duckdns.org"
# ENV CORS_ORIGINS=""

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       curl \
       ca-certificates \
       python3 \
       python3-pip \
       libstdc++6 \
       libusb-1.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Install libedgetpu-max from feranick/libedgetpu (same source Frigate uses)
# This runs the Coral at maximum clock speed for best performance
RUN curl -sL -o /tmp/libedgetpu1-max.deb \
    "https://github.com/feranick/libedgetpu/releases/download/16.0TF2.17.1-1/libedgetpu1-max_16.0tf2.17.1-1.bookworm_amd64.deb" \
    && dpkg-deb -x /tmp/libedgetpu1-max.deb /tmp/edgetpu \
    && cp /tmp/edgetpu/usr/lib/x86_64-linux-gnu/libedgetpu.so.1.0 /usr/lib/x86_64-linux-gnu/ \
    && ln -sf libedgetpu.so.1.0 /usr/lib/x86_64-linux-gnu/libedgetpu.so.1 \
    && ldconfig \
    && rm -rf /tmp/libedgetpu1-max.deb /tmp/edgetpu

# Install Python packages with pinned versions (LOW-007 Fix)
RUN pip3 install --no-cache-dir --break-system-packages \
      "numpy==1.26.4" \
      "tflite-runtime==2.14.0" \
      "Pillow==10.2.0" \
      "fastapi==0.109.0" \
      "python-multipart==0.0.6" \
      "uvicorn[standard]==0.27.0"

# Pre-download Frigate's tested models (mobiledet - much better than old mobilenet)
RUN mkdir -p /data/models \
    && curl -sL -o /data/models/ssdlite_mobiledet_coco_qat_postprocess_edgetpu.tflite \
       "https://github.com/google-coral/test_data/raw/release-frogfish/ssdlite_mobiledet_coco_qat_postprocess_edgetpu.tflite" \
    && curl -sL -o /data/models/ssdlite_mobiledet_coco_qat_postprocess.tflite \
       "https://github.com/google-coral/test_data/raw/release-frogfish/ssdlite_mobiledet_coco_qat_postprocess.tflite" \
    && curl -sL -o /data/models/coco_labels.txt \
       "https://github.com/google-coral/test_data/raw/master/coco_labels.txt"

WORKDIR /app
COPY app.py /app/app.py
COPY run.sh /app/run.sh
RUN chmod +x /app/run.sh

EXPOSE 5000
CMD ["/app/run.sh"]
