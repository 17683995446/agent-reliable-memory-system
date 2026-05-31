"""
CLI命令行工具模块

第23阶段（阶段316-320）CLI命令行工具
- 阶段316: 命令解析器 (CommandParser)
- 阶段317: 命令执行器 (CommandExecutor)
- 阶段318: 命令注册表 (CommandRegistry)
- 阶段319: 终端UI (TerminalUI)
- 阶段320: 交互式Shell (CLIShell)
"""

from .command_parser import CommandParser, Option, PositionalArg, SubCommand, ParseResult, ArgType, get_command_parser
from .command_executor import CommandExecutor, CommandResult, ExitCode, PipeSegment, get_command_executor
from .command_registry import CommandRegistry, CommandEntry, get_command_registry
from .terminal_ui import TerminalUI, Color, Column, get_terminal_ui
from .cli_shell import CLIShell, ShellState, HistoryEntry, get_cli_shell

__all__ = [
    'CommandParser', 'Option', 'PositionalArg', 'SubCommand', 'ParseResult', 'ArgType', 'get_command_parser',
    'CommandExecutor', 'CommandResult', 'ExitCode', 'PipeSegment', 'get_command_executor',
    'CommandRegistry', 'CommandEntry', 'get_command_registry',
    'TerminalUI', 'Color', 'Column', 'get_terminal_ui',
    'CLIShell', 'ShellState', 'HistoryEntry', 'get_cli_shell',
]
