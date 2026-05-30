# 流式输出保持和运行中会话标记 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复流式输出跨会话丢失问题，在会话列表中标记正在运行的任务，支持自动刷新。

**Architecture:** 新增 `_running_sessions` 和 `_streaming_session_id` 状态，在流式任务生命周期中管理这些状态，扩展会话列表渲染逻辑显示 `●` 标记，添加定时刷新机制。

**Tech Stack:** Python, Textual, asyncio

---

### Task 1: 新增运行中会话状态管理

**Files:**
- Modify: `hermes_dashboard.py` (SessionsPane.__init__, _do_create_session, _do_resume_session)

- [ ] **Step 1: 在 __init__ 中新增状态字段**

找到 `SessionsPane.__init__`（约第 210-226 行），在 `self._streaming_content = ""` 之后添加：

```python
        self._running_sessions: set[str] = set()
        self._streaming_session_id: str | None = None
        self._auto_refresh_timer = None
```

- [ ] **Step 2: 在 _do_create_session 中管理 running 状态**

找到 `_do_create_session` 方法（约第 686 行），在 `self._start_streaming_ai_message()` 之前添加：

```python
        self._streaming_session_id = None  # 新会话，ID 未知
        self._running_sessions.add("pending")
```

在 `session_id, cleaned = self._parse_chat_output(full_output)` 之后（约第 709 行），找到 `if session_id:` 块，修改为：

```python
        if session_id:
            self._active_session_id = session_id
            self._is_new_conv = False
            self._streaming_session_id = session_id
            self._running_sessions.discard("pending")
            self._running_sessions.add(session_id)
            self._add_chat_message(
                "assistant", f"[dim]🔗 会话: {session_id}[/dim]", is_meta=True
            )
            self.load_sessions()
```

在方法末尾（`inp.read_only = False` 之前）添加清理逻辑：

```python
        self._running_sessions.discard("pending")
        if self._streaming_session_id:
            self._running_sessions.discard(self._streaming_session_id)
            self._streaming_session_id = None
        self._maybe_start_auto_refresh()
```

- [ ] **Step 3: 在 _do_resume_session 中管理 running 状态**

找到 `_do_resume_session` 方法（约第 725 行），在 `self._start_streaming_ai_message()` 之前添加：

```python
        self._streaming_session_id = sid
        self._running_sessions.add(sid)
        self._maybe_start_auto_refresh()
```

在方法末尾（`inp.read_only = False` 之前）添加清理逻辑：

```python
        self._running_sessions.discard(sid)
        if self._streaming_session_id == sid:
            self._streaming_session_id = None
        self._maybe_start_auto_refresh()
```

- [ ] **Step 4: 验证语法**

```bash
~/hermes-agent/venv/bin/python -c "import ast; ast.parse(open('hermes_dashboard.py').read()); print('OK')"
```

- [ ] **Step 5: 提交**

```bash
git add hermes_dashboard.py
git commit -m "feat: add running session state management"
```

---

### Task 2: 实现自动刷新机制

**Files:**
- Modify: `hermes_dashboard.py` (SessionsPane 新增方法 + on_mount)

- [ ] **Step 1: 新增 _maybe_start_auto_refresh 和 _stop_auto_refresh 方法**

在 `_toggle_group` 方法之后（约第 605 行附近）添加：

```python
    def _maybe_start_auto_refresh(self):
        """如果有运行中的会话，启动定时刷新。"""
        if self._running_sessions and not self._auto_refresh_timer:
            self._auto_refresh_timer = self.set_interval(10, self.load_sessions)

    def _stop_auto_refresh(self):
        """停止定时刷新。"""
        if self._auto_refresh_timer:
            self._auto_refresh_timer.stop()
            self._auto_refresh_timer = None
```

- [ ] **Step 2: 在 on_mount 中确保初始状态**

在 `on_mount` 方法（约第 265 行）末尾，确保自动刷新初始为停止状态（已在 __init__ 中设为 None，无需额外操作）。

- [ ] **Step 3: 验证语法**

```bash
~/hermes-agent/venv/bin/python -c "import ast; ast.parse(open('hermes_dashboard.py').read()); print('OK')"
```

