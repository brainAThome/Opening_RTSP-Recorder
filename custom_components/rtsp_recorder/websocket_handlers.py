"""WebSocket API handlers for RTSP Recorder.

This module contains all WebSocket endpoint handlers, extracted from __init__.py
to improve maintainability (HIGH-001 Fix from Audit Report v1.0.7).

All handlers are registered via `register_websocket_handlers()` function.
"""
import logging
import datetime
import asyncio
import aiohttp
import voluptuous as vol

from homeassistant.components import websocket_api

from .const import DOMAIN
from .helpers import log_to_file, get_system_stats, get_inference_stats
from .face_matching import _normalize_embedding_simple, _update_person_centroid
from .people_db import _load_people_db, _save_people_db, _public_people_view
from .analysis_helpers import (
    _read_analysis_results,
    _find_analysis_for_video,
    _summarize_analysis,
    _update_all_face_matches,
)
from .analysis import detect_available_devices

_LOGGER = logging.getLogger(__name__)


def register_websocket_handlers(
    hass,
    entry,
    config_data: dict,
    analysis_output_path: str,
    analysis_detector_url: str,
    analysis_face_match_threshold: float,
    people_db_path: str,
    analysis_perf_cpu_entity: str | None,
    analysis_perf_igpu_entity: str | None,
    analysis_perf_coral_entity: str | None,
):
    """Register all WebSocket handlers for the RTSP Recorder integration.
    
    Args:
        hass: Home Assistant instance
        entry: Config entry
        config_data: Merged config data (entry.data + entry.options)
        analysis_output_path: Path to analysis output directory
        analysis_detector_url: URL of the detector service
        analysis_face_match_threshold: Face matching threshold
        people_db_path: Path to people database
        analysis_perf_cpu_entity: CPU performance sensor entity ID
        analysis_perf_igpu_entity: iGPU performance sensor entity ID
        analysis_perf_coral_entity: Coral performance sensor entity ID
    """
    
    # Get inference stats tracker
    _inference_stats = get_inference_stats()
    
    # Config values we need from config_data
    analysis_enabled = config_data.get("analysis_enabled", True)
    analysis_auto_enabled = config_data.get("analysis_auto_enabled", False)
    analysis_auto_mode = config_data.get("analysis_auto_mode", "daily")
    analysis_auto_time = config_data.get("analysis_auto_time", "03:00")
    analysis_auto_interval_hours = int(config_data.get("analysis_auto_interval_hours", 24))
    analysis_auto_since_days = int(config_data.get("analysis_auto_since_days", 3))
    analysis_auto_limit = int(config_data.get("analysis_auto_limit", 10))
    analysis_auto_skip_existing = bool(config_data.get("analysis_auto_skip_existing", True))
    analysis_auto_new = bool(config_data.get("analysis_auto_new", False))
    analysis_auto_force_coral = bool(config_data.get("analysis_auto_force_coral", False))
    analysis_device = config_data.get("analysis_device", "cpu")
    analysis_objects = config_data.get("analysis_objects", ["person"])
    analysis_face_enabled = bool(config_data.get("analysis_face_enabled", False))
    analysis_face_confidence = float(config_data.get("analysis_face_confidence", 0.5))
    analysis_face_store_embeddings = bool(config_data.get("analysis_face_store_embeddings", True))
    person_entities_enabled = bool(config_data.get("person_entities_enabled", False))

    # Helper functions
    def _sensor_info(entity_id: str | None) -> dict | None:
        """Get sensor info for performance tracking."""
        if not entity_id:
            return None
        state = hass.states.get(entity_id)
        if not state:
            return {"entity_id": entity_id, "state": None, "unit": None, "name": None}
        return {
            "entity_id": entity_id,
            "state": state.state,
            "unit": state.attributes.get("unit_of_measurement"),
            "name": state.attributes.get("friendly_name", entity_id),
        }

    async def _fetch_remote_devices(url: str) -> list[str]:
        """Fetch available devices from detector service."""
        if not url:
            return []
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{url.rstrip('/')}/info", timeout=5) as resp:
                    if resp.status != 200:
                        return []
                    data = await resp.json()
                    return data.get("devices", [])
        except Exception:
            return []

    async def _fetch_detector_stats(url: str) -> dict:
        """Fetch stats from detector service."""
        if not url:
            return {"error": "no_detector_url"}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{url.rstrip('/')}/stats", timeout=5) as resp:
                    if resp.status == 404:
                        async with session.get(f"{url.rstrip('/')}/info", timeout=5) as info_resp:
                            if info_resp.status == 200:
                                info = await info_resp.json()
                                return {
                                    "available": True,
                                    "devices": info.get("devices", []),
                                    "stats_supported": False,
                                }
                        return {"available": False, "error": "stats_not_supported"}
                    if resp.status != 200:
                        return {"available": False, "error": f"http_{resp.status}"}
                    data = await resp.json()
                    data["available"] = True
                    data["stats_supported"] = True
                    return data
        except asyncio.TimeoutError:
            return {"available": False, "error": "timeout"}
        except Exception as e:
            return {"available": False, "error": str(e)}

    # ===== WebSocket Handlers =====

    @websocket_api.websocket_command({
        vol.Required("type"): "rtsp_recorder/get_analysis_overview",
        vol.Optional("limit", default=20): int,
    })
    @websocket_api.async_response
    async def ws_get_analysis_overview(hass, connection, msg):
        """Get analysis overview with stats."""
        limit = msg.get("limit", 20)
        items = await hass.async_add_executor_job(_read_analysis_results, analysis_output_path, limit)
        stats = _summarize_analysis(items)
        devices = []
        if analysis_detector_url:
            devices = await _fetch_remote_devices(analysis_detector_url)
        if not devices:
            devices = await hass.async_add_executor_job(detect_available_devices)
        perf = {
            "cpu": _sensor_info(analysis_perf_cpu_entity),
            "igpu": _sensor_info(analysis_perf_igpu_entity),
            "coral": _sensor_info(analysis_perf_coral_entity),
        }
        connection.send_result(msg["id"], {"items": items, "stats": stats, "perf": perf, "devices": devices})

    websocket_api.async_register_command(hass, ws_get_analysis_overview)

    @websocket_api.websocket_command({
        vol.Required("type"): "rtsp_recorder/get_analysis_result",
        vol.Required("media_id"): str,
    })
    @websocket_api.async_response
    async def ws_get_analysis_result(hass, connection, msg):
        """Get analysis result for a specific video."""
        media_id = msg.get("media_id", "")
        if "local/" not in media_id:
            connection.send_result(msg["id"], {})
            return
        relative_path = media_id.split("local/", 1)[1]
        video_path = f"/media/{relative_path}"
        result = await hass.async_add_executor_job(_find_analysis_for_video, analysis_output_path, video_path)
        if result:
            result.pop("frames", None)
        connection.send_result(msg["id"], result or {})

    websocket_api.async_register_command(hass, ws_get_analysis_result)

    @websocket_api.websocket_command({
        vol.Required("type"): "rtsp_recorder/get_detector_stats",
    })
    @websocket_api.async_response
    async def ws_get_detector_stats(hass, connection, msg):
        """Return detector stats including CPU, Coral status, inference times."""
        stats = await _fetch_detector_stats(analysis_detector_url)
        perf = {
            "cpu": _sensor_info(analysis_perf_cpu_entity),
            "igpu": _sensor_info(analysis_perf_igpu_entity),
            "coral": _sensor_info(analysis_perf_coral_entity),
        }
        stats["perf_sensors"] = perf
        stats["inference_stats"] = _inference_stats.get_stats()
        stats["system_stats"] = await hass.async_add_executor_job(get_system_stats)
        connection.send_result(msg["id"], stats)

    websocket_api.async_register_command(hass, ws_get_detector_stats)

    @websocket_api.websocket_command({
        vol.Required("type"): "rtsp_recorder/test_inference",
    })
    @websocket_api.async_response
    async def ws_test_inference(hass, connection, msg):
        """Run a single test inference to populate Coral statistics."""
        import time as _t
        import io
        result = {"success": False, "message": "Unknown error", "device": None, "duration_ms": 0}
        
        if not analysis_detector_url:
            result["message"] = "Detector URL not configured"
            connection.send_result(msg["id"], result)
            return
        
        try:
            # Create a valid JPEG test image using PIL
            try:
                from PIL import Image
                img = Image.new('RGB', (320, 240), color=(128, 128, 128))
                buf = io.BytesIO()
                img.save(buf, format='JPEG', quality=70)
                test_image = buf.getvalue()
            except ImportError:
                import base64
                test_image = base64.b64decode(
                    '/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRof'
                    'Hh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwh'
                    'MjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAAR'
                    'CAABAAEDASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAn/xAAUEAEAAAAAAAAAAAAAAAAA'
                    'AAAA/8QAFQEBAQAAAAAAAAAAAAAAAAAAAAX/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oADAMB'
                    'AAIRAxEAPwCwAB//2Q=='
                )
            
            async with aiohttp.ClientSession() as session:
                form = aiohttp.FormData()
                form.add_field("file", test_image, filename="test.jpg", content_type="image/jpeg")
                form.add_field("confidence", "0.1")
                form.add_field("device", "coral_usb")
                
                start = _t.time()
                async with session.post(f"{analysis_detector_url.rstrip('/')}/detect", data=form, timeout=30) as resp:
                    duration_ms = (_t.time() - start) * 1000
                    if resp.status == 200:
                        data = await resp.json()
                        used_device = data.get("device", "cpu")
                        _inference_stats.record(used_device, duration_ms, 1)
                        result = {
                            "success": True,
                            "message": f"Test inference completed on {used_device}",
                            "device": used_device,
                            "duration_ms": round(duration_ms, 1),
                            "detections": len(data.get("detections", []))
                        }
                    else:
                        body = await resp.text()
                        result["message"] = f"Detector returned status {resp.status}: {body[:100]}"
        except Exception as e:
            import traceback
            result["message"] = f"{str(e)}"
            log_to_file(f"Test inference error: {traceback.format_exc()}")
        
        connection.send_result(msg["id"], result)

    websocket_api.async_register_command(hass, ws_test_inference)

    @websocket_api.websocket_command({
        vol.Required("type"): "rtsp_recorder/get_analysis_config",
        vol.Optional("camera"): str,
    })
    @websocket_api.async_response
    async def ws_get_analysis_config(hass, connection, msg):
        """Return current analysis schedule configuration."""
        camera = msg.get("camera")
        
        cam_objects = None
        if camera:
            safe_cam = camera.replace(" ", "_").replace("-", "_")
            cam_objects_key = f"analysis_objects_{safe_cam}"
            cam_objects = config_data.get(cam_objects_key, [])
        
        camera_objects_map = {}
        for key, value in config_data.items():
            if key.startswith("analysis_objects_"):
                cam_name = key.replace("analysis_objects_", "")
                camera_objects_map[cam_name] = value
        
        result = {
            "analysis_enabled": analysis_enabled,
            "analysis_auto_enabled": analysis_auto_enabled,
            "analysis_auto_mode": analysis_auto_mode,
            "analysis_auto_time": analysis_auto_time,
            "analysis_auto_interval_hours": analysis_auto_interval_hours,
            "analysis_auto_since_days": analysis_auto_since_days,
            "analysis_auto_limit": analysis_auto_limit,
            "analysis_auto_skip_existing": analysis_auto_skip_existing,
            "analysis_auto_new": analysis_auto_new,
            "analysis_auto_force_coral": analysis_auto_force_coral,
            "person_entities_enabled": person_entities_enabled,
            "analysis_device": analysis_device,
            "analysis_objects": analysis_objects,
            "analysis_face_enabled": analysis_face_enabled,
            "analysis_face_confidence": analysis_face_confidence,
            "analysis_face_match_threshold": analysis_face_match_threshold,
            "analysis_face_store_embeddings": analysis_face_store_embeddings,
            "camera_objects": cam_objects,
            "camera_objects_map": camera_objects_map,
        }
        connection.send_result(msg["id"], result)

    websocket_api.async_register_command(hass, ws_get_analysis_config)

    @websocket_api.websocket_command({
        vol.Required("type"): "rtsp_recorder/set_analysis_config",
        vol.Optional("analysis_auto_enabled"): bool,
        vol.Optional("analysis_auto_mode"): str,
        vol.Optional("analysis_auto_time"): str,
        vol.Optional("analysis_auto_interval_hours"): int,
        vol.Optional("analysis_auto_since_days"): int,
        vol.Optional("analysis_auto_limit"): int,
        vol.Optional("analysis_auto_skip_existing"): bool,
        vol.Optional("analysis_auto_new"): bool,
    })
    @websocket_api.async_response
    async def ws_set_analysis_config(hass, connection, msg):
        """Update analysis schedule configuration."""
        try:
            updatable_fields = [
                "analysis_auto_enabled",
                "analysis_auto_mode", 
                "analysis_auto_time",
                "analysis_auto_interval_hours",
                "analysis_auto_since_days",
                "analysis_auto_limit",
                "analysis_auto_skip_existing",
                "analysis_auto_new",
            ]
            
            updates = {}
            for field in updatable_fields:
                if field in msg:
                    updates[field] = msg[field]
            
            new_data = dict(entry.data)
            new_options = dict(entry.options) if entry.options else {}
            
            new_data.update(updates)
            new_options.update(updates)
            
            hass.config_entries.async_update_entry(entry, data=new_data, options=new_options)
            
            connection.send_result(msg["id"], {
                "success": True,
                "message": "Config updated. Reload integration for scheduler changes to take effect.",
                "updated": updates
            })
        except Exception as e:
            log_to_file(f"Set analysis config error: {e}")
            connection.send_result(msg["id"], {
                "success": False,
                "message": str(e)
            })

    websocket_api.async_register_command(hass, ws_set_analysis_config)

    @websocket_api.websocket_command({
        vol.Required("type"): "rtsp_recorder/set_camera_objects",
        vol.Required("camera"): str,
        vol.Required("objects"): list,
    })
    @websocket_api.async_response
    async def ws_set_camera_objects(hass, connection, msg):
        """Set camera-specific analysis objects."""
        try:
            camera = msg["camera"]
            objects = msg["objects"]
            
            safe_cam = camera.replace(" ", "_").replace("-", "_")
            cam_objects_key = f"analysis_objects_{safe_cam}"
            
            new_data = dict(entry.data)
            new_options = dict(entry.options) if entry.options else {}
            
            if objects:
                new_data[cam_objects_key] = objects
                new_options[cam_objects_key] = objects
            else:
                new_data.pop(cam_objects_key, None)
                new_options.pop(cam_objects_key, None)
            
            hass.config_entries.async_update_entry(entry, data=new_data, options=new_options)
            
            log_to_file(f"Set camera objects for {camera}: {objects}")
            
            connection.send_result(msg["id"], {
                "success": True,
                "camera": camera,
                "objects": objects,
                "message": f"Objects for {camera} updated"
            })
        except Exception as e:
            log_to_file(f"Set camera objects error: {e}")
            connection.send_result(msg["id"], {
                "success": False,
                "message": str(e)
            })

    websocket_api.async_register_command(hass, ws_set_camera_objects)


