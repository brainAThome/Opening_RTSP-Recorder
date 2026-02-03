"""Performance monitoring for RTSP Recorder.

This module provides performance metrics collection and monitoring
for the integration's operations.

Feature: MED-002 Performance Monitoring (Audit Report v1.1.0)
"""
import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, TypeVar
from functools import wraps
import threading

_LOGGER = logging.getLogger(__name__)

F = TypeVar('F', bound=Callable[..., Any])


@dataclass
class OperationMetric:
    """Metrics for a single operation."""
    name: str
    start_time: float
    end_time: float = 0.0
    success: bool = True
    error: str | None = None
    metadata: dict = field(default_factory=dict)
    
    @property
    def duration_ms(self) -> float:
        """Get operation duration in milliseconds."""
        if self.end_time == 0:
            return (time.time() - self.start_time) * 1000
        return (self.end_time - self.start_time) * 1000
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "duration_ms": round(self.duration_ms, 2),
            "success": self.success,
            "error": self.error,
            "metadata": self.metadata,
            "timestamp": self.start_time,
        }


@dataclass
class OperationStats:
    """Aggregated statistics for an operation type."""
    name: str
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    total_duration_ms: float = 0.0
    min_duration_ms: float = float('inf')
    max_duration_ms: float = 0.0
    last_call: float = 0.0
    
    @property
    def avg_duration_ms(self) -> float:
        """Get average duration in milliseconds."""
        if self.total_calls == 0:
            return 0.0
        return self.total_duration_ms / self.total_calls
    
    @property
    def success_rate(self) -> float:
        """Get success rate as percentage."""
        if self.total_calls == 0:
            return 100.0
        return (self.successful_calls / self.total_calls) * 100
    
    def record(self, metric: OperationMetric) -> None:
        """Record a new operation metric."""
        self.total_calls += 1
        self.total_duration_ms += metric.duration_ms
        self.min_duration_ms = min(self.min_duration_ms, metric.duration_ms)
        self.max_duration_ms = max(self.max_duration_ms, metric.duration_ms)
        self.last_call = metric.end_time or time.time()
        
        if metric.success:
            self.successful_calls += 1
        else:
            self.failed_calls += 1
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "total_calls": self.total_calls,
            "successful_calls": self.successful_calls,
            "failed_calls": self.failed_calls,
            "success_rate": round(self.success_rate, 1),
            "avg_duration_ms": round(self.avg_duration_ms, 2),
            "min_duration_ms": round(self.min_duration_ms, 2) if self.min_duration_ms != float('inf') else 0,
            "max_duration_ms": round(self.max_duration_ms, 2),
            "last_call": self.last_call,
        }


