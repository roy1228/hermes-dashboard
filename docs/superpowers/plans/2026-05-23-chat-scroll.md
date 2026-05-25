# 聊天区域滚动条和自动滚动 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在会话聊天区域显示可拖动的垂直滚动条，并在打开会话、收到新消息时自动滚动到最新内容。

**Architecture:** 修改 `hermes_dashboard.py` 中 `#sess-chat-feed` 的 CSS 启用垂直滚动条，在 4 个写入聊天内容的方法中设置 `cursor_position` 后调用 `log.scroll_end()`。

**Tech Stack:** Python, Textual (TextArea.scroll_end, scrollbar-size CSS)

---

### Task 1: 修改 CSS 显示垂直滚动条

**Files:**
- Modify: `hermes_dashboard.py` (DEFAULT_CSS 中 `#sess-chat-feed` 规则，约第 1437 行)

- [ ] **Step 1: 修改 scrollbar-size**

找到 `#sess-chat-feed` 的 CSS 规则：

```css
    #sess-chat-feed {
        height: 1fr;
        background: $surface;
        border: solid $primary 50%;
        scrollbar-size: 0 0;
    }
```

将 `scrollbar-size: 0 0;` 改为 `scrollbar-size: 1 0;`：

```css
    #sess-chat-feed {
        height: 1fr;
        background: $surface;
        border: solid $primary 50%;
        scrollbar-size: 1 0;
    }
```

`1` 启用垂直滚动条，`0` 不启用水平滚动条。

- [ ] **Step 2: 验证语法**

```bash
~/hermes-agent/venv/bin/python -c "import ast; ast.parse(open('hermes_dashboard.py').read()); print('OK')"
```

- [ ] **Step 3: 提交**

```bash
git add hermes_dashboard.py
git commit -m "feat: show vertical scrollbar in chat feed area"
```

---

### Task 2: 添加自动滚动到底部逻辑

**Files:**
- Modify: `hermes_dashboard.py` (4 个方法中的滚动调用)

- [ ] **Step 1: 在 `_add_chat_message` 中添加滚动**

找到 `_add_chat_message` 方法（约第 280-302 行），在 `log.cursor_position = len(log.text)` 后添加 `log.scroll_end()`：

```python
    def _add_chat_message(
        self,
        role: str,
        content: str,
        tool_name: str | None = None,
        is_meta: bool = False,
    ):
        log = self.query_one("#sess-chat-feed", TextArea)
        if role == "user":
            log.text += f"\n▸ 你: {content}\n"
        elif role == "assistant":
            log.text += f"\n◂ AI:\n{content}\n"
            if not is_meta:
                self._last_response = content
        elif role == "tool":
            name = tool_name or "工具"
            first_line = content.split("\n")[0].strip()[:120]
            total = len(content)
            if total > len(first_line):
                log.text += f"\n  🔧 {name}: {first_line}... ({total} 字符)\n"
            else:
                log.text += f"\n  🔧 {name}: {first_line}\n"
        log.cursor_position = len(log.text)
        log.scroll_end()
```

- [ ] **Step 2: 在 `_start_streaming_ai_message` 中添加滚动**

找到 `_start_streaming_ai_message` 方法（约第 304-310 行），在 `log.cursor_position = len(log.text)` 后添加 `log.scroll_end()`：

```python
    def _start_streaming_ai_message(self):
        log = self.query_one("#sess-chat-feed", TextArea)
        header = f"\n◂ AI:\n"
        log.text += header
        self._streaming_start_pos = len(log.text)
        self._streaming_content = ""
        log.cursor_position = len(log.text)
        log.scroll_end()
```

- [ ] **Step 3: 在 `_append_to_streaming_message` 中添加滚动**

找到 `_append_to_streaming_message` 方法（约第 312-319 行），在 `log.cursor_position = len(log.text)` 后添加 `log.scroll_end()`：

```python
    def _append_to_streaming_message(self, chunk: str):
        if self._streaming_start_pos is None:
            return
        log = self.query_one("#sess-chat-feed", TextArea)
        self._streaming_content += chunk
        full_text = log.text
        log.text = full_text[: self._streaming_start_pos] + self._streaming_content
        log.cursor_position = len(log.text)
        log.scroll_end()
```

- [ ] **Step 4: 在 `_load_session_chat` 中添加滚动**

找到 `_load_session_chat` 方法（约第 599-612 行），在设置 `log.text` 后添加 `log.scroll_end()`：

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
```

- [ ] **Step 5: 验证语法**

```bash
~/hermes-agent/venv/bin/python -c "import ast; ast.parse(open('hermes_dashboard.py').read()); print('OK')"
```

- [ ] **Step 6: 运行全部测试**

```bash
cd /home/clawbot/hermes_dashboard && ~/hermes-agent/venv/bin/python -m pytest tests/ -v
```

- [ ] **Step 7: 提交**

```bash
git add hermes_dashboard.py
git commit -m "feat: auto-scroll to bottom on new messages and session load"
```

---

### Task 3: 同步到 hermes-agent 目录

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

- [ ] **Step 3: 提交**

```bash
cd /home/clawbot/hermes_dashboard && git add hermes_dashboard.py
git commit -m "chore: sync chat scroll fix to hermes-agent"
```
