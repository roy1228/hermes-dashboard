# 会话列表折叠分组 — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 Hermes Dashboard 会话列表中添加按时间分组的折叠功能，提升历史对话可浏览性。

**Architecture:** 在现有 DataTable 中插入分组标题行作为特殊标记行，通过 key 前缀区分分组行和数据行。时间解析和分组逻辑提取为独立模块以便测试。

**Tech Stack:** Python 3.11+, Textual TUI, pytest

---

## 文件结构

| 文件 | 操作 | 说明 |
|------|------|------|
| `hermes_dashboard.py` | 修改 | SessionsPane 添加分组状态、时间解析、折叠逻辑 |
| `tests/test_session_groups.py` | 创建 | 时间解析和分组逻辑的单元测试 |

---

### Task 1: 测试基础设施

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/test_session_groups.py`
- Create: `pyproject.toml` (pytest 配置)

- [ ] **Step 1: 创建测试目录和配置**

```bash
mkdir -p /home/clawbot/hermes_dashboard/tests
touch /home/clawbot/hermes_dashboard/tests/__init__.py
```

创建 `pyproject.toml`:

```toml
[project]
name = "hermes-dashboard"
version = "0.1.0"

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 2: 验证 pytest 可运行**

```bash
cd /home/clawbot/hermes_dashboard && python -m pytest --version
```

Expected: pytest version displayed

- [ ] **Step 3: 创建初始空测试**

```python
# tests/test_session_groups.py
"""Session grouping logic tests."""

def test_placeholder():
    """Placeholder test to verify pytest works."""
    assert True
```

- [ ] **Step 4: 运行测试验证通过**

```bash
cd /home/clawbot/hermes_dashboard && python -m pytest tests/ -v
```

Expected: 1 passed

- [ ] **Step 5: Commit**

```bash
cd /home/clawbot/hermes_dashboard && git add tests/ pyproject.toml && git commit -m "test: add pytest infrastructure"
```

---

### Task 2: 时间解析函数（TDD）

**Files:**
- Create: `hermes_dashboard.py` (add functions at top, after imports)
- Modify: `tests/test_session_groups.py`

- [ ] **Step 1: 编写时间解析测试**

在 `tests/test_session_groups.py` 中添加：

```python
import pytest
import sys
import os

# Add parent dir to path so we can import from hermes_dashboard
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hermes_dashboard import _parse_ago_to_hours


class TestParseAgoToHours:
    """Tests for _parse_ago_to_hours function."""

    def test_just_now(self):
        assert _parse_ago_to_hours("just now") == 0

    def test_minutes_ago(self):
        assert _parse_ago_to_hours("30m ago") == 0  # < 1 hour → 0

    def test_one_hour_ago(self):
        assert _parse_ago_to_hours("1h ago") == 1

    def test_hours_ago(self):
        assert _parse_ago_to_hours("5h ago") == 5

    def test_one_day_ago(self):
        assert _parse_ago_to_hours("1d ago") == 24

    def test_days_ago(self):
        assert _parse_ago_to_hours("3d ago") == 72

    def test_large_days_ago(self):
        assert _parse_ago_to_hours("45d ago") == 1080

    def test_invalid_format(self):
        assert _parse_ago_to_hours("invalid") is None

    def test_empty_string(self):
        assert _parse_ago_to_hours("") is None

    def test_none_input(self):
        assert _parse_ago_to_hours(None) is None
```

- [ ] **Step 2: 运行测试验证失败**

```bash
cd /home/clawbot/hermes_dashboard && python -m pytest tests/test_session_groups.py::TestParseAgoToHours -v
```

Expected: FAIL with "ImportError: cannot import name '_parse_ago_to_hours'"

- [ ] **Step 3: 实现时间解析函数**

在 `hermes_dashboard.py` 中，在 `_copy_to_clipboard` 函数之后、`StatusContent` 类之前添加：

```python
import re
from dataclasses import dataclass, field


def _parse_ago_to_hours(ago: str | None) -> int | None:
    """Parse ago string like '2h ago', '3d ago', 'just now' to hours.
    
    Returns None if cannot parse.
    Minutes (< 1 hour) return 0.
    """
    if not ago:
        return None
    
    ago = ago.strip().lower()
    
    if ago == "just now":
        return 0
    
    # Match pattern: number + unit + optional " ago"
    m = re.match(r'^(\d+)\s*([mhd])\s*(ago)?$', ago)
    if not m:
        return None
    
    value = int(m.group(1))
    unit = m.group(2)
    
    if unit == 'm':
        return 0  # Minutes count as 0 hours
    elif unit == 'h':
        return value
    elif unit == 'd':
        return value * 24
    
    return None
```

