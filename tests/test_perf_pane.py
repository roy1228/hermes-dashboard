"""Tests for PerfPane metrics collection."""

import psutil
from collections import deque


def test_cpu_percent_returns_float():
    cpu = psutil.cpu_percent(interval=0.1)
    assert isinstance(cpu, float)
    assert 0 <= cpu <= 100


def test_memory_virtual_returns_usable_data():
    mem = psutil.virtual_memory()
    assert mem.total > 0
    assert mem.used > 0
    assert 0 <= mem.percent <= 100


def test_disk_usage_returns_usable_data():
    disk = psutil.disk_usage("/")
    assert disk.total > 0
    assert disk.used > 0
    assert 0 <= disk.percent <= 100


def test_net_io_counters_returns_data():
    net = psutil.net_io_counters()
    assert net is not None
    assert net.bytes_sent >= 0
    assert net.bytes_recv >= 0


def test_history_deque_maintains_maxlen():
    history = deque(maxlen=5)
    for i in range(10):
        history.append(i)
    assert len(history) == 5
    assert list(history) == [5, 6, 7, 8, 9]
