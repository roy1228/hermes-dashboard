#!/usr/bin/env python3
"""Hermes TUI Dashboard — 终端交互式仪表盘，替代远程 WebUI。

核心功能：
  - 系统状态监控（模型/Provider/网关/会话数/资源）
  - 会话管理（列表/搜索/恢复/删除/修剪）
  - Cron 任务管理（列表/启停/手动触发/查看输出）
  - 环境变量管理（查看/添加/编辑/删除 ~/.hermes/.env）
  - 日志实时查看（agent/errors/gateway/webui）
  - 快速聊天入口

启动：~/hermes-agent/venv/bin/python ~/hermes-agent/hermes_dashboard.py
"""

import asyncio
import subprocess
import sys
import json
import os
import shlex
import re
import yaml
from pathlib import Path

from textual.app import App, ComposeResult
from textual.containers import Vertical, Horizontal
from textual.widgets import (
    Header, Footer, Static, DataTable, Label, Button, Input,
    TextArea, RichLog, TabbedContent, TabPane
)
from textual.binding import Binding
from textual import work, on
from rich.text import Text
from rich.markdown import Markdown

# ──────────────────────────────────────────────
# 工具函数
# ──────────────────────────────────────────────
HERMES_HOME = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
LOG_DIR = HERMES_HOME / "logs"

def _run(args: list[str] | str, timeout: int = 15, shell: bool = False) -> str:
    """Run command, return stripped stdout."""
    try:
        r = subprocess.run(
            args, shell=shell, capture_output=True, text=True, timeout=timeout,
            env={**os.environ, "HERMES_HOME": str(HERMES_HOME)},
        )
        return (r.stdout or "").strip()
    except subprocess.TimeoutExpired:
        return "(timeout)"
    except Exception as e:
        return f"(error: {e})"

def hermes(*args: str, timeout: int = 15) -> str:
    return _run(["hermes"] + list(args), timeout=timeout)

def shell(cmd: str, timeout: int = 15) -> str:
    return _run(cmd, timeout=timeout, shell=True)

async def _shell_async(cmd: str, timeout: int = 15) -> str:
    try:
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env={**os.environ, "HERMES_HOME": str(HERMES_HOME)},
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return (stdout.decode() if stdout else "").strip()
    except asyncio.TimeoutError:
        return "(timeout)"
    except Exception as e:
        return f"(error: {e})"

def _copy_to_clipboard(text: str):
    import base64
    encoded = base64.b64encode(text.encode()).decode()
    sys.stdout.write(f"\033]52;c;{encoded}\007")
    sys.stdout.flush()
    for cmd in (["wl-copy"], ["xclip", "-selection", "clipboard"], ["xsel", "-ib"]):
        try:
            subprocess.run(cmd, input=text, text=True, timeout=2, capture_output=True)
            break
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue


def _get_config() -> dict:
    config_path = HERMES_HOME / "config.yaml"
    if config_path.exists():
        try:
            with open(config_path) as f:
                return yaml.safe_load(f) or {}
        except Exception:
            pass
    return {}

def _get_provider_model() -> tuple[str, str]:
    cfg = _get_config()
    mc = cfg.get("model", {}) if isinstance(cfg, dict) else {}
    if isinstance(mc, dict):
        provider = str(mc.get("provider", "")).strip()
        model = str(mc.get("default", "") or mc.get("model", "")).strip()
        return (provider, model)
    return ("", "")


# ──────────────────────────────────────────────
# 系统状态面板
# ──────────────────────────────────────────────
class StatusContent(Static):
    """系统状态详细内容。"""

    def __init__(self):
        super().__init__("[dim]加载中...[/dim]")
        self.set_interval(120, self.reload_data)

    def on_mount(self):
        self.reload_data()

    def reload_data(self):
        self.run_worker(self._fetch, exclusive=True)

    async def _fetch(self):
        disk = shell("df -h / | tail -1")
        mem = shell("free -h | grep Mem")
        uptime = shell("uptime -p")
        load = shell("uptime | awk -F'load average:' '{print $2}'").strip()
        top_procs = shell("ps aux --sort=-%mem | head -6 | tail -5")
        skills = shell("ls ~/.hermes/skills/ 2>/dev/null | wc -l")
        plugins = shell("ls ~/.hermes/plugins/ 2>/dev/null | wc -l")

        content = (
            f"[bold cyan]━━━ 系统资源 ━━━[/bold cyan]\n\n"
            f"  [bold]运行时间:[/bold]  {uptime}\n"
            f"  [bold]负载:[/bold]      {load}\n"
            f"  [bold]内存:[/bold]      {mem}\n"
            f"  [bold]磁盘:[/bold]      {disk.strip()}\n\n"
            f"  [bold]Top 进程 (内存):[/bold]\n"
            f"  [dim]{top_procs}[/dim]\n\n"
            f"[bold cyan]━━━ Agent 组件 ━━━[/bold cyan]\n\n"
            f"  [bold]技能数:[/bold]    {skills}\n"
            f"  [bold]插件数:[/bold]    {plugins}\n"
            f"  [bold]Session DB:[/bold] {shell('ls ~/.hermes/sessions/ 2>/dev/null | wc -l')} 个会话文件"
        )
        self.update(content)


