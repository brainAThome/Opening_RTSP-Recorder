#!/usr/bin/env python3
"""Comprehensive test for all new v1.1.0 security and quality modules.

Tests:
1. Rate Limiter
2. Exceptions
3. Performance Monitor
4. Migrations
5. XSS Protection in JavaScript
"""
import asyncio
import sys
import time
from pathlib import Path

# Add module path
sys.path.insert(0, "/config/custom_components/rtsp_recorder")

def test_rate_limiter():
    """Test Rate Limiter module."""
    print("\n" + "="*60)
    print("🔒 TESTING RATE LIMITER")
    print("="*60)
    
    from rate_limiter import RateLimiter, RateLimitConfig, get_rate_limiter
    
    tests_passed = 0
    tests_failed = 0
    
    # Test 1: Default configuration
    try:
        config = RateLimitConfig()
        assert config.requests_per_window == 60
        assert config.enabled == True
        print("✅ Default configuration OK")
        tests_passed += 1
    except Exception as e:
        print(f"❌ Default configuration FAILED: {e}")
        tests_failed += 1
    
    # Test 2: Custom configuration
    try:
        config = RateLimitConfig(
            requests_per_window=100,
            window_seconds=30,
            burst_size=20,
            enabled=False
        )
        assert config.requests_per_window == 100
        assert config.enabled == False
        print("✅ Custom configuration OK")
        tests_passed += 1
    except Exception as e:
        print(f"❌ Custom configuration FAILED: {e}")
        tests_failed += 1
    
    # Test 3: Rate limiter instance
    try:
        rl = RateLimiter()
        stats = rl.get_stats()
        assert "enabled" in stats
        assert "total_clients" in stats
        print("✅ Rate limiter instance OK")
        tests_passed += 1
    except Exception as e:
        print(f"❌ Rate limiter instance FAILED: {e}")
        tests_failed += 1
    
    # Test 4: Global instance
    try:
        rl1 = get_rate_limiter()
        rl2 = get_rate_limiter()
        assert rl1 is rl2
        print("✅ Global singleton OK")
        tests_passed += 1
    except Exception as e:
        print(f"❌ Global singleton FAILED: {e}")
        tests_failed += 1
    
    # Test 5: Async rate checking
    try:
        async def check_async():
            rl = RateLimiter(RateLimitConfig(requests_per_window=5, window_seconds=1))
            
            class MockConn:
                class user:
                    id = "test_user"
            
            allowed_count = 0
            for _ in range(10):
                allowed, _ = await rl.check_rate_limit(MockConn(), "test")
                if allowed:
                    allowed_count += 1
            
            return allowed_count
        
        result = asyncio.run(check_async())
        # Should allow initial tokens + burst, then block
        assert result >= 5  # At least the initial tokens
        print(f"✅ Async rate checking OK (allowed {result}/10)")
        tests_passed += 1
    except Exception as e:
        print(f"❌ Async rate checking FAILED: {e}")
        tests_failed += 1
    
    return tests_passed, tests_failed


