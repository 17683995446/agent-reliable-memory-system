"""
SDK生成器 (SDKGenerator)
阶段278-280: 接口定义、代码生成、版本管理

基于第一性原则设计:
1. 确定性: 基于模板的确定性代码生成
2. 一致性: 版本化接口定义
3. 可扩展性: 支持多语言代码生成
"""

import threading
import time
import hashlib
import re
from typing import Dict, List, Optional, Any, Callable, Tuple, Set
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict


class ParamType(Enum):
    """参数类型"""
    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    ARRAY = "array"
    OBJECT = "object"
    ANY = "any"


class TargetLanguage(Enum):
    """目标语言"""
    PYTHON = "python"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    GO = "go"
    JAVA = "java"


class InterfaceStatus(Enum):
    """接口状态"""
    DRAFT = "draft"
    STABLE = "stable"
    DEPRECATED = "deprecated"
    REMOVED = "removed"


@dataclass
class ParamDefinition:
    """参数定义"""
    name: str
    param_type: ParamType
    required: bool = True
    default_value: Any = None
    description: str = ""


@dataclass
class InterfaceDefinition:
    """接口定义"""
    interface_id: str
    name: str
    method: str  # GET/POST/PUT/DELETE
    path: str
    description: str = ""
    params: List[ParamDefinition] = field(default_factory=list)
    return_type: ParamType = ParamType.OBJECT
    status: InterfaceStatus = InterfaceStatus.DRAFT
    version: str = "1.0.0"
    tags: List[str] = field(default_factory=list)
    deprecated_message: str = ""


@dataclass
class SDKVersion:
    """SDK版本"""
    version_id: str
    version_number: str
    language: TargetLanguage
    interfaces: List[str]  # interface_ids
    generated_code: str = ""
    checksum: str = ""
    created_at: float = field(default_factory=time.time)
    changelog: str = ""


@dataclass
class CodeTemplate:
    """代码模板"""
    language: TargetLanguage
    template_name: str
    template: str
    description: str = ""