# ──────────────────────────────────────────────
# 会话面板（左右分栏）
# ──────────────────────────────────────────────
class SessionsPane(Vertical):
    """左右分栏：左侧会话列表 + 右侧对话上下文/聊天。"""

    BINDINGS = [
        Binding("enter", "chat_with_selected", "切换聊天"),
        Binding("n", "new_chat", "新对话"),
        Binding("ctrl+r", "rename_session", "重命名"),
        Binding("ctrl+y", "yank_last", "复制回复"),
        Binding("ctrl+c", "yank_last", "复制回复", show=False),
    ]

    def __init__(self):
        super().__init__()
        self._is_new_conv = False
        self._active_session_id = None
        self._loading_bar_timer = None
        self._last_response = ""
        self._rename_target = None

    def compose(self) -> ComposeResult:
        yield Label("[bold cyan]━━━ 会话管理 ━━━[/bold cyan]")
        yield Horizontal(
            Vertical(
                Horizontal(
                    Button("新对话", id="sess-new-btn", variant="success"),
                    Input(placeholder="搜索...", id="sess-search"),
                    Button("搜", id="sess-search-btn", variant="primary"),
                    Button("删除", id="sess-delete-btn", variant="warning"),
                    Button("重命名", id="sess-rename-btn"),
                    id="sess-search-bar"
                ),
                DataTable(id="sess-table"),
                id="sess-left"
            ),
            Vertical(
                Vertical(
                    Static("", id="sess-chat-status"),
                    Static("", id="sess-chat-loading-bar"),
                    id="sess-chat-status-area"
                ),
                RichLog(id="sess-chat-feed", markup=True, highlight=True, wrap=True),
                Horizontal(
                    Input(placeholder="输入消息 (Enter 发送)", id="sess-chat-input"),
                    Button("发送", id="sess-chat-send", variant="primary"),
                    Button("复制恢复命令", id="sess-resume-btn", variant="warning"),
                    id="sess-chat-bar"
                ),
                id="sess-right"
            ),
            id="sess-split-layout"
        )

    def on_mount(self):
        table = self.query_one("#sess-table", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        table.add_columns("", "会话", "时间")
        self.load_sessions()
        
        log = self.query_one("#sess-chat-feed", RichLog)
        log.write("[dim]← 选中左侧会话查看历史，或点击'新对话'开始。[/dim]\n[dim]鼠标拖拽选中文本后 Cmd+C 复制[/dim]")
        
        try:
            self._stop_loading_bar()
        except Exception:
            pass

    def _add_chat_message(self, role: str, content: str, tool_name: str | None = None):
        log = self.query_one("#sess-chat-feed", RichLog)
        if role == "user":
            log.write(f"[bold green]▸ 你[/bold green] {content}")
        elif role == "assistant":
            log.write("[bold cyan]◂ AI[/bold cyan]")
            log.write(Markdown(content))
            self._last_response = content
        elif role == "tool":
            name = tool_name or "工具"
            first_line = content.split("\n")[0].strip()[:120]
            total = len(content)
            if total > len(first_line):
                log.write(f"[dim]┊ [bold yellow]🔧 {name}[/bold yellow] {first_line}... [italic]({total} 字符)[/italic][/dim]")
            else:
                log.write(f"[dim]┊ [bold yellow]🔧 {name}[/bold yellow] {first_line}[/dim]")
        log.write("")
    def _start_loading_bar(self):
        if self._loading_bar_timer:
            self._loading_bar_timer.stop()

        bar = self.query_one("#sess-chat-loading-bar", Static)
        idx = 0

        def tick():
            nonlocal idx
            try:
                total = 40
                cycle = idx % (total * 2 - 4)
                if cycle >= total - 2:
                    pos = (total * 2 - 4) - cycle
                else:
                    pos = cycle

                seg_width = 6
                left = max(0, pos)
                mid_start = max(0, pos)
                mid_end = min(total, pos + seg_width)
                right = max(0, total - mid_end)

                bar_text = (
                    f"  [dim cyan]{'━' * left}[/dim cyan]"
                    f"[bold bright_cyan]{'━' * (mid_end - mid_start)}[/bold bright_cyan]"
                    f"[dim cyan]{'━' * right}[/dim cyan]"
                    f"  [dim]Agent 思考中...[/dim]"
                )
                bar.update(bar_text)
                idx += 1
            except Exception:
                pass

        self._loading_bar_timer = self.set_interval(0.06, tick)

    def _stop_loading_bar(self):
        """停止加载动效。"""
        if self._loading_bar_timer:
            self._loading_bar_timer.stop()
            self._loading_bar_timer = None
        try:
            self.query_one("#sess-chat-loading-bar", Static).update("")
        except Exception:
            pass

    def load_sessions(self):
        self.run_worker(self._fetch_sessions, exclusive=True)

    async def _fetch_sessions(self):
        raw = hermes("sessions", "list", "--source", "cli", "--limit", "80", timeout=20)
        table = self.query_one("#sess-table", DataTable)
        table.clear()
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
            active_marker = "◀" if sid == self._active_session_id else " "
            table.add_row(active_marker, display_name, ago, key=sid)

    def _selected_sid(self) -> str | None:
        table = self.query_one("#sess-table", DataTable)
        coord = table.cursor_coordinate
        if coord is not None:
            try:
                rows = list(table.ordered_rows)
                if 0 <= coord.row < len(rows):
                    key = rows[coord.row].key
                    return key.value if key else None
            except Exception:
                pass
        return None

    def _new_conversation(self):
        log = self.query_one("#sess-chat-feed", RichLog)
        log.clear()
        status.update("")

        self._is_new_conv = True
        self._active_session_id = None

        self._add_chat_message("assistant",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "💬 新对话 (Agent 模式)\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "输入第一条消息，将启动完整 Agent 流程\n"
            "(加载 Memory、Skills、Tools，自动保存)"
        )
        
        # 聚焦输入框
        try:
            inp = self.query_one("#sess-chat-input", Input)
            inp.focus()
        except Exception:
            pass

    @on(Button.Pressed, "#sess-new-btn")
    def handle_new_chat(self) -> None:
        self._new_conversation()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        sid = self._selected_sid()
        match event.button.id:
            case "sess-search-btn":
                q = self.query_one("#sess-search", Input).value.strip()
                if q:
                    self.run_worker(self._search_sessions(q), exclusive=True)
                else:
                    self.load_sessions()
            case "sess-chat-send":
                self._send_chat()
            case "sess-resume-btn":
                if sid:
                    self.app.copy_to_clipboard(f"hermes --resume {sid}")
                    s = self.query_one("#sess-chat-status", Static)
                    s.update("[bold bright_cyan]📋 命令已复制到剪贴板[/bold bright_cyan]")
                    self.set_timer(2, lambda: s.update(""))
            case "sess-delete-btn":
                if sid:
                    self.run_worker(self._delete_session(sid), exclusive=True)
            case "sess-rename-btn":
                if sid:
                    self._enter_rename_mode(sid)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "sess-chat-input":
            self._send_chat()
        elif event.input.id == "sess-search":
            q = self.query_one("#sess-search", Input).value.strip()
            if self._rename_target and q:
                self._do_rename(self._rename_target, q)
                self._rename_target = None
                self.query_one("#sess-search", Input).placeholder = "搜索..."
            elif q:
                self.run_worker(self._search_sessions(q), exclusive=True)
            else:
                self._rename_target = None
                self.query_one("#sess-search", Input).placeholder = "搜索..."
                self.load_sessions()

    def _do_rename(self, sid: str, new_title: str):
        s = self.query_one("#sess-chat-status", Static)
        s.update(f"[dim]⏳ 重命名 {sid}...[/dim]")
        self.run_worker(self._rename_session(sid, new_title), exclusive=True)

    async def _rename_session(self, sid: str, title: str):
        s = self.query_one("#sess-chat-status", Static)
        raw = hermes("sessions", "rename", sid, title, timeout=10)
        if "renamed" in raw.lower() or "set" in raw.lower() or not raw:
            s.update(f"[green]✅ 已重命名为: {title}[/green]")
        else:
            s.update(f"[yellow]重命名结果: {raw[:80]}[/yellow]")
        self.set_timer(3, lambda: s.update(""))
        self.load_sessions()

    async def _search_sessions(self, q: str):
        safe_q = shlex.quote(q)
        raw = shell(f"hermes sessions list --source cli --limit 80 2>/dev/null | grep -i {safe_q}")
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

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        key = event.row_key
        if key:
            self._load_session_chat(str(key.value))

    def _load_session_chat(self, sid: str):
        self._is_new_conv = False
        self._active_session_id = sid
        log = self.query_one("#sess-chat-feed", RichLog)
        log.clear()
        log.write("[dim]正在加载历史消息...[/dim]")
        self.run_worker(self._fetch_session_messages(sid), exclusive=True)

    async def _fetch_session_messages(self, sid: str):
        log = self.query_one("#sess-chat-feed", RichLog)
        log.clear()

        raw = shell(f"hermes sessions export --session-id {sid} - 2>/dev/null", timeout=25)
        if not raw:
            self._add_chat_message("assistant", "[red]无法获取会话内容[/red]")
            return

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            self._add_chat_message("assistant", "[red]解析失败[/red]")
            return

        msgs = data.get("messages", [])
        model = data.get("model", "?")

        log.clear()
        self._add_chat_message("assistant",
            f"**━━━ 会话: {sid} ━━━**\n\n"
            f"[dim]模型: {model} | 消息数: {len(msgs)} | 恢复命令: hermes --resume {sid}[/dim]"
        )

        for m in msgs:
            role = m.get("role", "")
            content = str(m.get("content", "")).strip()

            if not content and role != "assistant":
                continue
            if role == "assistant" and not content and not m.get("tool_calls"):
                continue

            if len(content) > 3000:
                content = content[:3000] + f"\n\n[dim italic]... (省略 {len(content) - 3000} 字符，完整内容请用 hermes --resume {sid} 查看)[/dim italic]"

            tool_name = None
            if role == "tool":
                tool_name = m.get("name") or m.get("tool_name") or "工具"
            self._add_chat_message(role, content, tool_name)

    def _send_chat(self):
        """发送消息：智能路由到新建或继续会话。"""
        inp = self.query_one("#sess-chat-input", Input)
        msg = inp.value.strip()
        if not msg:
            return
        inp.value = ""
        
        status = self.query_one("#sess-chat-status", Static)
        self._add_chat_message("user", msg)
        self._start_loading_bar()
        inp.disabled = True
        
        # 核心逻辑：如果有 active_id 就继续，否则新建
        if self._active_session_id:
            status.update("[bold yellow]💬 继续会话中...[/bold yellow]")
            asyncio.create_task(self._do_resume_session(self._active_session_id, msg))
        else:
            status.update("[bold yellow]🚀 启动新 Agent 会话...[/bold yellow]")
            asyncio.create_task(self._do_create_session(msg))

    async def _do_create_session(self, msg: str):
        status = self.query_one("#sess-chat-status", Static)
        inp = self.query_one("#sess-chat-input", Input)

        safe_msg = shlex.quote(msg)
        cmd = f"hermes chat -q {safe_msg} -Q 2>&1"

        raw = await _shell_async(cmd, timeout=300)
        if raw.startswith("(timeout)") or raw.startswith("(error:"):
            self._add_chat_message("assistant", f"[red]请求超时或错误: {raw}[/red]")
            self._stop_loading_bar()
            status.update("[red]❌ 请求失败[/red]")
            self.set_timer(3, lambda: status.update(""))
            inp.disabled = False
            return
        
        session_id, cleaned = self._parse_chat_output(raw)

        if cleaned:
            self._add_chat_message("assistant", cleaned)

        if session_id:
            self._active_session_id = session_id
            self._is_new_conv = False
            self._add_chat_message("assistant", f"[dim]🔗 会话: {session_id}[/dim]")
            self.load_sessions()

        self._stop_loading_bar()
        status.update("[bold green]✅ 完成[/bold green]")
        self.set_timer(3, lambda: status.update(""))
        inp.disabled = False

    async def _do_resume_session(self, sid: str, msg: str):
        status = self.query_one("#sess-chat-status", Static)
        inp = self.query_one("#sess-chat-input", Input)

        safe_msg = shlex.quote(msg)
        safe_sid = shlex.quote(sid)
        cmd = f"hermes chat -r {safe_sid} -q {safe_msg} -Q 2>&1"

        raw = await _shell_async(cmd, timeout=300)
        if raw.startswith("(timeout)") or raw.startswith("(error:"):
            self._add_chat_message("assistant", f"[red]请求超时或错误: {raw}[/red]")
            self._stop_loading_bar()
            status.update("[red]❌ 请求失败[/red]")
            self.set_timer(3, lambda: status.update(""))
            inp.disabled = False
            return
        
        session_id, cleaned = self._parse_chat_output(raw)

        if cleaned:
            self._add_chat_message("assistant", cleaned)

        if session_id:
            self._active_session_id = session_id

        self._stop_loading_bar()
        status.update("[bold green]✅ 回复完成[/bold green]")
        self.set_timer(3, lambda: status.update(""))
        inp.disabled = False

    def _parse_chat_output(self, raw: str) -> tuple[str | None, str]:
        """Parse hermes chat -Q output: (session_id, clean_response).
        
        -Q output: [↻ Resumed session <sid> (...)\n]\n
                    session_id: <sid>\n
                    <clean response>
        """
        if not raw:
            return (None, "")

        lines = raw.split("\n")
        session_id = None
        response_start = 0

        for i, line in enumerate(lines):
            if line.startswith("session_id:"):
                session_id = line.split(":", 1)[1].strip()
                response_start = i + 1
                break

        if response_start < len(lines) and not lines[response_start].strip():
            response_start += 1

        response = "\n".join(lines[response_start:]).strip()
        return (session_id, response)

    def action_chat_with_selected(self):
        sid = self._selected_sid()
        if sid:
            self._load_session_chat(sid)

    def action_new_chat(self):
        self._new_conversation()

    def action_rename_session(self):
        sid = self._selected_sid()
        if sid:
            self._enter_rename_mode(sid)

    def _enter_rename_mode(self, sid: str):
        inp = self.query_one("#sess-search", Input)
        self._rename_target = sid
        inp.value = ""
        inp.placeholder = f"重命名 {sid[:12]}... (Enter 确认)"
        inp.focus()
        s = self.query_one("#sess-chat-status", Static)
        s.update("[bold yellow]✏️ 在搜索框输入新名称后按 Enter[/bold yellow]")
        self.set_timer(4, lambda: s.update(""))

    def action_yank_last(self):
        if not self._last_response:
            return
        text = self._last_response.strip()
        if not text:
            return
        self.app.copy_to_clipboard(text)
        try:
            status = self.query_one("#sess-chat-status", Static)
            status.update("[bold bright_cyan]📋 已复制最后回复[/bold bright_cyan]")
            self.set_timer(2, lambda: status.update(""))
        except Exception:
            pass

    async def _delete_session(self, sid: str):
        s = self.query_one("#sess-chat-status", Static)
        s.update(f"[yellow]删除 {sid}...[/yellow]")
        raw = hermes("sessions", "delete", sid, timeout=15)
        if "deleted" in raw.lower() or not raw:
            s.update(f"[green]✅ 已删除 {sid}[/green]")
        else:
            s.update(f"[red]删除失败: {raw[:80]}[/red]")
        self.set_timer(3, lambda: s.update(""))
        if sid == self._active_session_id:
            self._active_session_id = None
            self._is_new_conv = True
        self.load_sessions()


# ──────────────────────────────────────────────
# Cron 面板
# ──────────────────────────────────────────────
class CronsPane(Vertical):
    def __init__(self):
        super().__init__()
        self._busy = False

    def compose(self) -> ComposeResult:
        yield Label("[bold cyan]━━━ 定时任务 ━━━[/bold cyan]")
        yield Horizontal(
            Button("刷新", id="cron-refresh", variant="primary"),
            Button("手动触发", id="cron-run", variant="success"),
            Button("暂停", id="cron-pause"),
            Button("恢复", id="cron-resume"),
            id="cron-toolbar"
        )
        yield DataTable(id="cron-table")
        yield Static("", id="cron-detail")

    def on_mount(self):
        table = self.query_one("#cron-table", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        table.add_columns("ID", "名称", "状态", "调度", "下次运行", "技能")
        self.load_crons()

    def load_crons(self):
        self.run_worker(self._fetch_crons, exclusive=True)

    async def _fetch_crons(self):
        raw = hermes("cron", "list", timeout=15)
        table = self.query_one("#cron-table", DataTable)
        table.clear()

        jobs = []
        current = {}
        for line in raw.split("\n"):
            s = line.strip()
            if not s:
                continue
            # Job ID line: a51296851293 [active]
            if "[" in s and "]" in s and len(s.split()[0]) >= 8:
                if current.get("job_id"):
                    jobs.append(current)
                parts = s.split()
                current = {
                    "job_id": parts[0],
                    "status": parts[1].strip("[]") if len(parts) > 1 else "unknown",
                    "name": "", "schedule": "", "next": "", "skills": ""
                }
            elif s.startswith("Name:"):
                current["name"] = s.split(":", 1)[1].strip()
            elif s.startswith("Schedule:"):
                current["schedule"] = s.split(":", 1)[1].strip()
            elif s.startswith("Next run:"):
                current["next"] = s.split(":", 1)[1].strip()
            elif s.startswith("Skills:"):
                current["skills"] = s.split(":", 1)[1].strip()
        if current.get("job_id"):
            jobs.append(current)

        for job in jobs:
            s = job.get("status", "")
            icon = {"active": "[green]●[/green]", "paused": "[yellow]●[/yellow]"}.get(s, "[red]●[/red]")
            table.add_row(
                job["job_id"][:12],
                job["name"],
                icon,
                job["schedule"],
                job["next"],
                job["skills"],
                key=job["job_id"]
            )

    def _selected_job_id(self) -> str | None:
        table = self.query_one("#cron-table", DataTable)
        coord = table.cursor_coordinate
        if coord is not None:
            try:
                rows = list(table.ordered_rows)
                if 0 <= coord.row < len(rows):
                    key = rows[coord.row].key
                    return key.value if key else None
            except Exception:
                pass
        return None

    def on_button_pressed(self, event: Button.Pressed) -> None:
        jid = self._selected_job_id()
        detail = self.query_one("#cron-detail", Static)
        if self._busy:
            return
        if event.button.id == "cron-refresh":
            self.load_crons()
        elif event.button.id == "cron-run" and jid:
            self._busy = True
            self._set_cron_buttons_disabled(True)
            detail.update(f"[dim]⏳ 正在触发 {jid[:12]}...[/dim]")
            self.run_worker(self._run_cron(jid), exclusive=True)
        elif event.button.id == "cron-pause" and jid:
            self._busy = True
            self._set_cron_buttons_disabled(True)
            detail.update(f"[dim]⏳ 正在暂停 {jid[:12]}...[/dim]")
            self.run_worker(self._pause_cron(jid), exclusive=True)
        elif event.button.id == "cron-resume" and jid:
            self._busy = True
            self._set_cron_buttons_disabled(True)
            detail.update(f"[dim]⏳ 正在恢复 {jid[:12]}...[/dim]")
            self.run_worker(self._resume_cron(jid), exclusive=True)

    def _set_cron_buttons_disabled(self, disabled: bool):
        for bid in ("cron-run", "cron-pause", "cron-resume"):
            try:
                btn = self.query_one(f"#{bid}", Button)
                btn.disabled = disabled
            except Exception:
                pass

    async def _run_cron(self, jid: str):
        try:
            detail = self.query_one("#cron-detail", Static)
            out = hermes("cron", "run", jid, timeout=30)
            detail.update(f"[green]已触发:\n{out[:500]}[/green]")
        finally:
            self._busy = False
            self._set_cron_buttons_disabled(False)

    async def _pause_cron(self, jid: str):
        try:
            detail = self.query_one("#cron-detail", Static)
            out = hermes("cron", "pause", jid, timeout=15)
            detail.update(f"[yellow]{out}[/yellow]")
            self.load_crons()
        finally:
            self._busy = False
            self._set_cron_buttons_disabled(False)

    async def _resume_cron(self, jid: str):
        try:
            detail = self.query_one("#cron-detail", Static)
            out = hermes("cron", "resume", jid, timeout=15)
            detail.update(f"[green]{out}[/green]")
            self.load_crons()
        finally:
            self._busy = False
            self._set_cron_buttons_disabled(False)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        jid = event.row_key
        if jid:
            self.run_worker(self._show_cron_detail(str(jid.value)), exclusive=True)

    async def _show_cron_detail(self, jid: str):
        detail = self.query_one("#cron-detail", Static)
        output = hermes("cron", "output", jid, timeout=15)
        if not output or "error" in output.lower()[:20]:
            output = "(无最近输出)"
        detail.update(
            f"[bold]任务:[/bold] {jid[:12]}\n"
            f"[bold]最近输出:[/bold]\n[dim]{output[:2000]}[/dim]"
        )


# ──────────────────────────────────────────────
# 环境变量面板
# ──────────────────────────────────────────────
ENV_PATH = HERMES_HOME / ".env"

def _mask_value(val: str, key: str) -> str:
    """Mask sensitive values."""
    sensitive = ["KEY", "SECRET", "TOKEN", "PASSWORD", "PASS", "AUTH"]
    if any(s in key.upper() for s in sensitive):
        if len(val) > 8:
            return val[:3] + "***" + val[-2:]
        return "***" if val else "(empty)"
    return val

def _parse_env(path: Path) -> list[dict]:
    """Parse .env file into list of {key, value, comment, raw}."""
    entries = []
    if not path.exists():
        return entries
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            entries.append({"raw": line, "key": "", "value": "", "comment": stripped, "is_comment": True})
            continue
        if "=" in stripped:
            k, v = stripped.split("=", 1)
            entries.append({"raw": line, "key": k.strip(), "value": v.strip(), "comment": "", "is_comment": False})
    return entries

def _write_env(path: Path, entries: list[dict]):
    """Write entries back to .env file."""
    lines = []
    for e in entries:
        if e.get("is_comment"):
            lines.append(e.get("raw", ""))
        else:
            lines.append(f"{e['key']}={e['value']}")
    path.write_text("\n".join(lines) + "\n")


class EnvPane(Vertical):
    def __init__(self):
        super().__init__()
        self._entries: list[dict] = []
        self._editing_key: str | None = None

    def compose(self) -> ComposeResult:
        yield Label("[bold cyan]━━━ 环境变量 ━━━[/bold cyan]")
        yield Horizontal(
            Button("刷新", id="env-refresh", variant="primary"),
            Button("添加", id="env-add", variant="success"),
            Button("编辑", id="env-edit"),
            Button("删除", id="env-delete", variant="warning"),
            id="env-toolbar"
        )
        yield DataTable(id="env-table")
        yield Static("", id="env-detail")
        yield Input(placeholder="KEY=VALUE (Enter 保存)", id="env-input")

    def on_mount(self):
        table = self.query_one("#env-table", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        table.add_columns("变量名", "值", "说明")
        self.load_env()

    def load_env(self):
        self.run_worker(self._fetch_env, exclusive=True)

    async def _fetch_env(self):
        self._entries = _parse_env(ENV_PATH)
        table = self.query_one("#env-table", DataTable)
        table.clear()
        for e in self._entries:
            if e.get("is_comment"):
                continue
            display_val = _mask_value(e["value"], e["key"])
            table.add_row(e["key"], display_val, "", key=e["key"])

    def _selected_key(self) -> str | None:
        table = self.query_one("#env-table", DataTable)
        coord = table.cursor_coordinate
        if coord is not None:
            try:
                rows = list(table.ordered_rows)
                if 0 <= coord.row < len(rows):
                    key = rows[coord.row].key
                    return key.value if key else None
            except Exception:
                pass
        return None

    def _reload_table(self):
        """Refresh table from current entries."""
        table = self.query_one("#env-table", DataTable)
        table.clear()
        for e in self._entries:
            if e.get("is_comment"):
                continue
            display_val = _mask_value(e["value"], e["key"])
            table.add_row(e["key"], display_val, "", key=e["key"])

    def on_button_pressed(self, event: Button.Pressed) -> None:
        inp = self.query_one("#env-input", Input)
        detail = self.query_one("#env-detail", Static)
        match event.button.id:
            case "env-refresh":
                self.load_env()
            case "env-add":
                self._editing_key = None
                inp.value = ""
                detail.update(
                    "[bold]添加环境变量[/bold]\n"
                    "在下方输入 KEY=VALUE 后按 Enter 保存"
                )
                inp.focus()
            case "env-edit":
                key = self._selected_key()
                if key:
                    entry = next((e for e in self._entries if e["key"] == key), None)
                    if entry:
                        self._editing_key = key
                        inp.value = f"{key}={entry['value']}"
                        detail.update(f"[bold]编辑: {key}[/bold]\n修改后按 Enter 保存")
                        inp.focus()
                else:
                    detail.update("[yellow]请先在表格中选中一个变量[/yellow]")
            case "env-delete":
                key = self._selected_key()
                if key:
                    self._entries = [e for e in self._entries if e["key"] != key]
                    _write_env(ENV_PATH, self._entries)
                    detail.update(f"[green]✅ 已删除 {key}[/green]")
                    self._reload_table()
                else:
                    detail.update("[yellow]请先在表格中选中一个变量[/yellow]")

    @on(Input.Submitted, "#env-input")
    def _on_env_submit(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        detail = self.query_one("#env-detail", Static)
        if not text or "=" not in text:
            detail.update("[yellow]格式错误，需要 KEY=VALUE[/yellow]")
            return
        key, value = text.split("=", 1)
        key, value = key.strip(), value.strip()
        if not key:
            detail.update("[yellow]变量名不能为空[/yellow]")
            return
        if self._editing_key:
            self._entries = [e for e in self._entries if e["key"] != self._editing_key]
        self._entries = [e for e in self._entries if e["key"] != key]
        self._entries.append({"key": key, "value": value, "comment": "", "is_comment": False})
        self._editing_key = None
        _write_env(ENV_PATH, self._entries)
        self._reload_table()
        self.query_one("#env-input", Input).value = ""
        detail.update(f"[green]✅ {key} 已保存[/green]")

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        key = event.row_key
        if key:
            key_val = key.value
            entry = next((e for e in self._entries if e["key"] == key_val), None)
            if entry:
                detail = self.query_one("#env-detail", Static)
                detail.update(
                    f"[bold]{key_val}[/bold]\n"
                    f"值: {_mask_value(entry['value'], key_val)}\n"
                    f"[dim]点击'编辑'修改此变量，点击'删除'移除[/dim]"
                )


# ──────────────────────────────────────────────
# 日志面板
# ──────────────────────────────────────────────
class LogsPane(Vertical):
    """日志查看器。"""

    def __init__(self):
        super().__init__()
        self._autorefresh = False
        self._current_log = "agent"
        self._refresh_timer = None

    def compose(self) -> ComposeResult:
        yield Label("[bold cyan]━━━ 日志查看 ━━━[/bold cyan]")
        yield Horizontal(
            Button("Agent 日志", id="log-agent", variant="primary"),
            Button("错误日志", id="log-errors"),
            Button("Gateway", id="log-gateway"),
            Button("WebUI", id="log-webui"),
            Button("自动刷新: 关", id="log-autorefresh", variant="default"),
            id="log-toolbar"
        )
        yield TextArea(id="log-viewer", language=None, read_only=True)

    def on_mount(self):
        self._load_log("agent")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        match event.button.id:
            case "log-agent":
                self._load_log("agent")
            case "log-errors":
                self._load_log("errors")
            case "log-gateway":
                self._load_log("gateway")
            case "log-webui":
                self._load_log("webui")
            case "log-autorefresh":
                self._autorefresh = not self._autorefresh
                btn = self.query_one("#log-autorefresh", Button)
                btn.label = f"自动刷新: {'开' if self._autorefresh else '关'}"
                btn.variant = "success" if self._autorefresh else "default"
                if self._autorefresh:
                    self._refresh_timer = self.set_interval(5, lambda: self._load_log(self._current_log))
                elif self._refresh_timer:
                    self._refresh_timer.stop()
                    self._refresh_timer = None

    def _load_log(self, log_type: str):
        self._current_log = log_type
        self.run_worker(self._fetch_log(log_type), exclusive=True)

    async def _fetch_log(self, log_type: str):
        viewer = self.query_one("#log-viewer", TextArea)
        paths = {
            "agent": str(LOG_DIR / "agent.log"),
            "errors": str(LOG_DIR / "errors.log"),
            "gateway": str(LOG_DIR / "gateway.log"),
            "webui": str(Path.home() / "hermes-webui" / "server.log"),
        }
        path = paths.get(log_type, "")
        if not path:
            viewer.text = "未知日志类型"
            return
        raw = shell(f"tail -500 {shlex.quote(path)} 2>/dev/null || echo '文件不存在'")
        viewer.text = raw[-80000:]
        try:
            viewer.cursor_position = len(viewer.text)
        except Exception:
            pass


# ──────────────────────────────────────────────
# 主 App
# ──────────────────────────────────────────────
class HermesDashboard(App):
    """Hermes Agent 终端仪表盘"""

    TITLE = "Hermes Agent Dashboard"
    SUB_TITLE = "终端版 — 按 ? 查看帮助"

    CSS = """
    Screen { background: $surface; }
    DataTable { border: solid $primary; }
    #sess-history, #cron-detail {
        height: 1fr;
        background: $surface-darken-1;
        border: solid $primary 50%;
    }
    #log-viewer { height: 1fr; }
    #chat-log { height: 1fr; }
    #chat-bar { dock: bottom; }
    
    /* 会话面板左右分栏 */
    #sess-split-layout {
        layout: horizontal;
        height: 1fr;
    }
    #sess-left {
        width: 30%;
        border: solid $primary 50%;
    }
    #sess-right {
        width: 1fr;
        border: solid $primary 50%;
    }
    #sess-table {
        height: 1fr;
    }
    #sess-chat-feed {
        height: 1fr;
        background: $surface;
        border: solid $primary 50%;
    }
    #sess-chat-status-area {
        height: auto;
        padding: 0 1;
        margin-bottom: 0;
        min-height: 2;
    }
    #sess-chat-status {
        height: auto;
        color: $text;
        padding: 0 1;
    }
    #sess-chat-loading-bar {
        height: 1;
        content-align: left middle;
        padding: 0 1;
    }
    #sess-chat-bar {
        dock: bottom;
        height: auto;
    }
    #sess-search-bar {
        height: auto;
    }
    #sess-search-bar Button#sess-new-btn {
        margin-right: 1;
        min-width: 8;
    }
    TabbedContent { height: 1fr; }
    TabPane { height: 1fr; }
    #tab-status { height: 1fr; }
    #tab-sessions { height: 1fr; }
    #tab-crons { height: 1fr; }
    #tab-env { height: 1fr; }
    #tab-logs { height: 1fr; }
    """

    BINDINGS = [
        Binding("q", "quit", "退出", show=True),
        Binding("r", "refresh", "刷新", show=True),
        Binding("1", "switch_tab('tab-status')", "状态"),
        Binding("2", "switch_tab('tab-sessions')", "会话"),
        Binding("3", "switch_tab('tab-crons')", "任务"),
        Binding("4", "switch_tab('tab-env')", "环境"),
        Binding("5", "switch_tab('tab-logs')", "日志"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        yield SystemStatusBar()
        with TabbedContent(initial="tab-sessions"):
            yield TabPane("状态", StatusContent(), id="tab-status")
            yield TabPane("会话", SessionsPane(), id="tab-sessions")
            yield TabPane("任务", CronsPane(), id="tab-crons")
            yield TabPane("环境变量", EnvPane(), id="tab-env")
            yield TabPane("日志", LogsPane(), id="tab-logs")
        yield Footer()

    @on(TabbedContent.TabActivated)
    def on_tab_activated(self, event: TabbedContent.TabActivated):
        pane = event.pane
        try:
            if pane.id == "tab-status":
                for sc in self.query(StatusContent):
                    if sc.is_attached_to_dom:
                        sc.reload_data()
            elif pane.id == "tab-sessions":
                for sp in self.query(SessionsPane):
                    if sp.is_attached_to_dom:
                        sp.load_sessions()
            elif pane.id == "tab-crons":
                for cp in self.query(CronsPane):
                    if cp.is_attached_to_dom:
                        cp.load_crons()
            elif pane.id == "tab-env":
                for ep in self.query(EnvPane):
                    if ep.is_attached_to_dom:
                        ep.load_env()
            elif pane.id == "tab-logs":
                pass
        except Exception:
            pass

    def action_refresh(self):
        """安全刷新：只刷新已挂载的组件，避免跨 Tab 闪退。"""
        try:
            for sc in self.query(StatusContent):
                if sc.is_attached_to_dom:
                    sc.reload_data()
            for sp in self.query(SessionsPane):
                if sp.is_attached_to_dom:
                    sp.load_sessions()
            for cp in self.query(CronsPane):
                if cp.is_attached_to_dom:
                    cp.load_crons()
            for wc in self.query(SystemStatusBar):
                if wc.is_attached_to_dom:
                    wc.reload_data()
        except Exception:
            pass

    def action_switch_tab(self, tab_id: str):
        try:
            tabs = self.query_one(TabbedContent)
            tabs.active = tab_id
        except Exception:
            pass


class SystemStatusBar(Static):
    """顶部系统状态条。"""

    DEFAULT_CSS = """
    SystemStatusBar {
        background: $primary-background;
        color: $primary;
        padding: 0 2;
        height: 3;
        dock: top;
    }
    """

    def __init__(self, **kwargs):
        super().__init__("", **kwargs)
        self.set_interval(60, self.refresh_status)

    def on_mount(self):
        self.refresh_status()

    def refresh_status(self):
        self.run_worker(self._fetch, exclusive=True)

    async def _fetch(self):
        provider, model = _get_provider_model()
        gw_raw = shell("curl -s http://127.0.0.1:9119/api/status 2>/dev/null")
        try:
            gw = json.loads(gw_raw)
        except Exception:
            gw = {}
        gw_state = gw.get("gateway_state", "unknown")
        active = gw.get("active_sessions", 0)
        icon = {"running": "[green]●ON[/green]", "stopped": "[red]●OFF[/red]"}.get(gw_state, "[yellow]●?[/yellow]")
        uptime = shell("uptime -p")
        self.update(f" [bold]Model:[/bold] {model}  [bold]Gateway:[/bold] {icon}  [bold]Sessions:[/bold] {active}  {uptime}")


if __name__ == "__main__":
    app = HermesDashboard()
    app.run()
