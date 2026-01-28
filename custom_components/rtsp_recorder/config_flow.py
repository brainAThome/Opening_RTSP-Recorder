"""RTSP Recorder Integration - Config Flow."""
import logging
import os
import re
import voluptuous as vol
import aiohttp
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector
from .analysis import detect_available_devices

DOMAIN = "rtsp_recorder"
_LOGGER = logging.getLogger(__name__)


def log_to_file(msg):
    """Debug logging."""
    _LOGGER.debug(msg)
    try:
        with open("/config/rtsp_debug.log", "a") as f:
            f.write(f"FLOW: {msg}\n")
    except Exception:
        pass


def normalize_camera_name(name: str) -> str:
    """Normalize camera name for deduplication."""
    clean = re.sub(r"[^\w\s-]", "", name).strip()
    clean = clean.replace("_", " ").lower()
    clean = " ".join(clean.split())
    return clean


def prettify_camera_name(name: str) -> str:
    """Make camera name display-friendly."""
    pretty = name.replace("_", " ")
    return pretty.title()


def sanitize_camera_key(name: str) -> str:
    """Sanitize camera name for config keys and folders."""
    clean = re.sub(r"[^\w\s-]", "", name).strip().replace(" ", "_")
    for char in [":", "/", "\\", "?", "*", "\"", "<", ">", "|"]:
        clean = clean.replace(char, "")
    return clean or "unknown"


class RtspRecorderConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle initial config flow for RTSP Recorder."""
    
    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow handler."""
        return RtspRecorderOptionsFlow(config_entry)

    async def async_step_user(self, user_input=None):
        """Handle the initial setup step."""
        errors = {}
        
        if user_input is not None:
            storage_path = user_input.get("storage_path", "")
            retention_days = user_input.get("retention_days", 7)
            snapshot_path = user_input.get("snapshot_path", "/config/www/thumbnails")
            
            if not storage_path or not storage_path.startswith("/"):
                errors["storage_path"] = "invalid_path"
            if not snapshot_path or not snapshot_path.startswith("/"):
                errors["snapshot_path"] = "invalid_path"
            elif retention_days < 1:
                errors["retention_days"] = "invalid_retention"
            
            if not errors:
                return self.async_create_entry(title="RTSP Recorder", data=user_input)

        data_schema = vol.Schema({
            vol.Required("storage_path", default="/media/rtsp_recordings"): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
            ),
            vol.Required("snapshot_path", default="/config/www/thumbnails"): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
            ),
            vol.Required("retention_days", default=7): selector.NumberSelector(
                selector.NumberSelectorConfig(min=1, max=365, step=1, mode=selector.NumberSelectorMode.BOX)
            ),
            vol.Optional("retention_hours", default=0): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, max=23, step=1, mode=selector.NumberSelectorMode.BOX)
            ),
        })

        return self.async_show_form(
            step_id="user", 
            data_schema=data_schema, 
            errors=errors
        )


class RtspRecorderOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow - Simplified 2-page design."""

    def __init__(self, config_entry):
        """Initialize options flow."""
        self._config_entry = config_entry
        self.config_cache = {**config_entry.data, **config_entry.options}
        self.selected_camera = None
        self._camera_list = []

    def _check_allowlist(self, path: str) -> bool:
        """Check if path is in allowlist_external_dirs."""
        try:
            allowlist = self.hass.config.allowlist_external_dirs
            for allowed in allowlist:
                if path.startswith(allowed):
                    return True
            return False
        except Exception:
            return False

    async def async_step_init(self, user_input=None):
        """
        HAUPTSEITE: Globale Einstellungen + Kamera-Auswahl
        Alles auf einer Seite fuer schnellen Zugriff.
        """
        log_to_file("OptionsFlow: Hauptseite")
        errors = {}
        
        # Build camera list on entry
        raw_cameras = await self._scan_cameras()
        self._camera_list = self._deduplicate_cameras(raw_cameras)
        
        if user_input is not None:
            # Validate storage path
            storage_path = user_input.get("storage_path", "").strip()
            snapshot_path = user_input.get("snapshot_path", "").strip()
            if not storage_path or not storage_path.startswith("/"):
                errors["storage_path"] = "invalid_path"
            elif not snapshot_path or not snapshot_path.startswith("/"):
                errors["snapshot_path"] = "invalid_path"
            else:
                # Save all settings
                self.config_cache["storage_path"] = storage_path
                self.config_cache["snapshot_path"] = snapshot_path
                self.config_cache["retention_days"] = user_input.get("retention_days", 7)
                self.config_cache["snapshot_retention_days"] = user_input.get("snapshot_retention_days", 7)
                
                selected = user_input.get("camera_selection")
                analysis_configure = user_input.get("analysis_configure", False)
                
                # If a camera is selected, go to camera config
                if analysis_configure:
                    return await self.async_step_analysis()
                if selected == "__MANUAL__":
                    return await self.async_step_manual_camera()
                if selected and selected != "__NONE__":
                    self.selected_camera = selected
                    return await self.async_step_camera_config()
                
                # Otherwise save and exit
                return self.async_create_entry(title="", data=self.config_cache)

        # Current values
        storage = self.config_cache.get("storage_path", "/media/rtsp_recordings")
        snapshot_path = self.config_cache.get("snapshot_path", "/config/www/thumbnails")
        vid_days = self.config_cache.get("retention_days", 7)
        snap_days = self.config_cache.get("snapshot_retention_days", 7)
        
        # Check allowlist status for description
        is_allowed = self._check_allowlist(storage)
        allowlist_status = "Pfad ist freigegeben" if is_allowed else "Pfad muss in configuration.yaml freigegeben werden!"

        # Build camera options
        cam_options = [
            {"value": "__NONE__", "label": "-- Keine Kamera konfigurieren --"},
            {"value": "__MANUAL__", "label": "Manuelle RTSP-Kamera hinzufuegen"}
        ]
        for cam in sorted(self._camera_list):
            display = prettify_camera_name(cam)
            safe_name = cam.replace(" ", "_")
            has_sensor = f"sensor_{safe_name}" in self.config_cache
            icon = "✅" if has_sensor else "🆕"
            cam_options.append({"value": cam, "label": f"{icon} {display}"})

        schema = vol.Schema({
            vol.Required("storage_path", default=storage): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
            ),
            vol.Required("snapshot_path", default=snapshot_path): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
            ),
            vol.Required("retention_days", default=vid_days): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=1, max=365, step=1, 
                    mode=selector.NumberSelectorMode.SLIDER,
                    unit_of_measurement="Tage"
                )
            ),
            vol.Required("snapshot_retention_days", default=snap_days): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=1, max=365, step=1, 
                    mode=selector.NumberSelectorMode.SLIDER,
                    unit_of_measurement="Tage"
                )
            ),
            vol.Optional("camera_selection", default="__NONE__"): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=cam_options,
                    mode=selector.SelectSelectorMode.DROPDOWN
                )
            ),
            vol.Optional("analysis_configure", default=False): selector.BooleanSelector(),
        })

        return self.async_show_form(
            step_id="init",
            data_schema=schema,
            errors=errors,
            description_placeholders={"allowlist_status": allowlist_status},
            last_step=True
        )

    async def async_step_camera_config(self, user_input=None):
        """
        SEITE 2: Kamera-Konfiguration
        Bewegungssensor und Aufnahme-Einstellungen.
        """
        cam = self.selected_camera
        display_name = prettify_camera_name(cam)
        log_to_file(f"OptionsFlow: Kamera konfigurieren - {cam}")
        
        # Create safe key prefix
        safe_name = sanitize_camera_key(cam)
        
        key_sensor = f"sensor_{safe_name}"
        key_duration = f"duration_{safe_name}"
        key_delay = f"snapshot_delay_{safe_name}"
        key_retention = f"retention_hours_{safe_name}"
        key_rtsp = f"rtsp_url_{safe_name}"
        key_objects = f"analysis_objects_{safe_name}"  # v1.0.6: Pro-Kamera Objekt-Filter
        
        if user_input is not None:
            # Save sensor (if selected)
            sensor = user_input.get("motion_sensor")
            if sensor:
                self.config_cache[key_sensor] = sensor
            elif key_sensor in self.config_cache:
                del self.config_cache[key_sensor]
            
            # Save duration
            self.config_cache[key_duration] = int(user_input.get("recording_duration", 120))
            
            # Save snapshot delay
            self.config_cache[key_delay] = int(user_input.get("snapshot_delay", 0))

            # Save RTSP URL override (optional)
            rtsp_url = (user_input.get("rtsp_url") or "").strip()
            if rtsp_url:
                self.config_cache[key_rtsp] = rtsp_url
            elif key_rtsp in self.config_cache:
                del self.config_cache[key_rtsp]
            
            # Save retention override (only if > 0)
            retention = float(user_input.get("camera_retention", 0))
            if retention > 0:
                self.config_cache[key_retention] = retention
            elif key_retention in self.config_cache:
                del self.config_cache[key_retention]
            
            # v1.0.6: Save camera-specific analysis objects
            cam_objects = user_input.get("camera_objects", [])
            if cam_objects:
                self.config_cache[key_objects] = cam_objects
            elif key_objects in self.config_cache:
                del self.config_cache[key_objects]  # Use global default
            
            # Check if user wants to configure another camera
            if user_input.get("configure_another", False):
                return await self.async_step_init()
            
            # Save and exit
            return self.async_create_entry(title="", data=self.config_cache)

        # Load current values
        cur_sensor = self.config_cache.get(key_sensor)
        cur_duration = self.config_cache.get(key_duration, 120)
        cur_delay = self.config_cache.get(key_delay, 0)
        cur_retention = self.config_cache.get(key_retention, 0)
        cur_rtsp = self.config_cache.get(key_rtsp, "")
        
        # v1.0.6: Camera-specific object filter (falls back to global)
        global_objects = self.config_cache.get("analysis_objects", ["person"])
        cur_objects = self.config_cache.get(key_objects, [])  # Empty = use global
        
        # Objektliste fuer Kamera-Auswahl
        cam_object_options = [
            {"value": "person", "label": "Person"},
            {"value": "cat", "label": "Katze"},
            {"value": "dog", "label": "Hund"},
            {"value": "bird", "label": "Vogel"},
            {"value": "car", "label": "Auto"},
            {"value": "truck", "label": "LKW"},
            {"value": "bicycle", "label": "Fahrrad"},
            {"value": "motorcycle", "label": "Motorrad"},
            {"value": "bus", "label": "Bus"},
            {"value": "tv", "label": "Fernseher"},
            {"value": "couch", "label": "Sofa"},
            {"value": "chair", "label": "Stuhl"},
            {"value": "bed", "label": "Bett"},
            {"value": "dining table", "label": "Esstisch"},
            {"value": "potted plant", "label": "Pflanze"},
            {"value": "laptop", "label": "Laptop"},
            {"value": "cell phone", "label": "Handy"},
            {"value": "remote", "label": "Fernbedienung"},
            {"value": "bottle", "label": "Flasche"},
            {"value": "cup", "label": "Tasse"},
            {"value": "book", "label": "Buch"},
            {"value": "backpack", "label": "Rucksack"},
            {"value": "umbrella", "label": "Regenschirm"},
            {"value": "suitcase", "label": "Koffer"},
            {"value": "package", "label": "Paket"},
        ]

        schema = vol.Schema({
            vol.Optional("motion_sensor", description={"suggested_value": cur_sensor}): selector.EntitySelector(
                selector.EntitySelectorConfig(
                    domain="binary_sensor",
                    device_class="motion"
                )
            ),
            vol.Required("recording_duration", default=cur_duration): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=10, max=600, step=10,
                    mode=selector.NumberSelectorMode.SLIDER,
                    unit_of_measurement="Sek"
                )
            ),
            vol.Optional("snapshot_delay", default=cur_delay): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0, max=60, step=1,
                    mode=selector.NumberSelectorMode.SLIDER,
                    unit_of_measurement="Sek"
                )
            ),
            vol.Optional("rtsp_url", default=cur_rtsp): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
            ),
            vol.Optional("camera_retention", default=float(cur_retention)): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0, max=168, step=0.5,
                    mode=selector.NumberSelectorMode.BOX,
                    unit_of_measurement="Std"
                )
            ),
            # v1.0.6: Camera-specific analysis objects
            vol.Optional("camera_objects", default=cur_objects): selector.SelectSelector(
                selector.SelectSelectorConfig(options=cam_object_options, multiple=True, mode=selector.SelectSelectorMode.DROPDOWN)
            ),
            vol.Optional("configure_another", default=False): selector.BooleanSelector(),
        })
        
        return self.async_show_form(
            step_id="camera_config",
            data_schema=schema,
            description_placeholders={"camera_name": display_name},
            last_step=True
        )

    async def async_step_manual_camera(self, user_input=None):
        """
        SEITE 2b: Manuelle RTSP-Kamera hinzufuegen
        """
        errors = {}

        if user_input is not None:
            camera_name = (user_input.get("camera_name") or "").strip()
            rtsp_url = (user_input.get("rtsp_url") or "").strip()

            if not camera_name:
                errors["camera_name"] = "invalid_camera_name"
            if not rtsp_url or not (rtsp_url.startswith("rtsp://") or rtsp_url.startswith("rtsps://")):
                errors["rtsp_url"] = "invalid_rtsp"

            safe_name = sanitize_camera_key(camera_name) if camera_name else ""
            key_sensor = f"sensor_{safe_name}"
            key_duration = f"duration_{safe_name}"
            key_delay = f"snapshot_delay_{safe_name}"
            key_retention = f"retention_hours_{safe_name}"
            key_rtsp = f"rtsp_url_{safe_name}"

            existing_norm = {normalize_camera_name(c) for c in self._camera_list}
            existing_norm.update({normalize_camera_name(k.replace("rtsp_url_", "")) for k in self.config_cache.keys() if k.startswith("rtsp_url_")})
            if camera_name and normalize_camera_name(camera_name) in existing_norm:
                errors["camera_name"] = "camera_exists"
            if safe_name and (key_rtsp in self.config_cache or key_duration in self.config_cache or key_sensor in self.config_cache):
                errors["camera_name"] = "camera_exists"

            if not errors:
                sensor = user_input.get("motion_sensor")
                if sensor:
                    self.config_cache[key_sensor] = sensor
                elif key_sensor in self.config_cache:
                    del self.config_cache[key_sensor]

                self.config_cache[key_duration] = int(user_input.get("recording_duration", 120))
                self.config_cache[key_delay] = int(user_input.get("snapshot_delay", 0))

                retention = float(user_input.get("camera_retention", 0))
                if retention > 0:
                    self.config_cache[key_retention] = retention
                elif key_retention in self.config_cache:
                    del self.config_cache[key_retention]

                self.config_cache[key_rtsp] = rtsp_url

                if user_input.get("configure_another", False):
                    return await self.async_step_init()

                return self.async_create_entry(title="", data=self.config_cache)

        schema = vol.Schema({
            vol.Required("camera_name"): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
            ),
            vol.Required("rtsp_url"): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
            ),
            vol.Optional("motion_sensor"): selector.EntitySelector(
                selector.EntitySelectorConfig(
                    domain="binary_sensor",
                    device_class="motion"
                )
            ),
            vol.Required("recording_duration", default=120): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=10, max=600, step=10,
                    mode=selector.NumberSelectorMode.SLIDER,
                    unit_of_measurement="Sek"
                )
            ),
            vol.Optional("snapshot_delay", default=0): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0, max=60, step=1,
                    mode=selector.NumberSelectorMode.SLIDER,
                    unit_of_measurement="Sek"
                )
            ),
            vol.Optional("camera_retention", default=0.0): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0, max=168, step=0.5,
                    mode=selector.NumberSelectorMode.BOX,
                    unit_of_measurement="Std"
                )
            ),
            vol.Optional("configure_another", default=False): selector.BooleanSelector(),
        })

        return self.async_show_form(
            step_id="manual_camera",
            data_schema=schema,
            errors=errors,
            last_step=True
        )

    async def async_step_analysis(self, user_input=None):
        """
        SEITE 3: Offline-Analyse konfigurieren
        """
        errors = {}

        storage = self.config_cache.get("storage_path", "/media/rtsp_recordings")
        default_output = self.config_cache.get("analysis_output_path", os.path.join(storage, "_analysis"))

        if user_input is not None:
            output_path = (user_input.get("analysis_output_path") or "").strip()
            if not output_path or not output_path.startswith("/"):
                errors["analysis_output_path"] = "invalid_path"

            auto_enabled = bool(user_input.get("analysis_auto_enabled", False))
            auto_new = bool(user_input.get("analysis_auto_new", False))
            auto_mode = user_input.get("analysis_auto_mode", "daily")
            auto_time = (user_input.get("analysis_auto_time") or "").strip()
            auto_interval = int(user_input.get("analysis_auto_interval_hours", 24))
            auto_since_days = int(user_input.get("analysis_auto_since_days", 1))
            auto_limit = int(user_input.get("analysis_auto_limit", 50))

            if auto_enabled:
                if auto_mode == "daily":
                    if not re.match(r"^\d{1,2}:\d{2}$", auto_time):
                        errors["analysis_auto_time"] = "invalid_time"
                else:
                    if auto_interval < 1:
                        errors["analysis_auto_interval_hours"] = "invalid_interval"
                if auto_since_days < 0:
                    errors["analysis_auto_since_days"] = "invalid_number"
                if auto_limit < 0:
                    errors["analysis_auto_limit"] = "invalid_number"

            if not errors:
                self.config_cache["analysis_enabled"] = bool(user_input.get("analysis_enabled", True))
                self.config_cache["analysis_device"] = user_input.get("analysis_device", "cpu")
                self.config_cache["analysis_objects"] = user_input.get("analysis_objects", [])
                self.config_cache["analysis_output_path"] = output_path
                self.config_cache["analysis_frame_interval"] = int(user_input.get("analysis_frame_interval", 2))
                self.config_cache["analysis_detector_url"] = (user_input.get("analysis_detector_url") or "").strip()
                self.config_cache["analysis_detector_confidence"] = float(user_input.get("analysis_detector_confidence", 0.4))
                self.config_cache["analysis_auto_enabled"] = auto_enabled
                self.config_cache["analysis_auto_mode"] = auto_mode
                self.config_cache["analysis_auto_time"] = auto_time or "03:00"
                self.config_cache["analysis_auto_interval_hours"] = auto_interval
                self.config_cache["analysis_auto_since_days"] = auto_since_days
                self.config_cache["analysis_auto_limit"] = auto_limit
                self.config_cache["analysis_auto_skip_existing"] = bool(user_input.get("analysis_auto_skip_existing", True))
                self.config_cache["analysis_auto_new"] = auto_new
                self.config_cache["analysis_perf_cpu_entity"] = user_input.get("analysis_perf_cpu_entity")
                self.config_cache["analysis_perf_igpu_entity"] = user_input.get("analysis_perf_igpu_entity")
                self.config_cache["analysis_perf_coral_entity"] = user_input.get("analysis_perf_coral_entity")

                return self.async_create_entry(title="", data=self.config_cache)

        # Erweiterte Objektliste: Outdoor + Indoor Objekte (v1.0.6)
        object_options = [
            # Personen & Tiere
            {"value": "person", "label": "Person"},
            {"value": "cat", "label": "Katze"},
            {"value": "dog", "label": "Hund"},
            {"value": "bird", "label": "Vogel"},
            # Fahrzeuge (Outdoor)
            {"value": "car", "label": "Auto"},
            {"value": "truck", "label": "LKW"},
            {"value": "bicycle", "label": "Fahrrad"},
            {"value": "motorcycle", "label": "Motorrad"},
            {"value": "bus", "label": "Bus"},
            # Haushalt (Indoor)
            {"value": "tv", "label": "Fernseher"},
            {"value": "couch", "label": "Sofa"},
            {"value": "chair", "label": "Stuhl"},
            {"value": "bed", "label": "Bett"},
            {"value": "dining table", "label": "Esstisch"},
            {"value": "potted plant", "label": "Pflanze"},
            # Elektronik
            {"value": "laptop", "label": "Laptop"},
            {"value": "cell phone", "label": "Handy"},
            {"value": "remote", "label": "Fernbedienung"},
            # Gegenstaende
            {"value": "bottle", "label": "Flasche"},
            {"value": "cup", "label": "Tasse"},
            {"value": "book", "label": "Buch"},
            {"value": "backpack", "label": "Rucksack"},
            {"value": "umbrella", "label": "Regenschirm"},
            {"value": "suitcase", "label": "Koffer"},
            {"value": "package", "label": "Paket"},
        ]

        detector_url = self.config_cache.get("analysis_detector_url", "")
        available_devices = ["cpu"]
        if detector_url:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(f"{detector_url.rstrip('/')}/info", timeout=5) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            available_devices = data.get("devices", ["cpu"]) or ["cpu"]
            except Exception:
                available_devices = ["cpu"]
        else:
            try:
                available_devices = await self.hass.async_add_executor_job(detect_available_devices)
            except Exception:
                available_devices = ["cpu"]

        device_options = []
        if "cpu" in available_devices:
            device_options.append({"value": "cpu", "label": "CPU"})
        if "coral_usb" in available_devices:
            device_options.append({"value": "coral_usb", "label": "Coral USB"})

        cur_enabled = self.config_cache.get("analysis_enabled", True)
        cur_device = self.config_cache.get("analysis_device", "cpu")
        if cur_device not in [d["value"] for d in device_options]:
            cur_device = "cpu"
        cur_objects = self.config_cache.get("analysis_objects", ["person"])
        cur_interval = int(self.config_cache.get("analysis_frame_interval", 2))
        cur_auto_enabled = self.config_cache.get("analysis_auto_enabled", False)
        cur_auto_mode = self.config_cache.get("analysis_auto_mode", "daily")
        cur_auto_time = self.config_cache.get("analysis_auto_time", "03:00")
        cur_auto_interval = int(self.config_cache.get("analysis_auto_interval_hours", 24))
        cur_auto_since_days = int(self.config_cache.get("analysis_auto_since_days", 1))
        cur_auto_limit = int(self.config_cache.get("analysis_auto_limit", 50))
        cur_auto_skip_existing = bool(self.config_cache.get("analysis_auto_skip_existing", True))
        cur_auto_new = bool(self.config_cache.get("analysis_auto_new", False))
        cur_perf_cpu = self.config_cache.get("analysis_perf_cpu_entity")
        cur_perf_igpu = self.config_cache.get("analysis_perf_igpu_entity")
        cur_perf_coral = self.config_cache.get("analysis_perf_coral_entity")
        cur_detector_url = self.config_cache.get("analysis_detector_url", "")
        cur_detector_conf = float(self.config_cache.get("analysis_detector_confidence", 0.4))

        schema = vol.Schema({
            vol.Required("analysis_enabled", default=cur_enabled): selector.BooleanSelector(),
            vol.Required("analysis_device", default=cur_device): selector.SelectSelector(
                selector.SelectSelectorConfig(options=device_options, mode=selector.SelectSelectorMode.DROPDOWN)
            ),
            vol.Required("analysis_objects", default=cur_objects): selector.SelectSelector(
                selector.SelectSelectorConfig(options=object_options, multiple=True, mode=selector.SelectSelectorMode.DROPDOWN)
            ),
            vol.Required("analysis_output_path", default=default_output): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
            ),
            vol.Required("analysis_frame_interval", default=cur_interval): selector.NumberSelector(
                selector.NumberSelectorConfig(min=1, max=10, step=1, mode=selector.NumberSelectorMode.SLIDER, unit_of_measurement="Sek")
            ),
            vol.Optional("analysis_detector_url", default=cur_detector_url): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
            ),
            vol.Required("analysis_detector_confidence", default=cur_detector_conf): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0.1, max=0.9, step=0.05, mode=selector.NumberSelectorMode.SLIDER)
            ),
            vol.Required("analysis_auto_enabled", default=cur_auto_enabled): selector.BooleanSelector(),
            vol.Required("analysis_auto_new", default=cur_auto_new): selector.BooleanSelector(),
            vol.Required("analysis_auto_mode", default=cur_auto_mode): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        {"value": "daily", "label": "Taeglich (Uhrzeit)"},
                        {"value": "interval", "label": "Intervall (Stunden)"},
                    ],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Required("analysis_auto_time", default=cur_auto_time): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
            ),
            vol.Required("analysis_auto_interval_hours", default=cur_auto_interval): selector.NumberSelector(
                selector.NumberSelectorConfig(min=1, max=168, step=1, mode=selector.NumberSelectorMode.BOX, unit_of_measurement="Std")
            ),
            vol.Required("analysis_auto_since_days", default=cur_auto_since_days): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, max=365, step=1, mode=selector.NumberSelectorMode.BOX, unit_of_measurement="Tage")
            ),
            vol.Required("analysis_auto_limit", default=cur_auto_limit): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, max=1000, step=1, mode=selector.NumberSelectorMode.BOX)
            ),
            vol.Required("analysis_auto_skip_existing", default=cur_auto_skip_existing): selector.BooleanSelector(),
            vol.Optional("analysis_perf_cpu_entity", description={"suggested_value": cur_perf_cpu}): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor")
            ),
            vol.Optional("analysis_perf_igpu_entity", description={"suggested_value": cur_perf_igpu}): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor")
            ),
            vol.Optional("analysis_perf_coral_entity", description={"suggested_value": cur_perf_coral}): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor")
            ),
        })

        return self.async_show_form(
            step_id="analysis",
            data_schema=schema,
            errors=errors,
            last_step=True
        )

    def _deduplicate_cameras(self, cameras: set) -> list:
        """Remove duplicate cameras (e.g., 'Flur oben' and 'Flur_oben')."""
        seen_normalized = {}
        result = []
        
        for cam in cameras:
            normalized = normalize_camera_name(cam)
            
            if normalized not in seen_normalized:
                # Prefer names with spaces over underscores
                seen_normalized[normalized] = cam
                result.append(cam)
            else:
                # If we have "Flur_oben" and now see "Flur oben", prefer the spaced version
                existing = seen_normalized[normalized]
                if "_" in existing and " " in cam:
                    # Replace underscore version with space version
                    result.remove(existing)
                    result.append(cam)
                    seen_normalized[normalized] = cam
        
        return result

    async def _scan_cameras(self) -> set:
        """Scan for available cameras from disk and HA entities."""
        storage_path = self.config_cache.get("storage_path", "/media/rtsp_recordings")
        candidates = set()
        
        # 1. Scan disk folders
        if os.path.exists(storage_path):
            try:
                subdirs = await self.hass.async_add_executor_job(self._get_subdirs, storage_path)
                for d in subdirs:
                    d_lower = d.lower()
                    if (
                        "snapshot" in d_lower
                        or d.startswith(".")
                        or d_lower in {"analysis", "_analysis"}
                        or d_lower.endswith("_analysis")
                    ):
                        continue
                    candidates.add(d)
            except Exception as e:
                log_to_file(f"Disk scan error: {e}")
        
        # 2. Scan HA camera entities
        try:
            for state in self.hass.states.async_all("camera"):
                if "rtsp_recorder" in state.entity_id:
                    continue
                    
                name = state.attributes.get("friendly_name", state.entity_id)
                if name:
                    name_lower = name.lower()
                    if (
                        "snapshot" in name_lower
                        or name_lower in {"analysis", "_analysis"}
                        or name_lower.endswith("_analysis")
                    ):
                        continue
                    candidates.add(name)
        except Exception as e:
            log_to_file(f"Entity scan error: {e}")
        
        return candidates

    def _get_subdirs(self, path: str) -> list:
        """Return subdirectories (camera folders)."""
        return [
            d for d in os.listdir(path)
            if os.path.isdir(os.path.join(path, d))
        ]