class SDKGenerator:
    """
    SDK生成器

    核心功能:
    1. 接口定义: 标准化的API接口描述
    2. 代码生成: 基于模板的多语言SDK生成
    3. 版本管理: SDK版本控制和变更追踪
    """

    def __init__(self):
        self._lock = threading.RLock()

        # 接口定义
        self._interfaces: Dict[str, InterfaceDefinition] = {}
        self._interface_versions: Dict[str, List[str]] = defaultdict(list)  # interface_id -> version list

        # SDK版本
        self._sdk_versions: Dict[str, List[SDKVersion]] = defaultdict(list)  # language -> versions
        self._max_versions = 50

        # 代码模板
        self._templates: Dict[TargetLanguage, List[CodeTemplate]] = defaultdict(list)
        self._register_builtin_templates()

        # 自定义生成器
        self._custom_generators: Dict[TargetLanguage, Callable[[List[InterfaceDefinition]], str]] = {}

    # ==================== 阶段278: 接口定义 ====================

    def define_interface(self, name: str, method: str, path: str,
                         description: str = "",
                         params: Optional[List[ParamDefinition]] = None,
                         return_type: ParamType = ParamType.OBJECT,
                         version: str = "1.0.0",
                         tags: Optional[List[str]] = None) -> str:
        """
        定义接口

        Args:
            name: 接口名称
            method: HTTP方法
            path: 路径
            description: 描述
            params: 参数列表
            return_type: 返回类型
            version: 版本
            tags: 标签

        Returns:
            接口ID
        """
        with self._lock:
            interface_id = self._generate_interface_id(name, path)

            interface = InterfaceDefinition(
                interface_id=interface_id,
                name=name,
                method=method,
                path=path,
                description=description,
                params=params or [],
                return_type=return_type,
                version=version,
                tags=tags or []
            )

            self._interfaces[interface_id] = interface
            self._interface_versions[interface_id].append(version)
            return interface_id

    def _generate_interface_id(self, name: str, path: str) -> str:
        """生成接口ID"""
        data = f"{name}_{path}_{time.time()}"
        return hashlib.md5(data.encode()).hexdigest()[:16]

    def get_interface(self, interface_id: str) -> Optional[InterfaceDefinition]:
        """获取接口定义"""
        with self._lock:
            return self._interfaces.get(interface_id)

    def list_interfaces(self, status: Optional[InterfaceStatus] = None,
                       tags: Optional[List[str]] = None) -> List[InterfaceDefinition]:
        """列出接口"""
        with self._lock:
            interfaces = list(self._interfaces.values())
            if status:
                interfaces = [i for i in interfaces if i.status == status]
            if tags:
                interfaces = [i for i in interfaces if any(t in i.tags for t in tags)]
            return interfaces

    def update_interface(self, interface_id: str,
                        status: Optional[InterfaceStatus] = None,
                        description: Optional[str] = None,
                        params: Optional[List[ParamDefinition]] = None,
                        deprecated_message: str = "") -> bool:
        """更新接口"""
        with self._lock:
            if interface_id not in self._interfaces:
                return False
            interface = self._interfaces[interface_id]
            if status:
                interface.status = status
            if description is not None:
                interface.description = description
            if params is not None:
                interface.params = params
            if deprecated_message:
                interface.deprecated_message = deprecated_message
            return True

    def remove_interface(self, interface_id: str) -> bool:
        """移除接口"""
        with self._lock:
            if interface_id not in self._interfaces:
                return False
            self._interfaces[interface_id].status = InterfaceStatus.REMOVED
            return True

    def add_param(self, interface_id: str, param: ParamDefinition) -> bool:
        """添加参数"""
        with self._lock:
            if interface_id not in self._interfaces:
                return False
            self._interfaces[interface_id].params.append(param)
            return True

    def remove_param(self, interface_id: str, param_name: str) -> bool:
        """移除参数"""
        with self._lock:
            if interface_id not in self._interfaces:
                return False
            params = self._interfaces[interface_id].params
            self._interfaces[interface_id].params = [
                p for p in params if p.name != param_name
            ]
            return True

    # ==================== 阶段279: 代码生成 ====================

    def generate_sdk(self, language: TargetLanguage,
                     interface_ids: Optional[List[str]] = None,
                     version_number: str = "1.0.0",
                     base_url: str = "http://localhost:8080",
                     package_name: str = "api_client") -> Optional[SDKVersion]:
        """
        生成SDK

        Args:
            language: 目标语言
            interface_ids: 接口ID列表
            version_number: 版本号
            base_url: 基础URL
            package_name: 包名

        Returns:
            SDK版本
        """
        with self._lock:
            if interface_ids is None:
                interfaces = [i for i in self._interfaces.values()
                             if i.status != InterfaceStatus.REMOVED]
            else:
                interfaces = [self._interfaces[iid] for iid in interface_ids
                             if iid in self._interfaces and
                             self._interfaces[iid].status != InterfaceStatus.REMOVED]

            if not interfaces:
                return None

            # 使用自定义生成器或内置模板
            if language in self._custom_generators:
                code = self._custom_generators[language](interfaces)
            else:
                code = self._generate_from_templates(language, interfaces, base_url, package_name)

            version_id = self._generate_version_id(language, version_number)
            checksum = hashlib.md5(code.encode()).hexdigest()

            sdk_version = SDKVersion(
                version_id=version_id,
                version_number=version_number,
                language=language,
                interfaces=[i.interface_id for i in interfaces],
                generated_code=code,
                checksum=checksum
            )

            self._sdk_versions[language.value].append(sdk_version)
            if len(self._sdk_versions[language.value]) > self._max_versions:
                self._sdk_versions[language.value] = \
                    self._sdk_versions[language.value][-self._max_versions:]

            return sdk_version

    def _generate_version_id(self, language: TargetLanguage, version: str) -> str:
        """生成版本ID"""
        data = f"{language.value}_{version}_{time.time()}"
        return hashlib.md5(data.encode()).hexdigest()[:16]

    def _generate_from_templates(self, language: TargetLanguage,
                                interfaces: List[InterfaceDefinition],
                                base_url: str, package_name: str) -> str:
        """基于模板生成代码"""
        if language == TargetLanguage.PYTHON:
            return self._generate_python(interfaces, base_url, package_name)
        elif language == TargetLanguage.JAVASCRIPT:
            return self._generate_javascript(interfaces, base_url, package_name)
        elif language == TargetLanguage.TYPESCRIPT:
            return self._generate_typescript(interfaces, base_url, package_name)
        elif language == TargetLanguage.GO:
            return self._generate_go(interfaces, base_url, package_name)
        return f"// Language {language.value} not yet supported"

    def _type_to_python(self, ptype: ParamType) -> str:
        """类型映射到Python"""
        mapping = {
            ParamType.STRING: "str", ParamType.INTEGER: "int",
            ParamType.FLOAT: "float", ParamType.BOOLEAN: "bool",
            ParamType.ARRAY: "list", ParamType.OBJECT: "dict",
            ParamType.ANY: "Any"
        }
        return mapping.get(ptype, "Any")

    def _generate_python(self, interfaces: List[InterfaceDefinition],
                         base_url: str, package_name: str) -> str:
        """生成Python SDK"""
        lines = []
        lines.append(f'"""Auto-generated {package_name} SDK"""')
        lines.append("import requests")
        lines.append("from typing import Any, Dict, List, Optional")
        lines.append("")
        lines.append(f'BASE_URL = "{base_url}"')
        lines.append("")
        lines.append("")
        lines.append(f"class {self._to_class_name(package_name)}:")
        lines.append(f'    """{package_name} API Client"""')
        lines.append("")
        lines.append("    def __init__(self, base_url: str = BASE_URL,")
        lines.append("                 headers: Optional[Dict[str, str]] = None):")
        lines.append("        self.base_url = base_url.rstrip('/')")
        lines.append("        self.headers = headers or {}")
        lines.append("        self.session = requests.Session()")
        lines.append("        self.session.headers.update(self.headers)")
        lines.append("")

        for interface in interfaces:
            method_lower = interface.method.lower()
            func_name = self._to_snake_case(interface.name)
            params_str = self._build_python_params(interface.params)

            lines.append(f"    def {func_name}(self{', ' + params_str if params_str else ''}) -> Any:")
            if interface.description:
                lines.append(f'        """{interface.description}"""')
            if interface.status == InterfaceStatus.DEPRECATED and interface.deprecated_message:
                lines.append(f"        # DEPRECATED: {interface.deprecated_message}")

            lines.append(f'        url = f"{{self.base_url}}{interface.path}"')
            lines.append("        return self.session." + method_lower + "(url, json=params)")

            # 构建参数字典
            if interface.params:
                required_params = [p for p in interface.params if p.required]
                optional_params = [p for p in interface.params if not p.required]
                if required_params or optional_params:
                    lines.append("")
                    lines.append("        params = {}")
                    for p in interface.params:
                        lines.append(f"        params['{p.name}'] = {p.name}")

            lines.append("")
            lines.append("")

        return "\n".join(lines)

    def _generate_javascript(self, interfaces: List[InterfaceDefinition],
                             base_url: str, package_name: str) -> str:
        """生成JavaScript SDK"""
        lines = []
        lines.append(f"// Auto-generated {package_name} SDK")
        lines.append("")
        lines.append(f"const BASE_URL = '{base_url}';")
        lines.append("")
        lines.append(f"class {self._to_class_name(package_name)} {{")
        lines.append("  constructor(baseUrl = BASE_URL, headers = {}) {")
        lines.append("    this.baseUrl = baseUrl.replace(/\\/$/, '');")
        lines.append("    this.headers = headers;")
        lines.append("  }")
        lines.append("")

        for interface in interfaces:
            func_name = self._to_camel_case(interface.name)
            params_list = [p.name for p in interface.params]
            params_str = ", ".join(params_list)

            lines.append(f"  async {func_name}({params_str}) {{")
            if interface.description:
                lines.append(f"    // {interface.description}")
            lines.append(f"    const url = `${{this.baseUrl}}{interface.path}`;")
            lines.append(f"    const response = await fetch(url, {{")
            lines.append(f"      method: '{interface.method}',")
            lines.append(f"      headers: {{ 'Content-Type': 'application/json', ...this.headers }},")
            lines.append(f"      body: JSON.stringify({{ {', '.join(params_list)} }})")
            lines.append(f"    }});")
            lines.append(f"    return response.json();")
            lines.append(f"  }}")
            lines.append("")

        lines.append("}")
        lines.append(f"module.exports = {{ {self._to_class_name(package_name)} }};")
        return "\n".join(lines)

    def _generate_typescript(self, interfaces: List[InterfaceDefinition],
                             base_url: str, package_name: str) -> str:
        """生成TypeScript SDK"""
        js_code = self._generate_javascript(interfaces, base_url, package_name)

        # 添加类型定义
        type_lines = []
        type_lines.append("// Type Definitions")
        type_lines.append("")
        for interface in interfaces:
            params_str = ", ".join(
                f"{p.name}: {'string' if p.param_type == ParamType.STRING else 'number' if p.param_type in (ParamType.INTEGER, ParamType.FLOAT) else 'boolean' if p.param_type == ParamType.BOOLEAN else 'any'}"
                + (" | undefined" if not p.required else "")
                for p in interface.params
            )
            type_lines.append(f"export interface {self._to_class_name(interface.name)}Params {{")
            for p in interface.params:
                ts_type = self._param_type_to_ts(p.param_type)
                opt = "?" if not p.required else ""
                type_lines.append(f"  {p.name}{opt}: {ts_type};")
            type_lines.append("}")
            type_lines.append("")

        return "\n".join(type_lines) + "\n\n" + js_code

    def _param_type_to_ts(self, ptype: ParamType) -> str:
        """类型映射到TypeScript"""
        mapping = {
            ParamType.STRING: "string", ParamType.INTEGER: "number",
            ParamType.FLOAT: "number", ParamType.BOOLEAN: "boolean",
            ParamType.ARRAY: "any[]", ParamType.OBJECT: "Record<string, any>",
            ParamType.ANY: "any"
        }
        return mapping.get(ptype, "any")

    def _generate_go(self, interfaces: List[InterfaceDefinition],
                     base_url: str, package_name: str) -> str:
        """生成Go SDK"""
        lines = []
        lines.append(f"package {package_name}")
        lines.append("")
        lines.append("import (")
        lines.append('    "bytes"')
        lines.append('    "encoding/json"')
        lines.append('    "fmt"')
        lines.append('    "net/http"')
        lines.append('    "io"')
        lines.append(")")
        lines.append("")
        lines.append(f"const BaseURL = \"{base_url}\"")
        lines.append("")
        lines.append(f"type {self._to_pascal_case(package_name)} struct {{")
        lines.append("    BaseURL string")
        lines.append("    Client  *http.Client")
        lines.append("}")
        lines.append("")
        lines.append(f"func New{self._to_pascal_case(package_name)}(baseURL string) *{self._to_pascal_case(package_name)} {{")
        lines.append("    if baseURL == \"\" {")
        lines.append("        baseURL = BaseURL")
        lines.append("    }")
        lines.append(f"    return &{self._to_pascal_case(package_name)}{{BaseURL: baseURL, Client: &http.Client{{}}}}")
        lines.append("}")
        lines.append("")

        for interface in interfaces:
            func_name = self._to_pascal_case(interface.name)
            lines.append(f"func (c *{self._to_pascal_case(package_name)}) {func_name}() {{")
            if interface.description:
                lines.append(f"    // {interface.description}")
            lines.append(f'    url := fmt.Sprintf("%s{interface.path}", c.BaseURL)')
            lines.append(f"    req, _ := http.NewRequest(\"{interface.method}\", url, nil)")
            lines.append(f"    resp, err := c.Client.Do(req)")
            lines.append(f"    if err != nil {{ return }}")
            lines.append(f"    defer resp.Body.Close()")
            lines.append(f"    body, _ := io.ReadAll(resp.Body)")
            lines.append(f"    fmt.Println(string(body))")
            lines.append("}")
            lines.append("")

        return "\n".join(lines)

    def _to_class_name(self, name: str) -> str:
        """转换为类名"""
        return re.sub(r'[^a-zA-Z0-9]', '', name.title().replace('_', ''))

    def _to_snake_case(self, name: str) -> str:
        """转换为蛇形命名"""
        s1 = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1_\2', name)
        return re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', s1).lower()

    def _to_camel_case(self, name: str) -> str:
        """转换为驼峰命名"""
        parts = name.replace('-', '_').split('_')
        return parts[0].lower() + ''.join(p.title() for p in parts[1:])

    def _to_pascal_case(self, name: str) -> str:
        """转换为帕斯卡命名"""
        return ''.join(p.title() for p in name.replace('-', '_').split('_'))

    def _build_python_params(self, params: List[ParamDefinition]) -> str:
        """构建Python参数字符串"""
        parts = []
        for p in params:
            py_type = self._type_to_python(p.param_type)
            if p.required:
                parts.append(f"{p.name}: {py_type}")
            else:
                default = f'"{p.default_value}"' if p.default_value is not None else "None"
                parts.append(f"{p.name}: Optional[{py_type}] = {default}")
        return ", ".join(parts)

    def register_custom_generator(self, language: TargetLanguage,
                                 generator: Callable[[List[InterfaceDefinition]], str]) -> None:
        """注册自定义代码生成器"""
        with self._lock:
            self._custom_generators[language] = generator

    def register_template(self, template: CodeTemplate) -> None:
        """注册代码模板"""
        with self._lock:
            self._templates[template.language].append(template)

    def _register_builtin_templates(self) -> None:
        """注册内置模板"""
        pass  # 内置生成器已直接实现

    # ==================== 阶段280: 版本管理 ====================

    def get_sdk_version(self, language: TargetLanguage,
                       version_number: str) -> Optional[SDKVersion]:
        """获取SDK版本"""
        with self._lock:
            versions = self._sdk_versions.get(language.value, [])
            for v in versions:
                if v.version_number == version_number:
                    return v
            return None

    def list_sdk_versions(self, language: Optional[TargetLanguage] = None,
                         limit: int = 20) -> List[SDKVersion]:
        """列出SDK版本"""
        with self._lock:
            if language:
                versions = self._sdk_versions.get(language.value, [])
            else:
                versions = []
                for lang_versions in self._sdk_versions.values():
                    versions.extend(lang_versions)
            return versions[-limit:]

    def get_latest_sdk(self, language: TargetLanguage) -> Optional[SDKVersion]:
        """获取最新SDK版本"""
        with self._lock:
            versions = self._sdk_versions.get(language.value, [])
            return versions[-1] if versions else None

    def compare_versions(self, language: TargetLanguage,
                        version1: str, version2: str) -> Optional[Dict[str, Any]]:
        """比较两个SDK版本"""
        with self._lock:
            v1 = self.get_sdk_version(language, version1)
            v2 = self.get_sdk_version(language, version2)
            if not v1 or not v2:
                return None

            interfaces1 = set(v1.interfaces)
            interfaces2 = set(v2.interfaces)

            return {
                "version1": version1,
                "version2": version2,
                "added": list(interfaces2 - interfaces1),
                "removed": list(interfaces1 - interfaces2),
                "common": list(interfaces1 & interfaces2),
                "checksum_match": v1.checksum == v2.checksum,
                "interface_count_diff": len(v2.interfaces) - len(v1.interfaces)
            }

    def get_changelog(self, language: TargetLanguage) -> List[Dict[str, Any]]:
        """获取变更日志"""
        with self._lock:
            versions = self._sdk_versions.get(language.value, [])
            changelog = []
            for i in range(1, len(versions)):
                prev = versions[i - 1]
                curr = versions[i]
                prev_ids = set(prev.interfaces)
                curr_ids = set(curr.interfaces)
                changelog.append({
                    "from_version": prev.version_number,
                    "to_version": curr.version_number,
                    "added": list(curr_ids - prev_ids),
                    "removed": list(prev_ids - curr_ids),
                    "timestamp": curr.created_at
                })
            return changelog

    def validate_sdk(self, language: TargetLanguage,
                    version_number: str) -> Dict[str, Any]:
        """验证SDK完整性"""
        with self._lock:
            sdk = self.get_sdk_version(language, version_number)
            if not sdk:
                return {"valid": False, "error": "Version not found"}

            issues = []
            for iid in sdk.interfaces:
                interface = self._interfaces.get(iid)
                if not interface:
                    issues.append(f"Missing interface: {iid}")
                elif interface.status == InterfaceStatus.REMOVED:
                    issues.append(f"Removed interface: {iid}")
                elif interface.status == InterfaceStatus.DEPRECATED:
                    issues.append(f"Deprecated interface: {iid}")

            return {
                "valid": len(issues) == 0,
                "issues": issues,
                "interface_count": len(sdk.interfaces),
                "checksum": sdk.checksum
            }


# 全局单例
_sdk_generator_instance: Optional[SDKGenerator] = None
_sdk_generator_lock = threading.Lock()


def get_sdk_generator() -> SDKGenerator:
    """获取SDK生成器全局单例"""
    global _sdk_generator_instance
    if _sdk_generator_instance is None:
        with _sdk_generator_lock:
            if _sdk_generator_instance is None:
                _sdk_generator_instance = SDKGenerator()
    return _sdk_generator_instance
