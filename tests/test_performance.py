"""Unit tests for Performance Monitoring module.

Feature: MED-001 Unit Test Framework (Audit Report v1.1.0)
"""
import asyncio
import time
from unittest.mock import MagicMock

import pytest
import sys
from pathlib import Path

# Add parent path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "custom_components" / "rtsp_recorder"))

try:
    from performance import (
        PerformanceMonitor,
        OperationMetric,
        OperationStats,
        get_performance_monitor,
        reset_performance_monitor,
    )
except ImportError:
    PerformanceMonitor = None


@pytest.mark.unit
class TestOperationMetric:
    """Tests for OperationMetric."""
    
    def test_metric_creation(self):
        """Test metric creation."""
        if PerformanceMonitor is None:
            pytest.skip("Module not available")
            
        metric = OperationMetric(name="test_op", start_time=time.time())
        
        assert metric.name == "test_op"
        assert metric.success is True
        assert metric.error is None
    
    def test_duration_calculation(self):
        """Test duration calculation."""
        if PerformanceMonitor is None:
            pytest.skip("Module not available")
            
        start = time.time()
        metric = OperationMetric(name="test", start_time=start)
        
        # Simulate some work
        time.sleep(0.1)
        
        metric.end_time = time.time()
        
        # Duration should be around 100ms
        assert 90 < metric.duration_ms < 200
    
    def test_to_dict(self):
        """Test conversion to dictionary."""
        if PerformanceMonitor is None:
            pytest.skip("Module not available")
            
        start = time.time()
        metric = OperationMetric(
            name="test", 
            start_time=start,
            end_time=start + 0.5,
            success=False,
            error="Test error",
            metadata={"key": "value"}
        )
        
        result = metric.to_dict()
        
        assert result["name"] == "test"
        assert result["success"] is False
        assert result["error"] == "Test error"
        assert result["metadata"] == {"key": "value"}
        assert 490 < result["duration_ms"] < 510


@pytest.mark.unit
class TestOperationStats:
    """Tests for OperationStats."""
    
    def test_initial_stats(self):
        """Test initial statistics values."""
        if PerformanceMonitor is None:
            pytest.skip("Module not available")
            
        stats = OperationStats(name="test_operation")
        
        assert stats.total_calls == 0
        assert stats.successful_calls == 0
        assert stats.failed_calls == 0
        assert stats.avg_duration_ms == 0.0
        assert stats.success_rate == 100.0
    
    def test_record_successful_operation(self):
        """Test recording a successful operation."""
        if PerformanceMonitor is None:
            pytest.skip("Module not available")
            
        stats = OperationStats(name="test")
        metric = OperationMetric(
            name="test",
            start_time=time.time(),
            end_time=time.time() + 0.1,
            success=True
        )
        
        stats.record(metric)
        
        assert stats.total_calls == 1
        assert stats.successful_calls == 1
        assert stats.failed_calls == 0
        assert stats.success_rate == 100.0
    
    def test_record_failed_operation(self):
        """Test recording a failed operation."""
        if PerformanceMonitor is None:
            pytest.skip("Module not available")
            
        stats = OperationStats(name="test")
        metric = OperationMetric(
            name="test",
            start_time=time.time(),
            end_time=time.time() + 0.1,
            success=False,
            error="Test failure"
        )
        
        stats.record(metric)
        
        assert stats.total_calls == 1
        assert stats.successful_calls == 0
        assert stats.failed_calls == 1
        assert stats.success_rate == 0.0
    
    def test_min_max_tracking(self):
        """Test min/max duration tracking."""
        if PerformanceMonitor is None:
            pytest.skip("Module not available")
            
        stats = OperationStats(name="test")
        
        # Record operations with different durations
        for duration in [0.1, 0.5, 0.2]:
            start = time.time()
            metric = OperationMetric(
                name="test",
                start_time=start,
                end_time=start + duration,
            )
            stats.record(metric)
        
        # Min should be ~100ms, max ~500ms
        assert 90 < stats.min_duration_ms < 110
        assert 490 < stats.max_duration_ms < 510


