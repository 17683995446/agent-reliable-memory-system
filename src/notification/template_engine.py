"""
模板引擎模块 (阶段357)

提供通知模板的注册、管理和渲染功能。
支持变量替换、条件渲染、循环渲染和管道过滤器。
线程安全设计，使用 threading.RLock 保证并发安全。
确定性规则设计，无模型依赖，无循环依赖。
"""

import re
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional


# ============================================================================
# 数据类定义
# ============================================================================


@dataclass
class Template:
    """模板数据类"""
    name: str
    content: str
    variables: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)


@dataclass
class RenderContext:
    """渲染上下文数据类"""
    variables: Dict[str, Any] = field(default_factory=dict)
    functions: Dict[str, Callable] = field(default_factory=dict)


# ============================================================================
# 内置函数
# ============================================================================


def _builtin_now() -> str:
    """返回当前时间的ISO格式字符串"""
    return datetime.now().isoformat()


def _builtin_format_date(timestamp: float, fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    """格式化时间戳为指定格式的字符串"""
    try:
        dt = datetime.fromtimestamp(float(timestamp))
        return dt.strftime(fmt)
    except (TypeError, ValueError, OSError):
        return str(timestamp)


def _builtin_len(obj: Any) -> int:
    """返回对象的长度"""
    try:
        return len(obj)
    except TypeError:
        return 0


# ============================================================================
# 管道过滤器
# ============================================================================


def _filter_upper(value: Any) -> str:
    """将值转换为大写"""
    return str(value).upper()


def _filter_lower(value: Any) -> str:
    """将值转换为小写"""
    return str(value).lower()


def _filter_trim(value: Any) -> str:
    """去除值两端的空白字符"""
    return str(value).strip()


def _filter_default(value: Any, default_value: str = "") -> str:
    """如果值为空，则使用默认值"""
    if value is None or str(value).strip() == "":
        return default_value
    return str(value)


def _filter_length(value: Any) -> int:
    """返回值的长度"""
    try:
        return len(value)
    except TypeError:
        return 0


# 管道过滤器注册表
_PIPE_FILTERS: Dict[str, Callable] = {
    "upper": _filter_upper,
    "lower": _filter_lower,
    "trim": _filter_trim,
    "default": _filter_default,
    "length": _filter_length,
}


# ============================================================================
# 模板引擎
# ============================================================================


class TemplateEngine:
    """
    模板引擎

    管理通知模板的注册、存储和渲染。支持以下模板语法：
    - {{ variable }}: 变量替换
    - {{ variable | filter }}: 管道过滤器
    - {{ variable | filter:arg }}: 带参数的过滤器
    - {% if condition %}...{% endif %}: 条件渲染
    - {% for item in list %}...{% endfor %}: 循环渲染
    - {{ now() }}: 内置函数调用
    """

    # 正则表达式模式
    _VAR_PATTERN = re.compile(r"\{\{\s*(.+?)\s*\}\}")
    _IF_PATTERN = re.compile(r"\{%\s*if\s+(.+?)\s*%\}")
    _ENDIF_PATTERN = re.compile(r"\{%\s*endif\s*%\}")
    _FOR_PATTERN = re.compile(r"\{%\s*for\s+(\w+)\s+in\s+(\w+)\s*%\}")
    _ENDFOR_PATTERN = re.compile(r"\{%\s*endfor\s*%\}")
    _ELSE_PATTERN = re.compile(r"\{%\s*else\s*%\}")
    _VAR_EXTRACT_PATTERN = re.compile(r"\{\{\s*(\w+)(?:\s*\|.*)?\s*\}\}")

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._templates: Dict[str, Template] = {}

    @staticmethod
    def _extract_variables(content: str) -> List[str]:
        """从模板内容中提取所有变量名"""
        variables: List[str] = []
        seen: set = set()
        for match in TemplateEngine._VAR_EXTRACT_PATTERN.finditer(content):
            var_name = match.group(1)
            if var_name not in seen:
                variables.append(var_name)
                seen.add(var_name)
        # 也提取 for 循环中的集合变量
        for match in TemplateEngine._FOR_PATTERN.finditer(content):
            collection_name = match.group(2)
            if collection_name not in seen:
                variables.append(collection_name)
                seen.add(collection_name)
        return variables

    def register_template(self, name: str, content: str) -> Template:
        """
        注册模板

        Args:
            name: 模板名称
            content: 模板内容

        Returns:
            注册的 Template 对象
        """
        variables = self._extract_variables(content)
        template = Template(
            name=name,
            content=content,
            variables=variables,
            created_at=time.time(),
        )
        with self._lock:
            self._templates[name] = template
        return template

    def get_template(self, name: str) -> Optional[Template]:
        """
        获取模板

        Args:
            name: 模板名称

        Returns:
            Template 对象或 None
        """
        with self._lock:
            return self._templates.get(name)

    def remove_template(self, name: str) -> bool:
        """
        移除模板

        Args:
            name: 模板名称

        Returns:
            是否成功移除
        """
        with self._lock:
            if name in self._templates:
                del self._templates[name]
                return True
            return False

    def _apply_filter(self, value: Any, filter_expr: str) -> Any:
        """
        应用管道过滤器

        Args:
            value: 输入值
            filter_expr: 过滤器表达式（如 "upper" 或 "default:N/A"）

        Returns:
            过滤后的值
        """
        filter_expr = filter_expr.strip()
        if ":" in filter_expr:
            filter_name, arg = filter_expr.split(":", 1)
            filter_name = filter_name.strip()
            arg = arg.strip()
        else:
            filter_name = filter_expr
            arg = None

        filter_func = _PIPE_FILTERS.get(filter_name)
        if filter_func is None:
            return value

        if arg is not None:
            return filter_func(value, arg)
        return filter_func(value)

    def _resolve_expression(self, expr: str, context: RenderContext) -> Any:
        """
        解析表达式，支持变量、过滤器和函数调用

        Args:
            expr: 表达式字符串
            context: 渲染上下文

        Returns:
            解析后的值
        """
        expr = expr.strip()

        # 处理管道过滤器
        if "|" in expr:
            parts = expr.split("|", 1)
            var_part = parts[0].strip()
            filter_part = parts[1].strip()
            value = self._resolve_expression(var_part, context)
            return self._apply_filter(value, filter_part)

        # 处理函数调用
        if "(" in expr and expr.endswith(")"):
            func_name = expr[: expr.index("(")].strip()
            # 先从上下文函数中查找，再从内置函数中查找
            func = context.functions.get(func_name)
            if func is None:
                builtin_funcs = {
                    "now": _builtin_now,
                    "format_date": _builtin_format_date,
                    "len": _builtin_len,
                }
                func = builtin_funcs.get(func_name)
            if func is not None:
                args_str = expr[expr.index("(") + 1: -1].strip()
                if args_str:
                    args = [
                        self._resolve_expression(a.strip(), context)
                        for a in args_str.split(",")
                    ]
                    return func(*args)
                return func()
            return f"{{{{ {expr} }}}}"

        # 处理变量
        if expr in context.variables:
            return context.variables[expr]
        return None

    def _render_variables(self, text: str, context: RenderContext) -> str:
        """替换模板中的所有变量表达式"""
        def replacer(match: re.Match) -> str:
            expr = match.group(1)
            value = self._resolve_expression(expr, context)
            if value is None:
                return ""
            return str(value)

        return self._VAR_PATTERN.sub(replacer, text)

    def _process_if_blocks(self, text: str, context: RenderContext) -> str:
        """处理条件渲染块"""
        result = []
        pos = 0
        length = len(text)

        while pos < length:
            # 查找 {% if ... %}
            if_match = self._IF_PATTERN.search(text, pos)
            if if_match is None:
                result.append(text[pos:])
                break

            # 添加 if 之前的文本
            result.append(text[pos: if_match.start()])
            condition_expr = if_match.group(1).strip()

            # 查找匹配的 {% endif %}
            endif_match = self._ENDIF_PATTERN.search(text, if_match.end())
            if endif_match is None:
                result.append(text[if_match.start():])
                break

            block_content = text[if_match.end(): endif_match.start()]

            # 检查是否有 {% else %}
            else_match = self._ELSE_PATTERN.search(block_content)
            if else_match is not None:
                true_content = block_content[: else_match.start()]
                false_content = block_content[else_match.end():]
            else:
                true_content = block_content
                false_content = ""

            # 评估条件
            condition_value = self._resolve_expression(condition_expr, context)
            if condition_value and condition_value != f"{{{{ {condition_expr} }}}}":
                result.append(self._render_variables(true_content, context))
            else:
                result.append(self._render_variables(false_content, context))

            pos = endif_match.end()

        return "".join(result)

    def _process_for_blocks(self, text: str, context: RenderContext) -> str:
        """处理循环渲染块"""
        result = []
        pos = 0
        length = len(text)

        while pos < length:
            # 查找 {% for item in list %}
            for_match = self._FOR_PATTERN.search(text, pos)
            if for_match is None:
                result.append(text[pos:])
                break

            # 添加 for 之前的文本
            result.append(text[pos: for_match.start()])
            item_name = for_match.group(1)
            collection_name = for_match.group(2)

            # 查找匹配的 {% endfor %}
            endfor_match = self._ENDFOR_PATTERN.search(text, for_match.end())
            if endfor_match is None:
                result.append(text[for_match.start():])
                break

            block_content = text[for_match.end(): endfor_match.start()]

            # 获取集合数据
            collection = context.variables.get(collection_name, [])
            if not isinstance(collection, (list, tuple)):
                collection = []

            # 渲染循环体
            for item in collection:
                loop_context = RenderContext(
                    variables={**context.variables, item_name: item},
                    functions=context.functions,
                )
                rendered = self._render_variables(block_content, loop_context)
                result.append(rendered)

            pos = endfor_match.end()

        return "".join(result)

    def render(self, template_name: str, context: RenderContext) -> str:
        """
        使用已注册的模板进行渲染

        Args:
            template_name: 模板名称
            context: 渲染上下文

        Returns:
            渲染后的字符串

        Raises:
            ValueError: 模板不存在
        """
        with self._lock:
            template = self._templates.get(template_name)
            if template is None:
                raise ValueError(f"Template '{template_name}' not found")
            content = template.content

        return self._render_content(content, context)

    def render_string(self, template_str: str, context: RenderContext) -> str:
        """
        直接使用模板字符串进行渲染

        Args:
            template_str: 模板字符串
            context: 渲染上下文

        Returns:
            渲染后的字符串
        """
        return self._render_content(template_str, context)

    def _render_content(self, content: str, context: RenderContext) -> str:
        """内部渲染方法，处理所有模板语法"""
        # 先处理 for 循环块
        result = self._process_for_blocks(content, context)
        # 再处理 if 条件块
        result = self._process_if_blocks(result, context)
        # 最后替换变量
        result = self._render_variables(result, context)
        return result

    def list_templates(self) -> List[str]:
        """
        列出所有已注册的模板名称

        Returns:
            模板名称列表
        """
        with self._lock:
            return list(self._templates.keys())

    def get_stats(self) -> Dict[str, Any]:
        """
        获取模板引擎统计信息

        Returns:
            统计信息字典
        """
        with self._lock:
            templates = list(self._templates.values())
            total = len(templates)
            total_variables = sum(len(t.variables) for t in templates)
            return {
                "total_templates": total,
                "total_variables": total_variables,
                "template_names": [t.name for t in templates],
                "available_filters": list(_PIPE_FILTERS.keys()),
                "builtin_functions": ["now", "format_date", "len"],
            }


# ============================================================================
# 全局单例
# ============================================================================

_template_engine_instance: Optional[TemplateEngine] = None
_template_engine_lock = threading.Lock()


def get_template_engine() -> TemplateEngine:
    """获取模板引擎全局单例"""
    global _template_engine_instance
    with _template_engine_lock:
        if _template_engine_instance is None:
            _template_engine_instance = TemplateEngine()
        return _template_engine_instance
