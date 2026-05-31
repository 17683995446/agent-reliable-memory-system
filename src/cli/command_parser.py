"""
命令解析器

第316阶段：参数解析、选项处理、子命令
遵循"图难于其易，为大于其细"原则，实现细粒度的命令解析
"""

import threading
import re
import shlex
from typing import Dict, List, Optional, Any, Callable, Union, Tuple
from dataclasses import dataclass, field
from enum import Enum


class ArgType(Enum):
    """参数类型"""
    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    LIST = "list"
    DICT = "dict"


@dataclass
class Option:
    """选项定义"""
    name: str                          # 短名 -h
    long_name: Optional[str] = None     # 长名 --help
    description: str = ""
    arg_type: ArgType = ArgType.STRING
    required: bool = False
    default: Any = None
    choices: Optional[List[Any]] = None
    multiple: bool = False              # 可多次出现
    hidden: bool = False                # 帮助中隐藏


@dataclass
class PositionalArg:
    """位置参数定义"""
    name: str
    description: str = ""
    arg_type: ArgType = ArgType.STRING
    required: bool = True
    default: Any = None
    choices: Optional[List[Any]] = None
    varargs: bool = False               # 可变参数 *


@dataclass
class SubCommand:
    """子命令定义"""
    name: str
    description: str = ""
    options: List[Option] = field(default_factory=list)
    positional_args: List[PositionalArg] = field(default_factory=list)
    sub_commands: Dict[str, 'SubCommand'] = field(default_factory=dict)
    handler: Optional[Callable] = None
    aliases: List[str] = field(default_factory=list)


@dataclass
class ParseResult:
    """解析结果"""
    command: str = ""
    sub_command: Optional[str] = None
    options: Dict[str, Any] = field(default_factory=dict)
    positional: List[Any] = field(default_factory=list)
    raw_args: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    remaining: List[str] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return len(self.errors) == 0