def register_people_websocket_handlers(
    hass,
    people_db_path: str,
    analysis_output_path: str,
    analysis_face_match_threshold: float,
    validate_person_name_func,
):
    """Register People DB WebSocket handlers.
    
    Args:
        hass: Home Assistant instance
        people_db_path: Path to people database
        analysis_output_path: Path to analysis output directory
        analysis_face_match_threshold: Face matching threshold
        validate_person_name_func: Function to validate person names
    """
    import uuid

    @websocket_api.websocket_command({
        vol.Required("type"): "rtsp_recorder/get_people",
    })
    @websocket_api.async_response
    async def ws_get_people(hass, connection, msg):
        """Get all people from database."""
        data = await _load_people_db(people_db_path)
        people_view = _public_people_view(data.get("people", []))
        log_to_file(f"WS get_people -> {people_view}")
        connection.send_result(msg["id"], {"people": people_view})

    websocket_api.async_register_command(hass, ws_get_people)

    @websocket_api.websocket_command({
        vol.Required("type"): "rtsp_recorder/add_person",
        vol.Required("name"): str,
    })
    @websocket_api.async_response
    async def ws_add_person(hass, connection, msg):
        """Add a new person to database."""
        name = (msg.get("name") or "").strip()
        is_valid, error_msg = validate_person_name_func(name)
        if not is_valid:
            connection.send_error(msg["id"], "invalid_name", error_msg)
            return
        data = await _load_people_db(people_db_path)
        person = {
            "id": uuid.uuid4().hex,
            "name": name,
            "created_utc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S"),
            "embeddings": [],
        }
        data.setdefault("people", []).append(person)
        await _save_people_db(people_db_path, data)
        connection.send_result(msg["id"], {"person": _public_people_view([person])[0]})

    websocket_api.async_register_command(hass, ws_add_person)

    @websocket_api.websocket_command({
        vol.Required("type"): "rtsp_recorder/rename_person",
        vol.Required("id"): vol.Any(str, int),
        vol.Required("name"): str,
    })
    @websocket_api.async_response
    async def ws_rename_person(hass, connection, msg):
        """Rename an existing person."""
        person_id = str(msg.get("id"))
        name = (msg.get("name") or "").strip()
        is_valid, error_msg = validate_person_name_func(name)
        if not is_valid:
            connection.send_error(msg["id"], "invalid_name", error_msg)
            return
        data = await _load_people_db(people_db_path)
        people = data.get("people", [])
        updated = None
        for p in people:
            if str(p.get("id")) == person_id:
                p["name"] = name
                updated = p
                break
        if not updated:
            connection.send_error(msg["id"], "not_found", "Person nicht gefunden")
            return
        await _save_people_db(people_db_path, data)
        connection.send_result(msg["id"], {"person": _public_people_view([updated])[0]})

    websocket_api.async_register_command(hass, ws_rename_person)

    @websocket_api.websocket_command({
        vol.Required("type"): "rtsp_recorder/delete_person",
        vol.Required("id"): vol.Any(str, int),
        vol.Optional("name"): str,
        vol.Optional("created_utc"): str,
    })
    @websocket_api.async_response
    async def ws_delete_person(hass, connection, msg):
        """Delete a person from database."""
        log_to_file(f"WS delete_person payload: {msg}")
        person_id = str(msg.get("id"))
        name = (msg.get("name") or "").strip()
        created_utc = (msg.get("created_utc") or "").strip()
        data = await _load_people_db(people_db_path)
        people = data.get("people", [])
        new_people = [p for p in people if str(p.get("id")) != person_id]
        
        if len(new_people) == len(people):
            if person_id.isdigit():
                idx = int(person_id)
                if 0 <= idx < len(people):
                    new_people = [p for i, p in enumerate(people) if i != idx]
                else:
                    new_people = people
            else:
                new_people = people

        if len(new_people) == len(people) and (name or created_utc):
            def _match(p: dict) -> bool:
                if created_utc and p.get("created_utc") == created_utc:
                    return True
                if name and p.get("name") == name:
                    return True
                return False
            new_people = [p for p in people if not _match(p)]

        if len(new_people) == len(people):
            connection.send_error(msg["id"], "not_found", "Person nicht gefunden")
            return
        data["people"] = new_people
        await _save_people_db(people_db_path, data)
        connection.send_result(msg["id"], {"deleted": True})

    websocket_api.async_register_command(hass, ws_delete_person)

    @websocket_api.websocket_command({
        vol.Required("type"): "rtsp_recorder/add_person_embedding",
        vol.Required("person_id"): vol.Any(str, int),
        vol.Required("embedding"): list,
        vol.Optional("name"): str,
        vol.Optional("created_utc"): str,
        vol.Optional("thumb"): str,
        vol.Optional("source", default="manual"): str,
    })
    @websocket_api.async_response
    async def ws_add_person_embedding(hass, connection, msg):
        """Add embedding to a person for face training."""
        log_to_file(f"INIT: add_person_embedding called with person_id={msg.get('person_id')}, embedding_len={len(msg.get('embedding') or [])}")
        try:
            person_id = str(msg.get("person_id"))
            name = (msg.get("name") or "").strip()
            created_utc = (msg.get("created_utc") or "").strip()
            thumb = msg.get("thumb")
            embedding = msg.get("embedding") or []
            try:
                embedding = [float(v) for v in embedding]
            except Exception:
                connection.send_error(msg["id"], "invalid_embedding", "Embedding ungueltig")
                return
            embedding = _normalize_embedding_simple(embedding)
            if not embedding:
                connection.send_error(msg["id"], "invalid_embedding", "Embedding ungueltig")
                return
            data = await _load_people_db(people_db_path)
            people = data.get("people", [])
            updated = None
            
            def _append_embedding(p: dict) -> None:
                entry = {"vector": embedding, "source": msg.get("source")}
                if thumb:
                    entry["thumb"] = thumb
                entry["created_utc"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")
                p.setdefault("embeddings", []).append(entry)

            for p in people:
                if str(p.get("id")) == person_id:
                    _append_embedding(p)
                    _update_person_centroid(p)
                    updated = p
                    break
            if not updated and (name or created_utc):
                for p in people:
                    if created_utc and p.get("created_utc") == created_utc:
                        _append_embedding(p)
                        _update_person_centroid(p)
                        updated = p
                        break
                    if name and p.get("name") == name:
                        _append_embedding(p)
                        _update_person_centroid(p)
                        updated = p
                        break
            if not updated:
                connection.send_error(msg["id"], "not_found", "Person nicht gefunden")
                return
            await _save_people_db(people_db_path, data)
            
            connection.send_result(msg["id"], {"person": _public_people_view([updated])[0]})
            
            async def _background_rematch():
                try:
                    updated_analyses = await _update_all_face_matches(
                        analysis_output_path, 
                        data.get("people", []), 
                        analysis_face_match_threshold
                    )
                    log_to_file(f"INIT: Re-matched faces in {updated_analyses} analysis files after training")
                except Exception as e:
                    log_to_file(f"INIT: Background re-match error: {e}")
            
            hass.async_create_task(_background_rematch())
            
        except Exception as exc:
            log_to_file(f"INIT: add_person_embedding ERROR: {type(exc).__name__}: {exc}")
            connection.send_error(msg["id"], "error", f"{type(exc).__name__}: {exc}")

    websocket_api.async_register_command(hass, ws_add_person_embedding)

    @websocket_api.websocket_command({
        vol.Required("type"): "rtsp_recorder/add_negative_sample",
        vol.Required("person_id"): str,
        vol.Required("embedding"): list,
        vol.Optional("thumb"): str,
        vol.Optional("source"): str,
    })
    @websocket_api.async_response
    async def ws_add_negative_sample(hass, connection, msg):
        """Add a negative sample to a person (mark as 'NOT this person')."""
        log_to_file(f"INIT: add_negative_sample called for person_id={msg.get('person_id')}")
        try:
            person_id = str(msg.get("person_id"))
            embedding = msg.get("embedding") or []
            thumb = msg.get("thumb")
            source = msg.get("source", "manual")
            
            try:
                embedding = [float(v) for v in embedding]
            except Exception:
                connection.send_error(msg["id"], "invalid_embedding", "Embedding ungueltig")
                return
            
            embedding = _normalize_embedding_simple(embedding)
            if not embedding:
                connection.send_error(msg["id"], "invalid_embedding", "Embedding ungueltig")
                return
            
            data = await _load_people_db(people_db_path)
            people = data.get("people", [])
            updated = None
            
            for p in people:
                if str(p.get("id")) == person_id:
                    entry = {
                        "vector": embedding,
                        "source": source,
                        "created_utc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")
                    }
                    if thumb:
                        entry["thumb"] = thumb
                    p.setdefault("negative_embeddings", []).append(entry)
                    updated = p
                    break
            
            if not updated:
                connection.send_error(msg["id"], "not_found", "Person nicht gefunden")
                return
            
            await _save_people_db(people_db_path, data)
            
            neg_count = len(updated.get("negative_embeddings", []))
            log_to_file(f"INIT: Added negative sample to {updated.get('name')} (total: {neg_count})")
            
            connection.send_result(msg["id"], {
                "success": True,
                "person_id": person_id,
                "negative_count": neg_count
            })
            
        except Exception as exc:
            log_to_file(f"INIT: add_negative_sample ERROR: {type(exc).__name__}: {exc}")
            connection.send_error(msg["id"], "error", f"{type(exc).__name__}: {exc}")

    websocket_api.async_register_command(hass, ws_add_negative_sample)