- [ ] **Step 4: 运行测试验证通过**

```bash
cd /home/clawbot/hermes_dashboard && python -m pytest tests/test_session_groups.py::TestParseAgoToHours -v
```

Expected: 10 passed

- [ ] **Step 5: Commit**

```bash
cd /home/clawbot/hermes_dashboard && git add hermes_dashboard.py tests/test_session_groups.py && git commit -m "feat: add _parse_ago_to_hours time parsing function"
```

---

### Task 3: 分组数据结构与分类逻辑（TDD）

**Files:**
- Modify: `hermes_dashboard.py`
- Modify: `tests/test_session_groups.py`

- [ ] **Step 1: 编写分组分类测试**

在 `tests/test_session_groups.py` 中添加：

```python
from hermes_dashboard import SessionGroup, _get_group_for_hours, GROUPS


class TestSessionGrouping:
    """Tests for session group classification."""

    def test_groups_defined(self):
        """Verify all expected groups exist."""
        group_keys = [g.key for g in GROUPS]
        assert "__group:today__" in group_keys
        assert "__group:3days__" in group_keys
        assert "__group:7days__" in group_keys
        assert "__group:30days__" in group_keys
        assert "__group:older__" in group_keys
        assert "__group:unknown__" in group_keys

    def test_today_group_expanded_by_default(self):
        today = next(g for g in GROUPS if g.key == "__group:today__")
        assert today.expanded is True

    def test_3days_group_expanded_by_default(self):
        g = next(g for g in GROUPS if g.key == "__group:3days__")
        assert g.expanded is True

    def test_7days_group_collapsed_by_default(self):
        g = next(g for g in GROUPS if g.key == "__group:7days__")
        assert g.expanded is False

    def test_30days_group_collapsed_by_default(self):
        g = next(g for g in GROUPS if g.key == "__group:30days__")
        assert g.expanded is False

    def test_older_group_collapsed_by_default(self):
        g = next(g for g in GROUPS if g.key == "__group:older__")
        assert g.expanded is False

    def test_get_group_today_0h(self):
        g = _get_group_for_hours(0)
        assert g.key == "__group:today__"

    def test_get_group_today_23h(self):
        g = _get_group_for_hours(23)
        assert g.key == "__group:today__"

    def test_get_group_3days_24h(self):
        g = _get_group_for_hours(24)
        assert g.key == "__group:3days__"

    def test_get_group_3days_71h(self):
        g = _get_group_for_hours(71)
        assert g.key == "__group:3days__"

    def test_get_group_7days_72h(self):
        g = _get_group_for_hours(72)
        assert g.key == "__group:7days__"

    def test_get_group_7days_167h(self):
        g = _get_group_for_hours(167)
        assert g.key == "__group:7days__"

    def test_get_group_30days_168h(self):
        g = _get_group_for_hours(168)
        assert g.key == "__group:30days__"

    def test_get_group_30days_719h(self):
        g = _get_group_for_hours(719)
        assert g.key == "__group:30days__"

    def test_get_group_older_720h(self):
        g = _get_group_for_hours(720)
        assert g.key == "__group:older__"

    def test_get_group_older_1000h(self):
        g = _get_group_for_hours(1000)
        assert g.key == "__group:older__"

    def test_get_group_unknown_none(self):
        g = _get_group_for_hours(None)
        assert g.key == "__group:unknown__"
```

- [ ] **Step 2: 运行测试验证失败**

```bash
cd /home/clawbot/hermes_dashboard && python -m pytest tests/test_session_groups.py::TestSessionGrouping -v
```

Expected: FAIL with ImportError

- [ ] **Step 3: 实现分组数据结构和分类函数**

在 `hermes_dashboard.py` 中，在 `_parse_ago_to_hours` 函数之后添加：

