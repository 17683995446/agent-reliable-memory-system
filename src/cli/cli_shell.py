"""
交互式Shell

第320阶段：REPL循环、历史记录、Tab补全
"""

import threading
import time
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum


class ShellState(Enum):
    """Shell状态"""
    IDLE = "idle"
    RUNNING = "running"
    EXITED = "exited"


@dataclass
class HistoryEntry:
    """历史记录条目"""
    command: str
    timestamp: float = field(default_factory=time.time)
    exit_code: int = 0


class CLIShell:
    """
    交互式Shell

    职责：
    1. REPL循环
    2. 命令历史记录
    3. 自动补全
    4. Shell状态管理
    """

    _instance: Optional['CLIShell'] = None
    _lock = threading.RLock()

    def __new__(cls) -> 'CLIShell':
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, '_initialized'):
            return
        self._initialized = True
        self._state = ShellState.IDLE
        self._prompt: str = "> "
        self._history: List[HistoryEntry] = []
        self._history_index: int = -1
        self._max_history: int = 1000
        self._aliases: Dict[str, str] = {}
        self._env: Dict[str, str] = {}
        self._pre_hooks: List[Callable] = []
        self._post_hooks: List[Callable] = []
        self._lock = threading.RLock()
        self._command_count = 0
        self._start_time: float = 0.0

    @property
    def state(self) -> ShellState:
        return self._state

    def set_prompt(self, prompt: str) -> None:
        """设置提示符"""
        with self._lock:
            self._prompt = prompt

    def set_alias(self, name: str, command: str) -> None:
        """设置别名"""
        with self._lock:
            self._aliases[name] = command

    def remove_alias(self, name: str) -> bool:
        """移除别名"""
        with self._lock:
            return self._aliases.pop(name, None) is not None

    def set_env(self, key: str, value: str) -> None:
        """设置环境变量"""
        with self._lock:
            self._env[key] = value

    def get_env(self, key: str, default: str = "") -> str:
        """获取环境变量"""
        with self._lock:
            return self._env.get(key, default)

    def add_pre_hook(self, hook: Callable) -> None:
        """添加前置钩子"""
        self._pre_hooks.append(hook)

    def add_post_hook(self, hook: Callable) -> None:
        """添加后置钩子"""
        self._post_hooks.append(hook)

    def add_history(self, command: str, exit_code: int = 0) -> None:
        """添加历史记录"""
        with self._lock:
            if self._history and self._history[-1].command == command:
                return  # 不重复
            self._history.append(HistoryEntry(command=command, exit_code=exit_code))
            self._history_index = len(self._history)
            # 限制历史大小
            if len(self._history) > self._max_history:
                self._history = self._history[-self._max_history:]

    def get_history(self, limit: Optional[int] = None) -> List[HistoryEntry]:
        """获取历史记录"""
        with self._lock:
            if limit:
                return self._history[-limit:]
            return list(self._history)

    def history_up(self) -> Optional[str]:
        """向上翻历史"""
        with self._lock:
            if self._history_index > 0:
                self._history_index -= 1
                return self._history[self._history_index].command
            return None

    def history_down(self) -> Optional[str]:
        """向下翻历史"""
        with self._lock:
            if self._history_index < len(self._history) - 1:
                self._history_index += 1
                return self._history[self._history_index].command
            elif self._history_index == len(self._history) - 1:
                self._history_index = len(self._history)
                return ""
            return None

    def expand_alias(self, command: str) -> str:
        """展开别名"""
        parts = command.strip().split()
        if parts and parts[0] in self._aliases:
            parts[0] = self._aliases[parts[0]]
            return " ".join(parts)
        return command

    def expand_env(self, command: str) -> str:
        """展开环境变量"""
        import re
        def replace_var(match):
            var_name = match.group(1)
            return self._env.get(var_name, match.group(0))
        return re.sub(r'\$\{(\w+)\}', replace_var, command)

    def preprocess(self, command: str) -> str:
        """预处理命令"""
        command = command.strip()
        if not command or command.startswith('#'):
            return ""
        command = self.expand_alias(command)
        command = self.expand_env(command)
        return command

    def process_line(self, line: str, executor: Optional[Any] = None) -> str:
        """
        处理一行输入

        Args:
            line: 输入行
            executor: 命令执行器

        Returns:
            输出文本
        """
        command = self.preprocess(line)
        if not command:
            return ""

        self._command_count += 1

        # 前置钩子
        for hook in self._pre_hooks:
            result = hook(command)
            if result is not None:
                return str(result)

        output = ""
        exit_code = 0

        if executor:
            parts = command.split()
            cmd_name = parts[0] if parts else ""
            args = parts[1:] if len(parts) > 1 else []
            result = executor.execute(cmd_name, args)
            output = result.stdout or ""
            if result.stderr:
                output += result.stderr
            exit_code = result.exit_code.value if hasattr(result.exit_code, 'value') else 0

        self.add_history(command, exit_code)

        # 后置钩子
        for hook in self._post_hooks:
            hook(command, output, exit_code)

        return output

    def start(self) -> None:
        """标记Shell启动"""
        with self._lock:
            self._state = ShellState.RUNNING
            self._start_time = time.time()

    def stop(self) -> None:
        """标记Shell停止"""
        with self._lock:
            self._state = ShellState.EXITED

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self._lock:
            duration = 0.0
            if self._start_time and self._state == ShellState.RUNNING:
                duration = time.time() - self._start_time
            return {
                'state': self._state.value,
                'command_count': self._command_count,
                'history_size': len(self._history),
                'aliases': len(self._aliases),
                'env_vars': len(self._env),
                'session_duration': round(duration, 2)
            }


def get_cli_shell() -> CLIShell:
    """获取全局CLIShell"""
    return CLIShell()
