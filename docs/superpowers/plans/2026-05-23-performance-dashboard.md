# 性能看板 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 Hermes Dashboard 中新增"性能"Tab，以数字+趋势图形式实时监控 CPU、内存、磁盘、网络。

**Architecture:** 新增 `PerfPane(Widget)` 作为独立 Tab 内容，使用 `psutil` 采集指标，`textual.widgets.Sparkline` 展示趋势，通过 `run_worker` 定时采集，Tab 不可见时自动停止。

**Tech Stack:** Python, Textual (Sparkline), psutil, asyncio

---

### Task 1: 编写 PerfPane 数据采集逻辑的测试

**Files:**
- Create: `tests/test_perf_pane.py`

- [ ] **Step 1: 写测试**

```python
# tests/test_perf_pane.py
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
```

- [ ] **Step 2: 运行测试验证通过**

```bash
cd /home/clawbot/hermes_dashboard && ~/hermes-agent/venv/bin/python -m pytest tests/test_perf_pane.py -v
```

- [ ] **Step 3: 提交**

```bash
git add tests/test_perf_pane.py
git commit -m "test: add PerfPane metrics collection tests"
```

---

### Task 2: 实现 PerfPane Widget 类

**Files:**
- Modify: `hermes_dashboard.py` (在 `LogsPane` 类之后、`HermesDashboard` 类之前插入)

- [ ] **Step 1: 添加 psutil import**

在文件顶部 import 区域（约第 22 行 `from pathlib import Path` 之后）添加：

```python
import psutil
from collections import deque
```

同时在 widgets import 中添加 `Sparkline`：

```python
from textual.widgets import (
    Footer,
    Static,
    DataTable,
    Label,
    Button,
    Input,
    TextArea,
    TabbedContent,
    TabPane,
    Sparkline,
)
```

- [ ] **Step 2: 实现 PerfPane 类**

在 `LogsPane` 类之后（约第 1200 行附近）、`HermesDashboard` 类之前插入：

```python
# ──────────────────────────────────────────────
# 性能监控面板
# ──────────────────────────────────────────────
class PerfPane(Vertical):
    """实时性能监控：CPU、内存、磁盘、网络 I/O + Sparkline 趋势。"""

    HISTORY_LEN = 30
    INTERVAL = 5

    def __init__(self):
        super().__init__()
        self._cpu_history: deque[float] = deque(maxlen=self.HISTORY_LEN)
        self._mem_history: deque[float] = deque(maxlen=self.HISTORY_LEN)
        self._disk_history: deque[float] = deque(maxlen=self.HISTORY_LEN)
        self._net_up_history: deque[float] = deque(maxlen=self.HISTORY_LEN)
        self._net_down_history: deque[float] = deque(maxlen=self.HISTORY_LEN)
        self._prev_net = None
        self._prev_time = None

    def compose(self) -> ComposeResult:
        yield Label("[bold cyan]━━━ 系统性能 ━━━[/bold cyan]")
        yield Label("", id="perf-cpu-label")
        yield Sparkline([], id="perf-cpu-spark")
        yield Label("", id="perf-mem-label")
        yield Sparkline([], id="perf-mem-spark")
        yield Label("", id="perf-disk-label")
        yield Sparkline([], id="perf-disk-spark")
        yield Label("", id="perf-net-label")
        yield Sparkline([], id="perf-net-up-spark")
        yield Sparkline([], id="perf-net-down-spark")

    def on_mount(self):
        self._start_monitoring()

    def _start_monitoring(self):
        self.run_worker(self._monitor_loop, exclusive=True)

    async def _monitor_loop(self):
        """定时采集循环，Tab 不可见时自动退出。"""
        while self.display:
            try:
                self._collect_metrics()
            except Exception:
                pass
            await asyncio.sleep(self.INTERVAL)

    def _collect_metrics(self):
        """采集所有指标并更新 UI。"""
        # CPU
        cpu_pct = psutil.cpu_percent(interval=0.1)
        self._cpu_history.append(cpu_pct)
        cpu_cores = psutil.cpu_count()
        cpu_label = self.query_one("#perf-cpu-label", Label)
        cpu_label.update(f"  [bold]CPU:[/bold]  {cpu_pct:.1f}%  ({cpu_cores} cores)")
        cpu_spark = self.query_one("#perf-cpu-spark", Sparkline)
        cpu_spark.data = list(self._cpu_history)

        # Memory
        mem = psutil.virtual_memory()
        mem_gb_used = mem.used / (1024**3)
        mem_gb_total = mem.total / (1024**3)
        self._mem_history.append(mem.percent)
        mem_label = self.query_one("#perf-mem-label", Label)
        mem_label.update(
            f"  [bold]内存:[/bold]  {mem_gb_used:.1f} / {mem_gb_total:.1f} GB ({mem.percent:.1f}%)"
        )
        mem_spark = self.query_one("#perf-mem-spark", Sparkline)
        mem_spark.data = list(self._mem_history)

        # Disk
        disk = psutil.disk_usage("/")
        disk_gb_used = disk.used / (1024**3)
        disk_gb_total = disk.total / (1024**3)
        self._disk_history.append(disk.percent)
        disk_label = self.query_one("#perf-disk-label", Label)
        disk_label.update(
            f"  [bold]磁盘:[/bold]  {disk_gb_used:.0f} / {disk_gb_total:.0f} GB ({disk.percent:.1f}%)"
        )
        disk_spark = self.query_one("#perf-disk-spark", Sparkline)
        disk_spark.data = list(self._disk_history)

        # Network I/O (rate since last sample)
        import time
        now = time.time()
        net = psutil.net_io_counters()
        if self._prev_net is not None and self._prev_time is not None:
            dt = now - self._prev_time
            if dt > 0:
                up_kbs = (net.bytes_sent - self._prev_net.bytes_sent) / dt / 1024
                down_kbs = (net.bytes_recv - self._prev_net.bytes_recv) / dt / 1024
                up_kbs = max(0, up_kbs)
                down_kbs = max(0, down_kbs)
                self._net_up_history.append(up_kbs)
                self._net_down_history.append(down_kbs)
                net_label = self.query_one("#perf-net-label", Label)
                net_label.update(
                    f"  [bold]网络:[/bold]  ↑{up_kbs:.1f} KB/s  ↓{down_kbs:.1f} KB/s"
                )
                spark_up = self.query_one("#perf-net-up-spark", Sparkline)
                spark_up.data = list(self._net_up_history)
                spark_down = self.query_one("#perf-net-down-spark", Sparkline)
                spark_down.data = list(self._net_down_history)
        self._prev_net = net
        self._prev_time = now
```