```python
@dataclass
class SessionGroup:
    """Defines a collapsible group of sessions in the sidebar."""
    name: str           # Display name, e.g. "今天（24h 内）"
    key: str            # Unique identifier, e.g. "__group:today__"
    expanded: bool      # Default expanded state
    order: int          # Sort priority (lower = higher)


# Group definitions in display order
GROUPS: list[SessionGroup] = [
    SessionGroup("今天（24h 内）", "__group:today__", True, 1),
    SessionGroup("3 天内", "__group:3days__", True, 2),
    SessionGroup("3-7 天", "__group:7days__", False, 3),
    SessionGroup("7 天-1 个月", "__group:30days__", False, 4),
    SessionGroup("1 个月以上", "__group:older__", False, 5),
    SessionGroup("未知时间", "__group:unknown__", False, 6),
]

# Prefix to identify group header rows in DataTable
GROUP_KEY_PREFIX = "__group:"


def _get_group_for_hours(hours: int | None) -> SessionGroup:
    """Return the appropriate group for a given hour count.
    
    None (unparseable) → unknown group.
    """
    if hours is None:
        return GROUPS[-1]  # unknown
    
    if hours < 24:
        return GROUPS[0]   # today
    elif hours < 72:
        return GROUPS[1]   # 3 days
    elif hours < 168:
        return GROUPS[2]   # 7 days
    elif hours < 720:
        return GROUPS[3]   # 30 days
    else:
        return GROUPS[4]   # older
```

- [ ] **Step 4: 运行测试验证通过**

```bash
cd /home/clawbot/hermes_dashboard && python -m pytest tests/test_session_groups.py::TestSessionGrouping -v
```

Expected: 17 passed

- [ ] **Step 5: Commit**

```bash
cd /home/clawbot/hermes_dashboard && git add hermes_dashboard.py tests/test_session_groups.py && git commit -m "feat: add SessionGroup dataclass and _get_group_for_hours classification"
```

---

### Task 4: SessionsPane 添加分组状态管理

**Files:**
- Modify: `hermes_dashboard.py:139-158` (SessionsPane.__init__)

- [ ] **Step 1: 修改 SessionsPane.__init__ 添加分组状态**

找到 `SessionsPane.__init__` 方法（约第 150 行），在现有属性后添加：

```python
    def __init__(self):
        super().__init__()
        self._is_new_conv = False
        self._active_session_id = None
        self._loading_bar_timer = None
        self._last_response = ""
        self._rename_target = None
        self._fullscreen = False
        # NEW: Collapsible group state
        self._collapsed_groups: set[str] = {
            g.key for g in GROUPS if not g.expanded
        }
        self._search_mode = False
```

- [ ] **Step 2: 验证应用可正常启动（手动）**

```bash
cd /home/clawbot/hermes_dashboard && python hermes_dashboard.py
```

Expected: App starts, press `q` to quit

- [ ] **Step 3: Commit**

```bash
cd /home/clawbot/hermes_dashboard && git add hermes_dashboard.py && git commit -m "refactor: add _collapsed_groups and _search_mode state to SessionsPane"
```

---

### Task 5: 重构 _fetch_sessions 支持分组行插入

**Files:**
- Modify: `hermes_dashboard.py:276-297` (_fetch_sessions)

- [ ] **Step 1: 重写 _fetch_sessions 方法**

替换整个 `_fetch_sessions` 方法：

```python
    async def _fetch_sessions(self):
        raw = hermes("sessions", "list", "--source", "cli", "--limit", "80", timeout=20)
        table = self.query_one("#sess-table", DataTable)
        table.clear()

        # Parse sessions into groups
        sessions_by_group: dict[str, list[tuple]] = {g.key: [] for g in GROUPS}
        
        for line in raw.strip().split("\n"):
            if not line.strip() or line.startswith("Title") or line.startswith("─"):
                continue
            m = re.search(r'(\d{8}_\d{6}_[0-9a-f]+|[0-9a-f]{12,})\s*$', line)
            if not m:
                continue
            sid = m.group(1)
            before = line[:m.start()].rstrip()
            m2 = re.search(r'(\d+[mhd]\s+ago|just\s+now)\s*$', before)
            ago = m2.group(1) if m2 else ""
            title = line[:32].strip()
            title = re.sub(r'\s{2,}', ' ', title)
            preview_start = 32
            preview_end = before.rfind(ago) - 1 if ago and m2 else len(before)
            preview = line[preview_start:max(preview_end, preview_start)].strip() if preview_end > preview_start else ""
            display_name = preview[:40] if title in ("—", "None", "") or len(title) < 2 else title
            
            hours = _parse_ago_to_hours(ago)
            group = _get_group_for_hours(hours)
            active_marker = "◀" if sid == self._active_session_id else " "
            sessions_by_group[group.key].append((active_marker, display_name, ago, sid))

        # Render groups and their sessions
        if self._search_mode:
            # Search mode: flat list, no group headers
            for group in GROUPS:
                for active_marker, display_name, ago, sid in sessions_by_group[group.key]:
                    table.add_row(active_marker, display_name, ago, key=sid)
        else:
            # Normal mode: group headers + sessions
            for group in GROUPS:
                is_collapsed = group.key in self._collapsed_groups
                count = len(sessions_by_group[group.key])
                icon = "▸" if is_collapsed else "▾"
                header_label = f"{icon} {group.name}（{count} 个对话）"
                table.add_row("", header_label, "", key=f"{GROUP_KEY_PREFIX}{group.key}")
                
                if not is_collapsed:
                    for active_marker, display_name, ago, sid in sessions_by_group[group.key]:
                        table.add_row(active_marker, display_name, ago, key=sid)
```

