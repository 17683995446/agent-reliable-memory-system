"""
终端UI

第319阶段：颜色输出、进度条、表格渲染
"""

import threading
import time
import sys
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum


class Color(Enum):
    """终端颜色"""
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    UNDERLINE = "\033[4m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"
    BG_RED = "\033[41m"
    BG_GREEN = "\033[42m"
    BG_YELLOW = "\033[43m"
    BG_BLUE = "\033[44m"


@dataclass
class Column:
    """表格列定义"""
    header: str
    width: int = 20
    align: str = "left"  # left, right, center
    color: Optional[Color] = None


class TerminalUI:
    """
    终端UI工具

    职责：
    1. 颜色文本输出
    2. 进度条渲染
    3. 表格渲染
    4. 状态指示器
    """

    _instance: Optional['TerminalUI'] = None
    _lock = threading.RLock()

    def __new__(cls) -> 'TerminalUI':
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, '_initialized'):
            return
        self._initialized = True
        self._color_enabled = True
        self._progress_current = 0
        self._progress_total = 0
        self._progress_prefix = ""
        self._lock = threading.RLock()

    @property
    def color_enabled(self) -> bool:
        return self._color_enabled

    @color_enabled.setter
    def color_enabled(self, value: bool) -> None:
        self._color_enabled = value

    def colorize(self, text: str, *colors: Color) -> str:
        """给文本添加颜色"""
        if not self._color_enabled:
            return text
        codes = "".join(c.value for c in colors)
        return f"{codes}{text}{Color.RESET.value}"

    def bold(self, text: str) -> str:
        return self.colorize(text, Color.BOLD)

    def red(self, text: str) -> str:
        return self.colorize(text, Color.RED)

    def green(self, text: str) -> str:
        return self.colorize(text, Color.GREEN)

    def yellow(self, text: str) -> str:
        return self.colorize(text, Color.YELLOW)

    def blue(self, text: str) -> str:
        return self.colorize(text, Color.BLUE)

    def cyan(self, text: str) -> str:
        return self.colorize(text, Color.CYAN)

    def dim(self, text: str) -> str:
        return self.colorize(text, Color.DIM)

    def success(self, text: str) -> str:
        return self.colorize(f"  {text}", Color.GREEN)

    def error(self, text: str) -> str:
        return self.colorize(f"  {text}", Color.RED)

    def warning(self, text: str) -> str:
        return self.colorize(f"  {text}", Color.YELLOW)

    def info(self, text: str) -> str:
        return self.colorize(f"  {text}", Color.BLUE)

    def render_table(
        self,
        columns: List[Column],
        rows: List[List[str]],
        title: Optional[str] = None
    ) -> str:
        """渲染表格"""
        lines = []

        if title:
            lines.append(self.bold(title))
            lines.append("")

        # 表头
        header_parts = []
        for col in columns:
            text = col.header[:col.width].ljust(col.width)
            if col.color:
                text = self.colorize(text, col.color, Color.BOLD)
            else:
                text = self.bold(text)
            header_parts.append(text)
        lines.append(" | ".join(header_parts))
        lines.append("-+-".join("-" * c.width for c in columns))

        # 数据行
        for row in rows:
            parts = []
            for i, cell in enumerate(row):
                col = columns[i] if i < len(columns) else columns[-1]
                text = str(cell)[:col.width]
                if col.align == "right":
                    text = text.rjust(col.width)
                elif col.align == "center":
                    text = text.center(col.width)
                else:
                    text = text.ljust(col.width)
                parts.append(text)
            lines.append(" | ".join(parts))

        return "\n".join(lines)

    def render_progress(
        self,
        current: int,
        total: int,
        prefix: str = "",
        width: int = 40
    ) -> str:
        """渲染进度条"""
        if total == 0:
            percent = 100
        else:
            percent = int(current / total * 100)

        filled = int(width * percent / 100)
        bar = self.colorize("█" * filled, Color.GREEN) + "░" * (width - filled)
        return f"{prefix} [{bar}] {percent}% ({current}/{total})"

    def render_status(self, status: str, message: str = "") -> str:
        """渲染状态指示器"""
        indicators = {
            "running": self.colorize("●", Color.YELLOW),
            "success": self.colorize("●", Color.GREEN),
            "error": self.colorize("●", Color.RED),
            "warning": self.colorize("●", Color.YELLOW),
            "pending": self.colorize("○", Color.DIM),
        }
        indicator = indicators.get(status, "○")
        return f"  {indicator} {message}"

    def render_key_value(self, data: Dict[str, Any], indent: int = 2) -> str:
        """渲染键值对"""
        lines = []
        prefix = " " * indent
        for key, value in data.items():
            if isinstance(value, dict):
                lines.append(f"{prefix}{self.cyan(key)}:")
                lines.append(self.render_key_value(value, indent + 2))
            else:
                lines.append(f"{prefix}{self.cyan(key)}: {value}")
        return "\n".join(lines)

    def clear_line(self) -> str:
        """清除当前行"""
        return "\r\033[K"

    def get_stats(self) -> Dict[str, Any]:
        return {
            'color_enabled': self._color_enabled
        }


def get_terminal_ui() -> TerminalUI:
    """获取全局终端UI"""
    return TerminalUI()