class PerformanceMonitor:
    """Performance monitoring system for RTSP Recorder.
    
    Tracks operation durations, success rates, and provides
    aggregated statistics for monitoring and debugging.
    
    Example:
        monitor = PerformanceMonitor()
        
        @monitor.track("analyze_video")
        async def analyze_video(path):
            ...
        
        # Or manually:
        with monitor.measure("custom_operation") as m:
            do_something()
            m.metadata["frames"] = 100
    """
    
    # Max history entries per operation type
    MAX_HISTORY = 100
    
    def __init__(self):
        """Initialize performance monitor."""
        self._lock = threading.Lock()
        self._stats: dict[str, OperationStats] = {}
        self._history: dict[str, deque[OperationMetric]] = {}
        self._start_time = time.time()
        self._enabled = True
    
    @property
    def enabled(self) -> bool:
        """Check if monitoring is enabled."""
        return self._enabled
    
    @enabled.setter
    def enabled(self, value: bool) -> None:
        """Enable or disable monitoring."""
        self._enabled = value
    
    def _get_or_create_stats(self, name: str) -> OperationStats:
        """Get or create stats for an operation."""
        if name not in self._stats:
            self._stats[name] = OperationStats(name=name)
            self._history[name] = deque(maxlen=self.MAX_HISTORY)
        return self._stats[name]
    
    def record(self, metric: OperationMetric) -> None:
        """Record an operation metric.
        
        Args:
            metric: The metric to record
        """
        if not self._enabled:
            return
            
        with self._lock:
            stats = self._get_or_create_stats(metric.name)
            stats.record(metric)
            self._history[metric.name].append(metric)
    
    def measure(self, name: str) -> 'MeasureContext':
        """Context manager for measuring operation duration.
        
        Args:
            name: Operation name
            
        Returns:
            Context manager that tracks the operation
        """
        return MeasureContext(self, name)
    
    def track(self, name: str | None = None) -> Callable[[F], F]:
        """Decorator to track function performance.
        
        Args:
            name: Optional operation name (defaults to function name)
            
        Returns:
            Decorator function
        """
        def decorator(func: F) -> F:
            op_name = name or func.__name__
            
            if asyncio.iscoroutinefunction(func):
                @wraps(func)
                async def async_wrapper(*args, **kwargs):
                    with self.measure(op_name) as m:
                        try:
                            result = await func(*args, **kwargs)
                            return result
                        except Exception as e:
                            m.metric.success = False
                            m.metric.error = str(e)
                            raise
                return async_wrapper  # type: ignore
            else:
                @wraps(func)
                def sync_wrapper(*args, **kwargs):
                    with self.measure(op_name) as m:
                        try:
                            result = func(*args, **kwargs)
                            return result
                        except Exception as e:
                            m.metric.success = False
                            m.metric.error = str(e)
                            raise
                return sync_wrapper  # type: ignore
        return decorator
    
    def get_stats(self, name: str | None = None) -> dict:
        """Get statistics for operations.
        
        Args:
            name: Optional specific operation name
            
        Returns:
            Statistics dictionary
        """
        with self._lock:
            if name:
                if name in self._stats:
                    return self._stats[name].to_dict()
                return {}
            
            return {
                op_name: stats.to_dict()
                for op_name, stats in self._stats.items()
            }
    
    def get_history(self, name: str, limit: int = 50) -> list[dict]:
        """Get recent history for an operation.
        
        Args:
            name: Operation name
            limit: Maximum entries to return
            
        Returns:
            List of metric dictionaries
        """
        with self._lock:
            if name not in self._history:
                return []
            
            history = list(self._history[name])[-limit:]
            return [m.to_dict() for m in history]
    
    def get_summary(self) -> dict:
        """Get overall performance summary.
        
        Returns:
            Summary dictionary with all stats
        """
        with self._lock:
            total_calls = sum(s.total_calls for s in self._stats.values())
            total_errors = sum(s.failed_calls for s in self._stats.values())
            
            # Get slowest operations
            slowest = sorted(
                [s for s in self._stats.values() if s.total_calls > 0],
                key=lambda s: s.avg_duration_ms,
                reverse=True
            )[:5]
            
            # Get most called operations
            most_called = sorted(
                self._stats.values(),
                key=lambda s: s.total_calls,
                reverse=True
            )[:5]
            
            return {
                "uptime_seconds": round(time.time() - self._start_time, 1),
                "total_operations": total_calls,
                "total_errors": total_errors,
                "error_rate": round((total_errors / total_calls * 100) if total_calls > 0 else 0, 2),
                "operations_tracked": len(self._stats),
                "slowest_operations": [s.to_dict() for s in slowest],
                "most_called_operations": [s.to_dict() for s in most_called],
                "enabled": self._enabled,
            }
    
    def reset(self) -> None:
        """Reset all statistics."""
        with self._lock:
            self._stats.clear()
            self._history.clear()
            self._start_time = time.time()
    
    def reset_operation(self, name: str) -> None:
        """Reset statistics for a specific operation."""
        with self._lock:
            if name in self._stats:
                del self._stats[name]
            if name in self._history:
                del self._history[name]


class MeasureContext:
    """Context manager for measuring operation duration."""
    
    def __init__(self, monitor: PerformanceMonitor, name: str):
        """Initialize measurement context.
        
        Args:
            monitor: Parent performance monitor
            name: Operation name
        """
        self._monitor = monitor
        self.metric = OperationMetric(name=name, start_time=time.time())
    
    def __enter__(self) -> 'MeasureContext':
        """Enter context."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit context and record metric."""
        self.metric.end_time = time.time()
        
        if exc_type is not None:
            self.metric.success = False
            self.metric.error = str(exc_val)
        
        self._monitor.record(self.metric)
    
    @property
    def metadata(self) -> dict:
        """Access metric metadata."""
        return self.metric.metadata


# Global performance monitor instance
_performance_monitor: PerformanceMonitor | None = None


def get_performance_monitor() -> PerformanceMonitor:
    """Get the global performance monitor instance."""
    global _performance_monitor
    if _performance_monitor is None:
        _performance_monitor = PerformanceMonitor()
    return _performance_monitor


def reset_performance_monitor() -> None:
    """Reset the global performance monitor."""
    global _performance_monitor
    if _performance_monitor:
        _performance_monitor.reset()
