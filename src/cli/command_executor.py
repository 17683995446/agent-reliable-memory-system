"""
命令执行器

第317阶段：命令分发、管道支持、错误处理
"""

import threading
import time
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum


class ExitCode(Enum):
    """退出码"""
    SUCCESS = 0
    ERROR = 1
    INVALID_ARGS = 2
    COMMAND_NOT_FOUND = 127
    PERMISSION_DENIED = 126
    TIMEOUT = 124


@dataclass
class CommandResult:
    """命令执行结果"""
    exit_code: ExitCode = ExitCode.SUCCESS
    stdout: str = ""
    stderr: str = ""
    duration: float = 0.0
    data: Any = None

    @property
    def success(self) -> bool:
        return self.exit_code == ExitCode.SUCCESS


@dataclass
class PipeSegment:
    """管道段"""
    command: str
    args: List[str] = field(default_factory=list)


class CommandExecutor:
    """
    命令执行器

    职责：
    1. 命令分发和执行
    2. 管道支持
    3. 超时控制
    4. 错误处理
    """

    _instance: Optional['CommandExecutor'] = None
    _lock = threading.RLock()

    def __new__(cls) -> 'CommandExecutor':
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, '_initialized'):
            return
        self._initialized = True
        self._handlers: Dict[str, Callable] = {}
        self._before_hooks: List[Callable] = []
        self._after_hooks: List[Callable] = []
        self._default_timeout: float = 30.0
        self._lock = threading.RLock()

    def register_handler(self, name: str, handler: Callable) -> None:
        """注册命令处理器"""
        with self._lock:
            self._handlers[name] = handler

    def unregister_handler(self, name: str) -> bool:
        """注销命令处理器"""
        with self._lock:
            return self._handlers.pop(name, None) is not None

    def add_before_hook(self, hook: Callable) -> None:
        self._before_hooks.append(hook)

    def add_after_hook(self, hook: Callable) -> None:
        self._after_hooks.append(hook)

    def execute(
        self,
        command: str,
        args: Optional[List[str]] = None,
        timeout: Optional[float] = None
    ) -> CommandResult:
        """
        执行命令

        Args:
            command: 命令名
            args: 参数列表
            timeout: 超时秒数

        Returns:
            执行结果
        """
        start = time.time()
        timeout = timeout or self._default_timeout

        # 前置钩子
        for hook in self._before_hooks:
            try:
                hook_result = hook(command, args)
                if hook_result is not None:
                    return hook_result
            except Exception:
                pass

        with self._lock:
            handler = self._handlers.get(command)

        if not handler:
            return CommandResult(
                exit_code=ExitCode.COMMAND_NOT_FOUND,
                stderr=f"Command not found: {command}",
                duration=time.time() - start
            )

        try:
            result = handler(args or [])
            duration = time.time() - start

            if isinstance(result, CommandResult):
                result.duration = duration
                return result
            elif isinstance(result, str):
                return CommandResult(
                    exit_code=ExitCode.SUCCESS,
                    stdout=result,
                    duration=duration
                )
            elif isinstance(result, dict):
                return CommandResult(
                    exit_code=ExitCode.SUCCESS,
                    data=result,
                    duration=duration
                )
            else:
                return CommandResult(
                    exit_code=ExitCode.SUCCESS,
                    stdout=str(result),
                    duration=duration
                )

        except TimeoutError:
            return CommandResult(
                exit_code=ExitCode.TIMEOUT,
                stderr=f"Command timed out after {timeout}s",
                duration=time.time() - start
            )
        except PermissionError:
            return CommandResult(
                exit_code=ExitCode.PERMISSION_DENIED,
                stderr="Permission denied",
                duration=time.time() - start
            )
        except Exception as e:
            return CommandResult(
                exit_code=ExitCode.ERROR,
                stderr=str(e),
                duration=time.time() - start
            )

    def execute_pipeline(self, segments: List[PipeSegment]) -> CommandResult:
        """
        执行管道命令

        Args:
            segments: 管道段列表

        Returns:
            最终执行结果
        """
        start = time.time()
        prev_stdout = ""

        for segment in segments:
            result = self.execute(segment.command, segment.args)
            if not result.success:
                return result
            prev_stdout = result.stdout

        return CommandResult(
            exit_code=ExitCode.SUCCESS,
            stdout=prev_stdout,
            duration=time.time() - start
        )

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self._lock:
            return {
                'registered_commands': len(self._handlers),
                'before_hooks': len(self._before_hooks),
                'after_hooks': len(self._after_hooks),
                'default_timeout': self._default_timeout
            }


def get_command_executor() -> CommandExecutor:
    """获取全局命令执行器"""
    return CommandExecutor()