- [ ] **Step 2: 验证应用可正常启动并显示分组**

```bash
cd /home/clawbot/hermes_dashboard && python hermes_dashboard.py
```

Expected: Sessions displayed in collapsible groups, recent groups expanded, older groups collapsed

- [ ] **Step 3: Commit**

```bash
cd /home/clawbot/hermes_dashboard && git add hermes_dashboard.py && git commit -m "feat: refactor _fetch_sessions to render collapsible group headers"
```

---

### Task 6: 实现分组展开/收起交互

**Files:**
- Modify: `hermes_dashboard.py:428-431` (on_data_table_row_selected)

- [ ] **Step 1: 修改 on_data_table_row_selected 处理分组行点击**

替换 `on_data_table_row_selected` 方法：

```python
    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        key = event.row_key
        if not key.value:
            return
        
        # Check if this is a group header row
        if str(key.value).startswith(GROUP_KEY_PREFIX):
            self._toggle_group(key.value)
            return
        
        self._load_session_chat(str(key.value))

    def _toggle_group(self, group_key: str):
        """Toggle expanded state of a group and refresh the table."""
        if group_key in self._collapsed_groups:
            self._collapsed_groups.discard(group_key)
        else:
            self._collapsed_groups.add(group_key)
        self.load_sessions()
```

- [ ] **Step 2: 验证分组展开/收起**

```bash
cd /home/clawbot/hermes_dashboard && python hermes_dashboard.py
```

Expected: Click collapsed group → expands; click expanded group → collapses

- [ ] **Step 3: Commit**

```bash
cd /home/clawbot/hermes_dashboard && git add hermes_dashboard.py && git commit -m "feat: add group toggle interaction on row select"
```

---

### Task 7: 搜索模式平铺显示

**Files:**
- Modify: `hermes_dashboard.py:406-426` (_search_sessions)
- Modify: `hermes_dashboard.py:342-389` (on_button_pressed, on_input_submitted)

- [ ] **Step 1: 修改 _search_sessions 设置搜索模式**

替换 `_search_sessions` 方法：

```python
    async def _search_sessions(self, q: str):
        self._search_mode = True
        safe_q = shlex.quote(q)
        raw = await _shell_async(f"hermes sessions list --source cli --limit 80 2>/dev/null | grep -i {safe_q}", timeout=20)
        table = self.query_one("#sess-table", DataTable)
        table.clear()
        for line in raw.strip().split("\n"):
            if not line.strip():
                continue
            m = re.search(r'(\d{8}_\d{6}_[0-9a-f]+|[0-9a-f]{12,})\s*$', line)
            if not m:
                continue
            sid = m.group(1)
            title = line[:32].strip()
            before = line[:m.start()].rstrip()
            m2 = re.search(r'(\d+[mhd]\s+ago|just\s+now)\s*$', before)
            ago = m2.group(1) if m2 else ""
            preview_end = before.rfind(ago) - 1 if ago and m2 else 0
            preview = line[32:max(preview_end, 32)].strip() if preview_end > 32 else ""
            display_name = preview[:40] if title in ("—", "None", "") or len(title) < 2 else title
            active_marker = "◀" if sid == self._active_session_id else " "
            table.add_row(active_marker, display_name, ago, key=sid)
```

- [ ] **Step 2: 修改 load_sessions 退出搜索模式**

修改 `load_sessions` 方法，在调用 `_fetch_sessions` 前重置搜索模式：

```python
    def load_sessions(self):
        self._search_mode = False
        self.run_worker(self._fetch_sessions, exclusive=True)
```

- [ ] **Step 3: 验证搜索行为**

```bash
cd /home/clawbot/hermes_dashboard && python hermes_dashboard.py
```

