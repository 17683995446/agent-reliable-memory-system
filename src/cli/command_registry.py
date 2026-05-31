"""
命令注册表

第318阶段：命令注册、帮助生成、自动补全
"""

import threading
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field


@dataclass
class CommandEntry:
    """命令条目"""
    name: str
    description: str = ""
    handler: Optional[Callable] = None
    aliases: List[str] = field(default_factory=list)
    category: str = "general"
    hidden: bool = False
    usage: str = ""
    examples: List[str] = field(default_factory=list)


class CommandRegistry:
    """
    命令注册表

    职责：
    1. 命令注册和管理
    2. 帮助文本生成
    3. 自动补全候选
    4. 命令搜索
    """

    _instance: Optional['CommandRegistry'] = None
    _lock = threading.RLock()

    def __new__(cls) -> 'CommandRegistry':
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, '_initialized'):
            return
        self._initialized = True
        self._commands: Dict[str, CommandEntry] = {}
        self._categories: Dict[str, List[str]] = {}
        self._lock = threading.RLock()

    def register(self, entry: CommandEntry) -> None:
        """注册命令"""
        with self._lock:
            self._commands[entry.name] = entry
            for alias in entry.aliases:
                self._commands[alias] = entry
            if entry.category not in self._categories:
                self._categories[entry.category] = []
            if entry.name not in self._categories[entry.category]:
                self._categories[entry.category].append(entry.name)

    def unregister(self, name: str) -> bool:
        """注销命令"""
        with self._lock:
            entry = self._commands.pop(name, None)
            if entry:
                for alias in entry.aliases:
                    self._commands.pop(alias, None)
                return True
            return False

    def get(self, name: str) -> Optional[CommandEntry]:
        """获取命令"""
        with self._lock:
            return self._commands.get(name)

    def search(self, prefix: str) -> List[str]:
        """搜索命令（自动补全）"""
        with self._lock:
            return [
                name for name in self._commands
                if name.startswith(prefix) and not self._commands[name].hidden
            ]

    def get_all(self, include_hidden: bool = False) -> Dict[str, CommandEntry]:
        """获取所有命令"""
        with self._lock:
            if include_hidden:
                return dict(self._commands)
            return {k: v for k, v in self._commands.items() if not v.hidden}

    def get_by_category(self) -> Dict[str, List[CommandEntry]]:
        """按分类获取命令"""
        with self._lock:
            result = {}
            for cat, names in self._categories.items():
                result[cat] = [
                    self._commands[n] for n in names
                    if n in self._commands and not self._commands[n].hidden
                ]
            return result

    def generate_help(self, category: Optional[str] = None) -> str:
        """生成帮助文本"""
        lines = ["Available Commands:", ""]

        if category:
            entries = self.get_by_category().get(category, [])
            lines.append(f"Category: {category}")
            lines.append("")
        else:
            entries = [e for e in self._commands.values() if not e.hidden]

        for entry in entries:
            aliases = f" ({','.join(entry.aliases)})" if entry.aliases else ""
            lines.append(f"  {entry.name:<20} {entry.description}{aliases}")

        return "\n".join(lines)

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self._lock:
            return {
                'total_commands': len(self._commands),
                'categories': len(self._categories),
                'hidden_commands': sum(1 for c in self._commands.values() if c.hidden)
            }


def get_command_registry() -> CommandRegistry:
    """获取全局命令注册表"""
    return CommandRegistry()