class CommandParser:
    """
    命令解析器

    职责：
    1. 解析命令行参数
    2. 处理短选项和长选项
    3. 支持子命令
    4. 类型转换和验证

    设计原则：
    - 细粒度参数控制
    - 支持嵌套子命令
    - 详细的错误信息
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._options: Dict[str, Option] = {}
        self._long_options: Dict[str, Option] = {}
        self._positional_args: List[PositionalArg] = []
        self._sub_commands: Dict[str, SubCommand] = {}
        self._description: str = ""
        self._name: str = "cli"

    def set_name(self, name: str) -> None:
        self._name = name

    def set_description(self, desc: str) -> None:
        self._description = desc

    def add_option(self, option: Option) -> None:
        """添加选项"""
        with self._lock:
            self._options[option.name] = option
            if option.long_name:
                self._long_options[option.long_name] = option

    def add_positional(self, arg: PositionalArg) -> None:
        """添加位置参数"""
        with self._lock:
            self._positional_args.append(arg)

    def add_sub_command(self, sub: SubCommand) -> None:
        """添加子命令"""
        with self._lock:
            self._sub_commands[sub.name] = sub
            for alias in sub.aliases:
                self._sub_commands[alias] = sub

    def _convert_value(self, value: str, arg_type: ArgType) -> Any:
        """类型转换"""
        try:
            if arg_type == ArgType.INTEGER:
                return int(value)
            elif arg_type == ArgType.FLOAT:
                return float(value)
            elif arg_type == ArgType.BOOLEAN:
                return value.lower() in ('true', '1', 'yes', 'on')
            elif arg_type == ArgType.LIST:
                return value.split(',')
            elif arg_type == ArgType.DICT:
                result = {}
                for pair in value.split(','):
                    if '=' in pair:
                        k, v = pair.split('=', 1)
                        result[k.strip()] = v.strip()
                return result
            return value
        except ValueError:
            return value

    def _validate_choice(self, value: Any, choices: Optional[List[Any]]) -> Optional[str]:
        """验证选项值"""
        if choices and value not in choices:
            return f"Value '{value}' must be one of {choices}"
        return None

    def parse(self, args: Optional[List[str]] = None) -> ParseResult:
        """
        解析命令行参数

        Args:
            args: 参数列表（不含程序名）

        Returns:
            解析结果
        """
        result = ParseResult(raw_args=args or [])

        if not args:
            return result

        idx = 0
        positional_idx = 0
        positional_values = []

        while idx < len(args):
            token = args[idx]

            # 子命令检测
            if token in self._sub_commands and not result.options:
                result.sub_command = token
                idx += 1
                # 将剩余参数交给子命令
                result.remaining = args[idx:]
                return result

            # 长选项 --option=value 或 --option value
            if token.startswith('--'):
                opt_name = token[2:]
                opt_value = None

                if '=' in opt_name:
                    opt_name, opt_value = opt_name.split('=', 1)

                option = self._long_options.get(opt_name)
                if not option:
                    result.errors.append(f"Unknown option: --{opt_name}")
                    idx += 1
                    continue

                # 布尔标志
                if option.arg_type == ArgType.BOOLEAN and opt_value is None:
                    opt_value = 'true'
                elif opt_value is None and idx + 1 < len(args) and not args[idx + 1].startswith('-'):
                    idx += 1
                    opt_value = args[idx]

                if opt_value is not None:
                    converted = self._convert_value(opt_value, option.arg_type)
                    err = self._validate_choice(converted, option.choices)
                    if err:
                        result.errors.append(err)
                    else:
                        if option.multiple:
                            if option.name not in result.options:
                                result.options[option.name] = []
                            result.options[option.name].append(converted)
                        else:
                            result.options[option.name] = converted
                else:
                    result.options[option.name] = option.default or True

            # 短选项 -a 或 -abc 或 -a value
            elif token.startswith('-') and len(token) > 1:
                chars = token[1:]
                for i, char in enumerate(chars):
                    option = self._options.get(char)
                    if not option:
                        result.errors.append(f"Unknown option: -{char}")
                        continue

                    if option.arg_type == ArgType.BOOLEAN:
                        result.options[option.name] = True
                    elif i == len(chars) - 1 and idx + 1 < len(args) and not args[idx + 1].startswith('-'):
                        idx += 1
                        converted = self._convert_value(args[idx], option.arg_type)
                        err = self._validate_choice(converted, option.choices)
                        if err:
                            result.errors.append(err)
                        else:
                            result.options[option.name] = converted
                    else:
                        result.options[option.name] = option.default or True

            # 位置参数
            else:
                if positional_idx < len(self._positional_args):
                    arg_def = self._positional_args[positional_idx]
                    converted = self._convert_value(token, arg_def.arg_type)
                    err = self._validate_choice(converted, arg_def.choices)
                    if err:
                        result.errors.append(err)
                    positional_values.append(converted)
                    positional_idx += 1
                else:
                    result.remaining.append(token)

            idx += 1

        result.positional = positional_values

        # 检查必需选项
        for opt in self._options.values():
            if opt.required and opt.name not in result.options:
                result.errors.append(f"Missing required option: -{opt.name}")

        # 检查必需位置参数
        for i, arg_def in enumerate(self._positional_args):
            if arg_def.required and i >= len(positional_values):
                result.errors.append(f"Missing required argument: {arg_def.name}")

        return result

    def generate_help(self) -> str:
        """生成帮助文本"""
        lines = [f"Usage: {self._name} [options]", ""]

        if self._description:
            lines.append(self._description)
            lines.append("")

        # 位置参数
        if self._positional_args:
            lines.append("Arguments:")
            for arg in self._positional_args:
                req = " (required)" if arg.required else ""
                default = f" (default: {arg.default})" if arg.default is not None else ""
                lines.append(f"  {arg.name:<20} {arg.description}{req}{default}")
            lines.append("")

        # 选项
        if self._options:
            lines.append("Options:")
            for opt in self._options.values():
                if opt.hidden:
                    continue
                short = f"-{opt.name}"
                long = f" --{opt.long_name}" if opt.long_name else ""
                desc = opt.description or ""
                default = f" (default: {opt.default})" if opt.default is not None else ""
                lines.append(f"  {short}{long:<20} {desc}{default}")
            lines.append("")

        # 子命令
        if self._sub_commands:
            lines.append("Commands:")
            for name, sub in self._sub_commands.items():
                if name != sub.name:
                    continue
                aliases = f" ({','.join(sub.aliases)})" if sub.aliases else ""
                lines.append(f"  {name:<20} {sub.description}{aliases}")
            lines.append("")

        return "\n".join(lines)


# 全局实例
_command_parser: Optional[CommandParser] = None
_parser_lock = threading.Lock()


def get_command_parser() -> CommandParser:
    """获取全局命令解析器"""
    global _command_parser
    if _command_parser is None:
        with _parser_lock:
            if _command_parser is None:
                _command_parser = CommandParser()
    return _command_parser