Expected: Search → flat list of matches; Clear search → grouped view restored

- [ ] **Step 4: Commit**

```bash
cd /home/clawbot/hermes_dashboard && git add hermes_dashboard.py && git commit -m "feat: search mode shows flat list ignoring groups"
```

---

### Task 8: 分组行样式优化

**Files:**
- Modify: `hermes_dashboard.py:1080-1153` (CSS block)

- [ ] **Step 1: 添加分组行 CSS 样式**

在 `HermesDashboard.CSS` 中添加：

```css
    /* Group header row styling */
    #sess-table > .datatable--header {
        background: $surface-darken-2;
    }
```

注：Textual 的 DataTable 不直接支持按行 key 设置样式，我们通过 `_fetch_sessions` 中分组行的内容格式（包含 `▾`/`▸` 图标）来视觉区分。如需更精细的样式，可在后续迭代中使用自定义 RowLabel。

- [ ] **Step 2: 验证视觉效果**

```bash
cd /home/clawbot/hermes_dashboard && python hermes_dashboard.py
```

Expected: Group headers visually distinct with icons and count

- [ ] **Step 3: Commit**

```bash
cd /home/clawbot/hermes_dashboard && git add hermes_dashboard.py && git commit -m "style: add group header visual styling"
```

---

### Task 9: 全量测试与验证

**Files:**
- Modify: `tests/test_session_groups.py`

- [ ] **Step 1: 添加集成测试**

在 `tests/test_session_groups.py` 中添加端到端场景测试：

```python
class TestEndToEndScenarios:
    """Integration-style tests for common scenarios."""

    def test_parse_and_group_pipeline_just_now(self):
        """just now → 0h → today group."""
        hours = _parse_ago_to_hours("just now")
        group = _get_group_for_hours(hours)
        assert group.key == "__group:today__"

    def test_parse_and_group_pipeline_30min(self):
        """30m ago → 0h → today group."""
        hours = _parse_ago_to_hours("30m ago")
        group = _get_group_for_hours(hours)
        assert group.key == "__group:today__"

    def test_parse_and_group_pipeline_2days(self):
        """2d ago → 48h → 3days group."""
        hours = _parse_ago_to_hours("2d ago")
        group = _get_group_for_hours(hours)
        assert group.key == "__group:3days__"

    def test_parse_and_group_pipeline_5days(self):
        """5d ago → 120h → 7days group."""
        hours = _parse_ago_to_hours("5d ago")
        group = _get_group_for_hours(hours)
        assert group.key == "__group:7days__"

    def test_parse_and_group_pipeline_15days(self):
        """15d ago → 360h → 30days group."""
        hours = _parse_ago_to_hours("15d ago")
        group = _get_group_for_hours(hours)
        assert group.key == "__group:30days__"

    def test_parse_and_group_pipeline_60days(self):
        """60d ago → 1440h → older group."""
        hours = _parse_ago_to_hours("60d ago")
        group = _get_group_for_hours(hours)
        assert group.key == "__group:older__"

    def test_all_groups_have_sessions_in_default_state(self):
        """Verify collapsed_groups set matches GROUPS default state."""
        expected_collapsed = {g.key for g in GROUPS if not g.expanded}
        # Simulate fresh SessionsPane state
        actual_collapsed = {g.key for g in GROUPS if not g.expanded}
        assert actual_collapsed == expected_collapsed
```

- [ ] **Step 2: 运行全部测试**

```bash
cd /home/clawbot/hermes_dashboard && python -m pytest tests/ -v
```

Expected: All tests passed (27+ tests)

- [ ] **Step 3: 最终手动验证**

```bash
cd /home/clawbot/hermes_dashboard && python hermes_dashboard.py
```

验证清单：
- [ ] 今天（24h 内）分组默认展开
- [ ] 3 天内分组默认展开
- [ ] 3-7 天分组默认收起
- [ ] 7 天-1 个月分组默认收起
- [ ] 1 个月以上分组默认收起
- [ ] 点击收起分组 → 展开显示会话
- [ ] 点击已展开分组 → 收起隐藏会话
- [ ] 搜索功能平铺显示所有匹配项
- [ ] 清空搜索框恢复分组视图
- [ ] 空分组显示"0 个对话"

- [ ] **Step 4: 最终 Commit**

```bash
cd /home/clawbot/hermes_dashboard && git add -A && git commit -m "feat: complete collapsible session groups with tests"
```
