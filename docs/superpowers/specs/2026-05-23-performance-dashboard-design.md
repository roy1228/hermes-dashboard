# 性能看板设计文档

## 概述

在 Hermes Dashboard 中新增一个"性能"Tab 页面，实时监控服务器的系统资源负担（CPU、内存、磁盘、网络），以数字+趋势图的形式展示。

## 需求

- 监控指标：CPU 使用率、内存占用、磁盘空间、网络 I/O
- 展示形式：当前数值 + Sparkline 迷你趋势图
- 刷新频率：每 5 秒自动采集一次
- 智能刷新：仅在 Tab 页面可见时采集，切走后停止
- 历史深度：保留最近 30 个采样点（约 2.5 分钟趋势）

## 架构

### 组件结构

```
HermesDashboard
├── TabbedContent
│   ├── TabPane "状态" (StatusContent)
│   ├── TabPane "会话" (SessionsPane)
│   ├── TabPane "任务" (CronsPane)
│   ├── TabPane "环境变量" (EnvPane)
│   ├── TabPane "日志" (LogsPane)
│   └── TabPane "性能" (PerfPane) ← 新增
└── Footer
```

### PerfPane 组件

新增 `PerfPane(Widget)` 类，包含：

- 4 个指标行，每行包含：
  - 左侧：Label 显示指标名称和当前数值
  - 右侧：Sparkline 显示历史趋势
- 内部使用 `deque(maxlen=30)` 维护每个指标的历史数据
- 使用 `psutil` 库采集系统指标

### 指标定义

| 行 | 指标 | 数值格式 | Sparkline 数据 |
|---|------|----------|----------------|
| 1 | CPU | `CPU: 45.2% (8 cores)` | cpu_percent per core |
| 2 | 内存 | `内存: 6.2 / 16.0 GB (38.7%)` | mem_used_percent |
| 3 | 磁盘 | `磁盘: 120 / 500 GB (24.0%)` | disk_used_percent |
| 4 | 网络 | `网络: ↑12.3 ↓45.6 KB/s` | net_up KB/s + net_down KB/s |

### 数据流

```
psutil 采集 → 存入 deque(maxlen=30) → 更新 Sparkline.data → 渲染
```

### 生命周期

- `on_mount`: 初始化历史缓冲区，启动 `_monitor_loop` worker
- `_monitor_loop`: `while self.display` 循环，每 5 秒采集一次
- Tab 切走时 `self.display` 变为 False，循环自动退出
- Tab 切回时 `on_mount` 或 `reload_data` 重新启动采集

### 集成点

1. `hermes_dashboard.py` 中新增 `PerfPane` 类
2. `HermesDashboard.compose()` 新增 `TabPane("性能", PerfPane(), id="tab-perf")`
3. `BINDINGS` 新增 `Binding("6", "switch_tab('tab-perf')", "性能")`
4. `on_tab_activated()` 新增 `tab-perf` 分支
5. `action_refresh()` 新增 `PerfPane` 刷新逻辑
6. CSS 中新增 `#tab-perf` 样式

### 依赖

- `psutil`（已安装在 hermes-agent venv 中）
- `textual.widgets.Sparkline`（Textual >= 8.0 已支持）
- 无需新增外部依赖

## 错误处理

- `psutil` 采集失败时显示 `(error)` 占位
- 网络 I/O 首次采集无历史数据时显示 `--`
- Worker 超时或异常时不阻塞 UI