@pytest.mark.unit
class TestPerformanceMonitor:
    """Tests for PerformanceMonitor."""
    
    @pytest.fixture
    def monitor(self):
        """Create a fresh performance monitor."""
        if PerformanceMonitor is None:
            pytest.skip("Module not available")
        return PerformanceMonitor()
    
    def test_measure_context(self, monitor):
        """Test measure context manager."""
        with monitor.measure("test_operation") as m:
            time.sleep(0.1)
            m.metadata["items"] = 5
        
        stats = monitor.get_stats("test_operation")
        
        assert stats["total_calls"] == 1
        assert 90 < stats["avg_duration_ms"] < 200
    
    def test_measure_with_error(self, monitor):
        """Test measure context with error."""
        try:
            with monitor.measure("failing_op"):
                raise ValueError("Test error")
        except ValueError:
            pass
        
        stats = monitor.get_stats("failing_op")
        
        assert stats["failed_calls"] == 1
        assert stats["success_rate"] == 0.0
    
    def test_track_decorator_sync(self, monitor):
        """Test track decorator on sync function."""
        @monitor.track("sync_operation")
        def do_work():
            time.sleep(0.05)
            return "done"
        
        result = do_work()
        
        assert result == "done"
        stats = monitor.get_stats("sync_operation")
        assert stats["total_calls"] == 1
    
    @pytest.mark.asyncio
    async def test_track_decorator_async(self, monitor):
        """Test track decorator on async function."""
        @monitor.track("async_operation")
        async def do_async_work():
            await asyncio.sleep(0.05)
            return "async done"
        
        result = await do_async_work()
        
        assert result == "async done"
        stats = monitor.get_stats("async_operation")
        assert stats["total_calls"] == 1
    
    def test_get_all_stats(self, monitor):
        """Test getting all statistics."""
        with monitor.measure("op1"):
            pass
        with monitor.measure("op2"):
            pass
        
        all_stats = monitor.get_stats()
        
        assert "op1" in all_stats
        assert "op2" in all_stats
    
    def test_get_history(self, monitor):
        """Test getting operation history."""
        for i in range(5):
            with monitor.measure("repeated_op") as m:
                m.metadata["iteration"] = i
        
        history = monitor.get_history("repeated_op")
        
        assert len(history) == 5
        assert history[0]["metadata"]["iteration"] == 0
    
    def test_get_summary(self, monitor):
        """Test getting performance summary."""
        # Record some operations
        for _ in range(3):
            with monitor.measure("fast_op"):
                time.sleep(0.01)
        
        for _ in range(2):
            with monitor.measure("slow_op"):
                time.sleep(0.05)
        
        summary = monitor.get_summary()
        
        assert summary["total_operations"] == 5
        assert summary["operations_tracked"] == 2
        assert "slowest_operations" in summary
        assert "most_called_operations" in summary
    
    def test_disabled_monitor(self, monitor):
        """Test that disabled monitor doesn't record."""
        monitor.enabled = False
        
        with monitor.measure("disabled_op"):
            pass
        
        stats = monitor.get_stats("disabled_op")
        assert stats == {}  # No stats recorded
    
    def test_reset(self, monitor):
        """Test reset functionality."""
        with monitor.measure("test_op"):
            pass
        
        monitor.reset()
        
        all_stats = monitor.get_stats()
        assert all_stats == {}
    
    def test_reset_operation(self, monitor):
        """Test resetting single operation."""
        with monitor.measure("op1"):
            pass
        with monitor.measure("op2"):
            pass
        
        monitor.reset_operation("op1")
        
        all_stats = monitor.get_stats()
        assert "op1" not in all_stats
        assert "op2" in all_stats


@pytest.mark.unit
class TestGlobalPerformanceMonitor:
    """Tests for global performance monitor instance."""
    
    def test_get_instance(self):
        """Test getting global instance."""
        if PerformanceMonitor is None:
            pytest.skip("Module not available")
            
        monitor1 = get_performance_monitor()
        monitor2 = get_performance_monitor()
        
        # Should return same instance
        assert monitor1 is monitor2
    
    def test_reset_global(self):
        """Test resetting global monitor."""
        if PerformanceMonitor is None:
            pytest.skip("Module not available")
            
        monitor = get_performance_monitor()
        with monitor.measure("global_test"):
            pass
        
        reset_performance_monitor()
        
        # Stats should be cleared
        stats = get_performance_monitor().get_stats()
        assert stats == {}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