def test_exceptions():
    """Test Exceptions module."""
    print("\n" + "="*60)
    print("⚠️  TESTING EXCEPTIONS")
    print("="*60)
    
    from exceptions import (
        RTSPRecorderError,
        ConfigurationError,
        InvalidConfigError,
        MissingConfigError,
        DatabaseError,
        DatabaseConnectionError,
        PersonNotFoundError,
        ValidationError,
        handle_exception,
    )
    
    tests_passed = 0
    tests_failed = 0
    
    # Test 1: Base exception
    try:
        e = RTSPRecorderError("Test error", {"key": "value"})
        assert e.message == "Test error"
        assert e.details["key"] == "value"
        d = e.to_dict()
        assert d["error"] == "RTSPRecorderError"
        print("✅ Base exception OK")
        tests_passed += 1
    except Exception as ex:
        print(f"❌ Base exception FAILED: {ex}")
        tests_failed += 1
    
    # Test 2: InvalidConfigError
    try:
        e = InvalidConfigError("retention_days", -5, "Must be positive")
        assert "retention_days" in e.message
        assert e.details["value"] == "-5"
        print("✅ InvalidConfigError OK")
        tests_passed += 1
    except Exception as ex:
        print(f"❌ InvalidConfigError FAILED: {ex}")
        tests_failed += 1
    
    # Test 3: PersonNotFoundError
    try:
        e = PersonNotFoundError("person_123")
        assert "person_123" in e.message
        assert e.details["person_id"] == "person_123"
        print("✅ PersonNotFoundError OK")
        tests_passed += 1
    except Exception as ex:
        print(f"❌ PersonNotFoundError FAILED: {ex}")
        tests_failed += 1
    
    # Test 4: ValidationError
    try:
        e = ValidationError("name", "too short")
        assert "name" in e.message
        d = e.to_dict()
        assert d["details"]["field"] == "name"
        print("✅ ValidationError OK")
        tests_passed += 1
    except Exception as ex:
        print(f"❌ ValidationError FAILED: {ex}")
        tests_failed += 1
    
    # Test 5: handle_exception utility
    try:
        result = handle_exception(ValueError("Test"), "context")
        assert result["error"] == "ValueError"
        assert result["details"]["context"] == "context"
        
        result2 = handle_exception(ValidationError("f", "r"))
        assert result2["error"] == "ValidationError"
        print("✅ handle_exception utility OK")
        tests_passed += 1
    except Exception as ex:
        print(f"❌ handle_exception utility FAILED: {ex}")
        tests_failed += 1
    
    # Test 6: Inheritance
    try:
        e = DatabaseConnectionError("/path/db", "error")
        assert isinstance(e, RTSPRecorderError)
        assert isinstance(e, DatabaseError)
        print("✅ Exception inheritance OK")
        tests_passed += 1
    except Exception as ex:
        print(f"❌ Exception inheritance FAILED: {ex}")
        tests_failed += 1
    
    return tests_passed, tests_failed


def test_performance():
    """Test Performance Monitor module."""
    print("\n" + "="*60)
    print("📊 TESTING PERFORMANCE MONITOR")
    print("="*60)
    
    from performance import (
        PerformanceMonitor,
        OperationMetric,
        OperationStats,
        get_performance_monitor,
        reset_performance_monitor,
    )
    
    tests_passed = 0
    tests_failed = 0
    
    # Test 1: OperationMetric
    try:
        start = time.time()
        metric = OperationMetric(name="test_op", start_time=start)
        time.sleep(0.05)
        metric.end_time = time.time()
        
        assert metric.duration_ms >= 40  # At least 40ms
        d = metric.to_dict()
        assert d["name"] == "test_op"
        assert d["success"] == True
        print(f"✅ OperationMetric OK ({metric.duration_ms:.1f}ms)")
        tests_passed += 1
    except Exception as e:
        print(f"❌ OperationMetric FAILED: {e}")
        tests_failed += 1
    
    # Test 2: OperationStats
    try:
        stats = OperationStats(name="test")
        assert stats.total_calls == 0
        assert stats.success_rate == 100.0
        
        # Record an operation
        metric = OperationMetric(
            name="test",
            start_time=time.time(),
            end_time=time.time() + 0.1,
            success=True
        )
        stats.record(metric)
        
        assert stats.total_calls == 1
        assert stats.successful_calls == 1
        print("✅ OperationStats OK")
        tests_passed += 1
    except Exception as e:
        print(f"❌ OperationStats FAILED: {e}")
        tests_failed += 1
    
    # Test 3: PerformanceMonitor measure context
    try:
        monitor = PerformanceMonitor()
        
        with monitor.measure("test_operation") as m:
            time.sleep(0.02)
            m.metadata["items"] = 5
        
        stats = monitor.get_stats("test_operation")
        assert stats["total_calls"] == 1
        assert stats["avg_duration_ms"] >= 15
        print("✅ Monitor measure context OK")
        tests_passed += 1
    except Exception as e:
        print(f"❌ Monitor measure context FAILED: {e}")
        tests_failed += 1
    
    # Test 4: Track decorator
    try:
        monitor = PerformanceMonitor()
        
        @monitor.track("decorated_func")
        def do_work():
            time.sleep(0.01)
            return "done"
        
        result = do_work()
        assert result == "done"
        
        stats = monitor.get_stats("decorated_func")
        assert stats["total_calls"] == 1
        print("✅ Track decorator OK")
        tests_passed += 1
    except Exception as e:
        print(f"❌ Track decorator FAILED: {e}")
        tests_failed += 1
    
    # Test 5: Get summary
    try:
        monitor = PerformanceMonitor()
        
        for _ in range(3):
            with monitor.measure("op1"):
                time.sleep(0.01)
        
        for _ in range(2):
            with monitor.measure("op2"):
                time.sleep(0.02)
        
        summary = monitor.get_summary()
        assert summary["total_operations"] == 5
        assert summary["operations_tracked"] == 2
        assert "slowest_operations" in summary
        print("✅ Get summary OK")
        tests_passed += 1
    except Exception as e:
        print(f"❌ Get summary FAILED: {e}")
        tests_failed += 1
    
    # Test 6: Reset
    try:
        monitor = PerformanceMonitor()
        
        with monitor.measure("test"):
            pass
        
        assert len(monitor.get_stats()) > 0
        
        monitor.reset()
        
        assert len(monitor.get_stats()) == 0
        print("✅ Reset OK")
        tests_passed += 1
    except Exception as e:
        print(f"❌ Reset FAILED: {e}")
        tests_failed += 1
    
    return tests_passed, tests_failed