- [ ] **Step 4: 提交**

```bash
git add hermes_dashboard.py
git commit -m "feat: add auto-refresh when sessions are running"
```

---

### Task 3: 会话列表显示运行中标记

**Files:**
- Modify: `hermes_dashboard.py` (SessionsPane._fetch_sessions 和 _search_sessions)

- [ ] **Step 1: 修改 _fetch_sessions 中的 active_marker 逻辑**

找到 `_fetch_sessions` 方法中的 `active_marker` 行（约第 418 行）：

```python
            active_marker = "◀" if sid == self._active_session_id else " "
```

改为：

```python
            if sid in self._running_sessions:
                active_marker = "●"
            elif sid == self._active_session_id:
                active_marker = "◀"
            else:
                active_marker = " "
```

- [ ] **Step 2: 修改 _search_sessions 中的标记逻辑**

找到 `_search_sessions` 方法中类似行（约第 584 行）：

```python
            active_marker = "◀" if sid == self._active_session_id else " "
```

改为：

```python
            if sid in self._running_sessions:
                active_marker = "●"
            elif sid == self._active_session_id:
                active_marker = "◀"
            else:
                active_marker = " "
```

- [ ] **Step 3: 验证语法**

```bash
~/hermes-agent/venv/bin/python -c "import ast; ast.parse(open('hermes_dashboard.py').read()); print('OK')"
```

- [ ] **Step 4: 运行全部测试**

```bash
cd /home/clawbot/hermes_dashboard && ~/hermes-agent/venv/bin/python -m pytest tests/ -v
```

- [ ] **Step 5: 提交**

```bash
git add hermes_dashboard.py
git commit -m "feat: show running marker (●) in session list"
```

---

### Task 4: 切回运行中会话时自动刷新

**Files:**
- Modify: `hermes_dashboard.py` (SessionsPane._load_session_chat)

- [ ] **Step 1: 修改 _load_session_chat**

找到 `_load_session_chat` 方法（约第 606-617 行），修改为：

```python
    def _load_session_chat(self, sid: str):
        self._is_new_conv = False
        self._active_session_id = sid
        log = self.query_one("#sess-chat-feed", TextArea)
        log.load_text("正在加载历史消息...\n")
        log.scroll_end()
        status = self.query_one("#sess-chat-status", Static)
        status.update("[dim]⏳ 加载中...[/dim]")
        inp = self.query_one("#sess-chat-input", TextArea)
        inp.read_only = False
        asyncio.create_task(self._fetch_session_messages(sid))

        # 如果该会话正在运行，标记状态
        if sid in self._running_sessions:
            status.update("[bold yellow]⏳ 任务运行中...[/bold yellow]")
```

- [ ] **Step 2: 验证语法**

```bash
~/hermes-agent/venv/bin/python -c "import ast; ast.parse(open('hermes_dashboard.py').read()); print('OK')"
```

- [ ] **Step 3: 提交**

```bash
git add hermes_dashboard.py
git commit -m "feat: show running status when switching to active session"
```

---

### Task 5: 同步到 hermes-agent 目录

**Files:**
- Copy: `hermes_dashboard.py` → `~/hermes-agent/hermes_dashboard.py`

- [ ] **Step 1: 同步文件**

```bash
cp /home/clawbot/hermes_dashboard/hermes_dashboard.py ~/hermes-agent/hermes_dashboard.py
```

- [ ] **Step 2: 验证可导入**

```bash
~/hermes-agent/venv/bin/python3 -c "
import sys
sys.path.insert(0, '/home/clawbot/hermes-agent')
from hermes_dashboard import SessionsPane
print('SessionsPane imported successfully')
"
```

- [ ] **Step 3: 运行全部测试**

```bash
cd /home/clawbot/hermes_dashboard && ~/hermes-agent/venv/bin/python -m pytest tests/ -v
```

- [ ] **Step 4: 提交**

```bash
cd /home/clawbot/hermes_dashboard && git add hermes_dashboard.py
git commit -m "chore: sync streaming persistence to hermes-agent"
```
