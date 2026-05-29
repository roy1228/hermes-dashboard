# 流式输出保持和运行中会话标记设计文档

## 概述

修复两个问题：
1. 通过 dashboard 发送消息后，切换到其他会话再切回来，看不到原对话的实时流式输出
2. 无法同时看到多个正在执行的任务的进度

## 问题根因

**问题 1**：流式输出写入 TextArea 内存缓冲区。切换会话时 `_load_session_chat` 调用 `log.load_text("")` 清空缓冲区，流式 worker 还在跑但写到了已清空区域。切回时从 `hermes sessions export` 加载，但正在运行的任务输出还没保存到服务端。

**问题 2**：`_active_session_id` 是单值，无法跟踪多个并发任务。

## 需求

- 切换会话时不丢失正在进行的流式输出
- 切回运行中的会话时自动刷新获取最新内容
- 会话列表中标记正在运行的会话（绿色圆点 `●`）
- 有运行中任务时自动刷新会话列表

## 设计

### 新增状态

```python
self._running_sessions: set[str] = set()  # 正在执行的会话 ID
self._streaming_session_id: str | None = None  # 当前正在流式输出的会话 ID
```

### 改动 1：流式输出跨会话保持

**`_do_create_session` / `_do_resume_session`**：
- 启动时设置 `self._streaming_session_id = session_id`（如果有）或临时标记
- 将 session_id 加入 `self._running_sessions`
- 完成后从 `_running_sessions` 移除，清除 `_streaming_session_id`

**`_load_session_chat`**：
- 如果切走的会话正在流式输出（`sid == self._streaming_session_id`），不清空 TextArea
- 切回时如果 `sid in self._running_sessions`，调用 `_fetch_session_messages` 刷新

### 改动 2：运行中会话标记

**`_fetch_sessions`**：
- 渲染会话行时，如果 `sid in self._running_sessions`，前缀显示 `●` 替代空格
- 已有 `active_marker` 逻辑，扩展为：`"●"` if running else `"◀"` if active else `" "`

**自动刷新**：
- 当 `_running_sessions` 非空时，启动一个定时任务每 10 秒调用 `load_sessions()`
- 当 `_running_sessions` 为空时，停止定时刷新

### 改动 3：会话列表显示效果

```
  ◀ 今天（24h 内）（3 个对话）
    ● 之前我写过一个性能看板...    26m ago   ← 运行中
    ◀ 看看你监控的 ai 信用数据...   1h ago    ← 当前选中
      盘前策略推演复查...          8h ago
```

## 集成点

| 文件 | 改动 |
|------|------|
| `hermes_dashboard.py` SessionsPane.__init__ | 新增 `_running_sessions`, `_streaming_session_id` |
| `hermes_dashboard.py` SessionsPane._do_create_session | 启动/完成时管理 running 状态 |
| `hermes_dashboard.py` SessionsPane._do_resume_session | 启动/完成时管理 running 状态 |
| `hermes_dashboard.py` SessionsPane._load_session_chat | 切回运行中会话时自动刷新 |
| `hermes_dashboard.py` SessionsPane._fetch_sessions | 渲染 `●` 标记 |
| `hermes_dashboard.py` SessionsPane.on_mount | 启动/停止定时刷新 |