def test_migrations():
    """Test Migrations module."""
    print("\n" + "="*60)
    print("🔄 TESTING MIGRATIONS")
    print("="*60)
    
    import sqlite3
    import tempfile
    import os
    
    from migrations import (
        CURRENT_SCHEMA_VERSION,
        get_current_version,
        run_migrations,
        check_migration_status,
        initialize_schema,
    )
    
    tests_passed = 0
    tests_failed = 0
    
    # Test 1: Schema version constant
    try:
        assert CURRENT_SCHEMA_VERSION >= 2
        print(f"✅ Schema version is {CURRENT_SCHEMA_VERSION}")
        tests_passed += 1
    except Exception as e:
        print(f"❌ Schema version FAILED: {e}")
        tests_failed += 1
    
    # Test 2: Get version for new database
    try:
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE test (id INTEGER)")
        conn.commit()
        
        version = get_current_version(conn)
        assert version == 1  # No version table = v1
        
        conn.close()
        os.unlink(db_path)
        print("✅ Get version for new DB OK")
        tests_passed += 1
    except Exception as e:
        print(f"❌ Get version for new DB FAILED: {e}")
        tests_failed += 1
    
    # Test 3: Check migration status - nonexistent
    try:
        status = check_migration_status("/nonexistent/path/db.sqlite")
        assert status["database_exists"] == False
        assert status["needs_migration"] == False
        print("✅ Migration status (nonexistent) OK")
        tests_passed += 1
    except Exception as e:
        print(f"❌ Migration status (nonexistent) FAILED: {e}")
        tests_failed += 1
    
    # Test 4: Run migration on new database
    try:
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        
        conn = sqlite3.connect(db_path)
        # Create v1 schema
        conn.execute("""
            CREATE TABLE recognition_history (
                id INTEGER PRIMARY KEY,
                person_name TEXT,
                camera_name TEXT,
                recognized_at TIMESTAMP
            )
        """)
        conn.commit()
        conn.close()
        
        result = run_migrations(db_path)
        assert result["success"] == True
        assert result["from_version"] == 1
        
        os.unlink(db_path)
        print("✅ Run migrations OK")
        tests_passed += 1
    except Exception as e:
        print(f"❌ Run migrations FAILED: {e}")
        tests_failed += 1
    
    # Test 5: Initialize schema
    try:
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        
        conn = sqlite3.connect(db_path)
        # Create base table needed for indexes
        conn.execute("""
            CREATE TABLE recognition_history (
                id INTEGER PRIMARY KEY,
                person_name TEXT,
                camera_name TEXT,
                recognized_at TIMESTAMP
            )
        """)
        
        initialize_schema(conn)
        
        # Check version table exists
        cursor = conn.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='schema_version'
        """)
        assert cursor.fetchone() is not None
        
        conn.close()
        os.unlink(db_path)
        print("✅ Initialize schema OK")
        tests_passed += 1
    except Exception as e:
        print(f"❌ Initialize schema FAILED: {e}")
        tests_failed += 1
    
    return tests_passed, tests_failed


def test_xss_protection():
    """Test XSS protection in JavaScript."""
    print("\n" + "="*60)
    print("🛡️  TESTING XSS PROTECTION")
    print("="*60)
    
    tests_passed = 0
    tests_failed = 0
    
    js_path = Path("/config/www/rtsp-recorder-card.js")
    
    # Test 1: File exists
    try:
        assert js_path.exists()
        print("✅ JavaScript file exists")
        tests_passed += 1
    except Exception as e:
        print(f"❌ JavaScript file check FAILED: {e}")
        tests_failed += 1
        return tests_passed, tests_failed
    
    content = js_path.read_text()
    
    # Test 2: escapeHtml function exists
    try:
        assert "_escapeHtml" in content
        assert "&amp;" in content  # HTML entity
        print("✅ _escapeHtml function exists")
        tests_passed += 1
    except Exception as e:
        print(f"❌ _escapeHtml function FAILED: {e}")
        tests_failed += 1
    
    # Test 3: escapeHtml is used for camera names
    try:
        # Check that camera names are escaped
        assert 'this._escapeHtml(c)' in content or 'this._escapeHtml(displayName)' in content
        print("✅ Camera names are escaped")
        tests_passed += 1
    except Exception as e:
        print(f"❌ Camera name escaping FAILED: {e}")
        tests_failed += 1
    
    # Test 4: escapeHtml is used in error messages
    try:
        assert 'this._escapeHtml(e.message' in content
        print("✅ Error messages are escaped")
        tests_passed += 1
    except Exception as e:
        print(f"❌ Error message escaping FAILED: {e}")
        tests_failed += 1
    
    # Test 5: Count innerHTML usages vs escaped usages
    try:
        innerHTML_count = content.count('innerHTML')
        escapeHtml_count = content.count('_escapeHtml')
        
        print(f"   innerHTML usages: {innerHTML_count}")
        print(f"   _escapeHtml usages: {escapeHtml_count}")
        
        # Should have reasonable escaping
        assert escapeHtml_count >= 10  # Multiple escaped usages
        print("✅ Sufficient escaping in place")
        tests_passed += 1
    except Exception as e:
        print(f"❌ Escaping count FAILED: {e}")
        tests_failed += 1
    
    return tests_passed, tests_failed


def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("🧪 RTSP RECORDER v1.1.0 - SECURITY & QUALITY MODULE TESTS")
    print("="*60)
    
    total_passed = 0
    total_failed = 0
    
    # Run all test suites
    p, f = test_rate_limiter()
    total_passed += p
    total_failed += f
    
    p, f = test_exceptions()
    total_passed += p
    total_failed += f
    
    p, f = test_performance()
    total_passed += p
    total_failed += f
    
    p, f = test_migrations()
    total_passed += p
    total_failed += f
    
    p, f = test_xss_protection()
    total_passed += p
    total_failed += f
    
    # Summary
    print("\n" + "="*60)
    print("📋 TEST SUMMARY")
    print("="*60)
    print(f"   ✅ Passed: {total_passed}")
    print(f"   ❌ Failed: {total_failed}")
    print(f"   📊 Total:  {total_passed + total_failed}")
    print(f"   📈 Rate:   {total_passed / (total_passed + total_failed) * 100:.1f}%")
    print("="*60)
    
    if total_failed == 0:
        print("🎉 ALL TESTS PASSED!")
        return 0
    else:
        print(f"⚠️  {total_failed} TESTS FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
