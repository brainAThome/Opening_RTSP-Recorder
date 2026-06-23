"""Regressionstest fuer den Query-Kontrakt von ws_get_movement_profile.

ws_get_movement_profile (websocket_handlers.py) liest die recognition_history mit
einer eigenen Roh-Query (Filter nach person_name, feste 5 Spalten, ORDER BY
recognized_at DESC, LIMIT 500) und baut daraus movements + summary. Dieser Test
pinnt genau diesen Query-/Mapping-Kontrakt gegen eine echte SQLite-DB fest — die
bestehenden get_recognition_history-Tests filtern nach person_id und SELECT *,
decken den person_name-Filter also NICHT ab.

Ehrlicher Scope: getestet wird der Query-/Mapping-Kontrakt. Das in beta3
eingefuehrte Auslagern dieser Query in hass.async_add_executor_job
(off-event-loop) ist eine code-reviewte Aenderung im Handler selbst;
websocket_handlers.py ist wegen seiner relativen Modul-Importe nicht standalone
importierbar und wird hier nicht direkt instanziiert.
"""
import os
import sys
import tempfile
import datetime

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "custom_components", "rtsp_recorder"))


@pytest.fixture
def db_manager():
    from database import DatabaseManager

    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    manager = DatabaseManager(path)
    manager.initialize()
    yield manager
    manager.close()
    if os.path.exists(path):
        os.remove(path)


def _movement_profile(db, person_name=None, hours=24):
    """Spiegelt exakt die Query + das movements/summary-Mapping von
    ws_get_movement_profile (websocket_handlers.py)."""
    since = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=hours)
    query = """
        SELECT person_name, camera_name, recognized_at, confidence, recording_path
        FROM recognition_history
        WHERE recognized_at >= ?
    """
    params = [since.isoformat()]
    if person_name:
        query += " AND person_name = ?"
        params.append(person_name)
    query += " ORDER BY recognized_at DESC LIMIT 500"

    rows = db.conn.execute(query, params).fetchall()
    movements = [
        {"person": r[0], "camera": r[1], "time": r[2], "confidence": r[3], "video": r[4]}
        for r in rows
    ]
    summary = {}
    for m in movements:
        person = m["person"] or "Unbekannt"
        summary.setdefault(person, []).append(
            {"camera": m["camera"], "time": m["time"], "confidence": m["confidence"]}
        )
    return {"movements": movements, "summary": summary, "total": len(movements)}


def test_person_name_filter_returns_only_that_person(db_manager):
    db_manager.add_person("p1", "Alice")
    db_manager.add_person("p2", "Bob")
    db_manager.add_recognition(camera_name="Frontdoor", person_id="p1", person_name="Alice", confidence=0.9, recording_path="/v/a1.mp4")
    db_manager.add_recognition(camera_name="Garden", person_id="p1", person_name="Alice", confidence=0.8, recording_path="/v/a2.mp4")
    db_manager.add_recognition(camera_name="Frontdoor", person_id="p2", person_name="Bob", confidence=0.7, recording_path="/v/b1.mp4")

    result = _movement_profile(db_manager, person_name="Alice")

    assert result["total"] == 2
    assert {m["camera"] for m in result["movements"]} == {"Frontdoor", "Garden"}
    assert all(m["person"] == "Alice" for m in result["movements"])
    assert set(result["summary"].keys()) == {"Alice"}


def test_without_filter_returns_all_people(db_manager):
    db_manager.add_person("p1", "Alice")
    db_manager.add_person("p2", "Bob")
    db_manager.add_recognition(camera_name="Frontdoor", person_id="p1", person_name="Alice", confidence=0.9)
    db_manager.add_recognition(camera_name="Frontdoor", person_id="p2", person_name="Bob", confidence=0.6)

    result = _movement_profile(db_manager, person_name=None)

    assert result["total"] == 2
    assert set(result["summary"].keys()) == {"Alice", "Bob"}
    # Mapping-Kontrakt: jede Bewegung hat genau die 5 erwarteten Felder
    assert all(set(m.keys()) == {"person", "camera", "time", "confidence", "video"} for m in result["movements"])


def test_movement_row_field_mapping(db_manager):
    db_manager.add_person("p1", "Alice")
    db_manager.add_recognition(camera_name="Garage", person_id="p1", person_name="Alice", confidence=0.95, recording_path="/rec/x.mp4")

    m = _movement_profile(db_manager, person_name="Alice")["movements"][0]

    assert m["person"] == "Alice"
    assert m["camera"] == "Garage"
    assert m["confidence"] == 0.95
    assert m["video"] == "/rec/x.mp4"
    assert m["time"]  # recognized_at ist gesetzt