- [ ] **Step 3: 添加 CSS 样式**

在 `HermesDashboard.DEFAULT_CSS` 中（约第 1359 行 `#tab-logs` 之后）添加：

```css
    #tab-perf { height: 1fr; }
    PerfPane { height: 1fr; }
    #perf-cpu-spark { height: 3; margin: 0 2 1 2; }
    #perf-mem-spark { height: 3; margin: 0 2 1 2; }
    #perf-disk-spark { height: 3; margin: 0 2 1 2; }
    #perf-net-up-spark { height: 3; margin: 0 2 1 2; }
    #perf-net-down-spark { height: 3; margin: 0 2 1 2; }
```

- [ ] **Step 4: 提交**

```bash
git add hermes_dashboard.py
git commit -m "feat: add PerfPane widget with CPU/mem/disk/net monitoring"
```

---

### Task 3: 将 PerfPane 集成到 Dashboard

**Files:**
- Modify: `hermes_dashboard.py` (HermesDashboard 类: compose, BINDINGS, on_tab_activated, action_refresh)

- [ ] **Step 1: 在 compose 中添加 TabPane**

找到 `HermesDashboard.compose()` 方法（约第 1373 行），在日志 Tab 之后添加：

```python
            yield TabPane("性能", PerfPane(), id="tab-perf")
```

完整 compose 变为：

```python
    def compose(self) -> ComposeResult:
        with TabbedContent(initial="tab-sessions"):
            yield TabPane("状态", StatusContent(), id="tab-status")
            yield TabPane("会话", SessionsPane(), id="tab-sessions")
            yield TabPane("任务", CronsPane(), id="tab-crons")
            yield TabPane("环境变量", EnvPane(), id="tab-env")
            yield TabPane("日志", LogsPane(), id="tab-logs")
            yield TabPane("性能", PerfPane(), id="tab-perf")
        yield Footer()
```

- [ ] **Step 2: 添加快捷键绑定**

在 `BINDINGS` 列表（约第 1362 行）中添加：

```python
        Binding("6", "switch_tab('tab-perf')", "性能"),
```

- [ ] **Step 3: 添加 Tab 激活时的刷新逻辑**

在 `on_tab_activated()` 方法中（约第 1402 行 `elif pane.id == "tab-logs"` 之后）添加：

```python
            elif pane.id == "tab-perf":
                for pp in self.query(PerfPane):
                    if pp.display:
                        pp._start_monitoring()
```

- [ ] **Step 4: 添加刷新动作中的 PerfPane 刷新**

在 `action_refresh()` 方法中（约第 1419 行 CronsPane 刷新之后）添加：

```python
            for pp in self.query(PerfPane):
                if pp.display:
                    pp._start_monitoring()
```

- [ ] **Step 5: 提交**

```bash
git add hermes_dashboard.py
git commit -m "feat: integrate PerfPane into dashboard tabs with keybinding"
```

---

### Task 4: 同步到 hermes-agent 目录并验证

**Files:**
- Copy: `hermes_dashboard.py` → `~/hermes-agent/hermes_dashboard.py`
- Copy: `time_utils.py` → `~/hermes-agent/time_utils.py`

- [ ] **Step 1: 同步文件**

```bash
cp /home/clawbot/hermes_dashboard/hermes_dashboard.py ~/hermes-agent/hermes_dashboard.py
cp /home/clawbot/hermes_dashboard/time_utils.py ~/hermes-agent/time_utils.py
```

- [ ] **Step 2: 验证可导入**

```bash
~/hermes-agent/venv/bin/python3 -c "
import sys
sys.path.insert(0, '/home/clawbot/hermes-agent')
from hermes_dashboard import PerfPane
print('PerfPane imported successfully')
print(f'HISTORY_LEN={PerfPane.HISTORY_LEN}')
print(f'INTERVAL={PerfPane.INTERVAL}')
"
```

- [ ] **Step 3: 运行全部测试**

```bash
cd /home/clawbot/hermes_dashboard && ~/hermes-agent/venv/bin/python -m pytest tests/ -v
```

- [ ] **Step 4: 提交同步确认**

```bash
git add hermes_dashboard.py time_utils.py
git commit -m "chore: sync performance dashboard to hermes-agent"
```
