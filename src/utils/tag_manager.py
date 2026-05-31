"""
Agent可靠记忆系统 - 记忆标签系统
阶段161-163: 标签的创建、管理、查询与统计

设计原则:
- 确定性规则驱动，无模型依赖
- 线程安全（RLock）
- 全局单例模式
- 支持层级标签、自动标签、标签统计
"""

import threading
import time
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Set, Optional, Tuple
from collections import defaultdict


class TagType(Enum):
    """标签类型"""
    MANUAL = "manual"          # 手动标签
    AUTO = "auto"              # 自动标签（基于规则）
    SYSTEM = "system"          # 系统标签
    CATEGORY = "category"      # 分类标签
    PRIORITY = "priority"      # 优先级标签
    TEMPORAL = "temporal"      # 时间标签


class TagColor(Enum):
    """标签颜色（用于可视化）"""
    RED = "#e74c3c"
    ORANGE = "#e67e22"
    YELLOW = "#f1c40f"
    GREEN = "#2ecc71"
    BLUE = "#3498db"
    PURPLE = "#9b59b6"
    GRAY = "#95a5a6"
    DEFAULT = "#34495e"


@dataclass
class Tag:
    """标签数据结构"""
    name: str                          # 标签名称
    tag_type: TagType = TagType.MANUAL # 标签类型
    color: TagColor = TagColor.DEFAULT # 标签颜色
    description: str = ""              # 标签描述
    parent: Optional[str] = None       # 父标签名称（层级支持）
    aliases: List[str] = field(default_factory=list)  # 别名列表
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    metadata: Dict = field(default_factory=dict)

    @property
    def full_path(self) -> str:
        """获取标签完整路径"""
        if self.parent:
            return f"{self.parent}/{self.name}"
        return self.name

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "type": self.tag_type.value,
            "color": self.color.value,
            "description": self.description,
            "parent": self.parent,
            "aliases": self.aliases,
            "full_path": self.full_path,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": self.metadata,
        }


@dataclass
class TagRule:
    """自动标签规则"""
    rule_id: str                       # 规则ID
    tag_name: str                      # 关联标签
    field: str = "content"             # 匹配字段 (content/metadata/layer/namespace)
    pattern: str = ""                  # 正则表达式模式
    keyword_list: List[str] = field(default_factory=list)  # 关键词列表（任一匹配）
    require_all: bool = False          # 是否需要所有关键词都匹配
    layer_filter: Optional[str] = None # 层级过滤 (L1/L2/L3)
    namespace_filter: Optional[str] = None  # 命名空间过滤
    priority: int = 0                  # 规则优先级（越大越先执行）
    enabled: bool = True               # 是否启用
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict:
        return {
            "rule_id": self.rule_id,
            "tag_name": self.tag_name,
            "field": self.field,
            "pattern": self.pattern,
            "keyword_list": self.keyword_list,
            "require_all": self.require_all,
            "layer_filter": self.layer_filter,
            "namespace_filter": self.namespace_filter,
            "priority": self.priority,
            "enabled": self.enabled,
            "created_at": self.created_at,
        }


@dataclass
class TagStatistics:
    """标签统计信息"""
    tag_name: str
    total_count: int = 0
    memory_ids: Set[str] = field(default_factory=set)
    created_today: int = 0
    created_this_week: int = 0
    created_this_month: int = 0
    child_tags: List[str] = field(default_factory=list)
    related_tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "tag_name": self.tag_name,
            "total_count": self.total_count,
            "memory_count": len(self.memory_ids),
            "created_today": self.created_today,
            "created_this_week": self.created_this_week,
            "created_this_month": self.created_this_month,
            "child_tags": self.child_tags,
            "related_tags": self.related_tags,
        }


class TagManager:
    """
    记忆标签管理器

    功能:
    - 标签CRUD操作
    - 层级标签支持（父子关系）
    - 自动标签规则引擎
    - 标签查询与过滤
    - 标签统计与分析
    - 标签合并与拆分
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._tags: Dict[str, Tag] = {}                  # name -> Tag
        self._memory_tags: Dict[str, Set[str]] = {}       # memory_id -> set of tag names
        self._tag_memories: Dict[str, Set[str]] = {}      # tag_name -> set of memory_ids
        self._rules: Dict[str, TagRule] = {}              # rule_id -> TagRule
        self._rule_counter: int = 0
        self._alias_index: Dict[str, str] = {}            # alias -> canonical tag name

    # ==================== 标签CRUD ====================

    def create_tag(self, name: str, tag_type: TagType = TagType.MANUAL,
                   color: TagColor = TagColor.DEFAULT,
                   description: str = "", parent: Optional[str] = None,
                   aliases: Optional[List[str]] = None,
                   metadata: Optional[Dict] = None) -> Tag:
        """
        创建标签

        Args:
            name: 标签名称（唯一标识）
            tag_type: 标签类型
            color: 标签颜色
            description: 标签描述
            parent: 父标签名称
            aliases: 别名列表
            metadata: 额外元数据

        Returns:
            创建的Tag对象

        Raises:
            ValueError: 标签已存在或父标签不存在
        """
        with self._lock:
            name = self._normalize_name(name)
            if name in self._tags:
                raise ValueError(f"标签 '{name}' 已存在")

            if parent and parent not in self._tags:
                raise ValueError(f"父标签 '{parent}' 不存在")

            # 检查层级深度（最多5层）
            depth = self._get_depth(parent)
            if depth >= 5:
                raise ValueError(f"标签层级深度不能超过5层（当前深度: {depth}）")

            tag = Tag(
                name=name,
                tag_type=tag_type,
                color=color,
                description=description,
                parent=parent,
                aliases=aliases or [],
                metadata=metadata or {},
            )
            self._tags[name] = tag
            self._tag_memories[name] = set()

            # 建立别名索引
            for alias in tag.aliases:
                normalized_alias = self._normalize_name(alias)
                self._alias_index[normalized_alias] = name

            return tag

    def get_tag(self, name: str) -> Optional[Tag]:
        """获取标签（支持别名查找）"""
        with self._lock:
            name = self._normalize_name(name)
            if name in self._tags:
                return self._tags[name]
            # 尝试别名查找
            if name in self._alias_index:
                canonical = self._alias_index[name]
                return self._tags.get(canonical)
            return None

    def update_tag(self, name: str, description: Optional[str] = None,
                   color: Optional[TagColor] = None,
                   add_aliases: Optional[List[str]] = None,
                   remove_aliases: Optional[List[str]] = None,
                   metadata: Optional[Dict] = None) -> Optional[Tag]:
        """更新标签属性"""
        with self._lock:
            tag = self._tags.get(name)
            if not tag:
                return None

            if description is not None:
                tag.description = description
            if color is not None:
                tag.color = color
            if add_aliases:
                for alias in add_aliases:
                    normalized = self._normalize_name(alias)
                    self._alias_index[normalized] = name
                    tag.aliases.append(alias)
            if remove_aliases:
                for alias in remove_aliases:
                    normalized = self._normalize_name(alias)
                    self._alias_index.pop(normalized, None)
                    if alias in tag.aliases:
                        tag.aliases.remove(alias)
            if metadata is not None:
                tag.metadata.update(metadata)

            tag.updated_at = time.time()
            return tag

    def delete_tag(self, name: str, cascade: bool = False) -> bool:
        """
        删除标签

        Args:
            name: 标签名称
            cascade: 是否级联删除子标签

        Returns:
            是否删除成功
        """
        with self._lock:
            if name not in self._tags:
                return False

            # 检查子标签
            children = self._get_children(name)
            if children and not cascade:
                raise ValueError(
                    f"标签 '{name}' 有 {len(children)} 个子标签，"
                    f"请使用 cascade=True 级联删除"
                )

            if cascade:
                for child in children:
                    self.delete_tag(child, cascade=True)

            tag = self._tags[name]

            # 清理别名索引
            for alias in tag.aliases:
                normalized = self._normalize_name(alias)
                self._alias_index.pop(normalized, None)

            # 清理记忆关联
            memory_ids = self._tag_memories.pop(name, set())
            for mid in memory_ids:
                if mid in self._memory_tags:
                    self._memory_tags[mid].discard(name)

            del self._tags[name]
            return True

    def list_tags(self, tag_type: Optional[TagType] = None,
                  parent: Optional[str] = None,
                  search: Optional[str] = None,
                  sort_by: str = "name",
                  ascending: bool = True) -> List[Tag]:
        """
        列出标签

        Args:
            tag_type: 按类型过滤
            parent: 按父标签过滤
            search: 搜索关键词（匹配名称、描述、别名）
            sort_by: 排序字段 (name/created_at/updated_at/total_count)
            ascending: 是否升序
        """
        with self._lock:
            tags = list(self._tags.values())

            if tag_type:
                tags = [t for t in tags if t.tag_type == tag_type]
            if parent is not None:
                tags = [t for t in tags if t.parent == parent]
            if search:
                search_lower = search.lower()
                tags = [t for t in tags if
                        search_lower in t.name.lower() or
                        search_lower in t.description.lower() or
                        any(search_lower in a.lower() for a in t.aliases)]

            # 排序
            if sort_by == "name":
                tags.sort(key=lambda t: t.name, reverse=not ascending)
            elif sort_by == "created_at":
                tags.sort(key=lambda t: t.created_at, reverse=not ascending)
            elif sort_by == "updated_at":
                tags.sort(key=lambda t: t.updated_at, reverse=not ascending)
            elif sort_by == "total_count":
                tags.sort(
                    key=lambda t: len(self._tag_memories.get(t.name, set())),
                    reverse=not ascending
                )

            return tags

    # ==================== 记忆标签关联 ====================

    def tag_memory(self, memory_id: str, tag_names: List[str],
                   auto_create: bool = False) -> Dict[str, bool]:
        """
        为记忆添加标签

        Args:
            memory_id: 记忆ID
            tag_names: 标签名称列表
            auto_create: 标签不存在时是否自动创建

        Returns:
            {tag_name: success} 字典
        """
        with self._lock:
            results = {}
            for name in tag_names:
                name = self._normalize_name(name)
                if name not in self._tags:
                    if auto_create:
                        self.create_tag(name, tag_type=TagType.MANUAL)
                    else:
                        results[name] = False
                        continue

                # 建立双向关联
                if memory_id not in self._memory_tags:
                    self._memory_tags[memory_id] = set()
                self._memory_tags[memory_id].add(name)
                self._tag_memories[name].add(memory_id)
                results[name] = True

            return results

    def untag_memory(self, memory_id: str, tag_names: List[str]) -> int:
        """
        移除记忆的标签

        Returns:
            成功移除的数量
        """
        with self._lock:
            count = 0
            for name in tag_names:
                name = self._normalize_name(name)
                if memory_id in self._memory_tags and name in self._memory_tags[memory_id]:
                    self._memory_tags[memory_id].discard(name)
                    if name in self._tag_memories:
                        self._tag_memories[name].discard(memory_id)
                    count += 1

            # 清理空集合
            if memory_id in self._memory_tags and not self._memory_tags[memory_id]:
                del self._memory_tags[memory_id]

            return count

    def get_memory_tags(self, memory_id: str) -> List[Tag]:
        """获取记忆的所有标签"""
        with self._lock:
            tag_names = self._memory_tags.get(memory_id, set())
            return [self._tags[name] for name in tag_names if name in self._tags]

    def get_memories_by_tag(self, tag_name: str, include_children: bool = False) -> Set[str]:
        """
        获取带有指定标签的所有记忆ID

        Args:
            tag_name: 标签名称
            include_children: 是否包含子标签的记忆
        """
        with self._lock:
            tag_name = self._normalize_name(tag_name)
            memory_ids = set(self._tag_memories.get(tag_name, set()))

            if include_children:
                children = self._get_children(tag_name)
                for child in children:
                    memory_ids.update(self._tag_memories.get(child, set()))

            return memory_ids

    # ==================== 自动标签规则 ====================

    def add_rule(self, tag_name: str, pattern: str = "",
                 keyword_list: Optional[List[str]] = None,
                 field: str = "content", layer_filter: Optional[str] = None,
                 namespace_filter: Optional[str] = None,
                 require_all: bool = False, priority: int = 0) -> TagRule:
        """
        添加自动标签规则

        Args:
            tag_name: 关联标签名称（必须已存在）
            pattern: 正则表达式
            keyword_list: 关键词列表
            field: 匹配字段
            layer_filter: 层级过滤
            namespace_filter: 命名空间过滤
            require_all: 是否需要所有关键词匹配
            priority: 优先级
        """
        with self._lock:
            tag_name = self._normalize_name(tag_name)
            if tag_name not in self._tags:
                raise ValueError(f"标签 '{tag_name}' 不存在，请先创建标签")

            self._rule_counter += 1
            rule_id = f"rule_{self._rule_counter:04d}"

            rule = TagRule(
                rule_id=rule_id,
                tag_name=tag_name,
                field=field,
                pattern=pattern,
                keyword_list=keyword_list or [],
                require_all=require_all,
                layer_filter=layer_filter,
                namespace_filter=namespace_filter,
                priority=priority,
            )
            self._rules[rule_id] = rule
            return rule

    def remove_rule(self, rule_id: str) -> bool:
        """移除自动标签规则"""
        with self._lock:
            return self._rules.pop(rule_id, None) is not None

    def evaluate_rules(self, memory_data: Dict) -> List[str]:
        """
        对记忆数据执行所有规则，返回匹配的标签名列表

        Args:
            memory_data: 记忆数据字典，应包含:
                - content: 记忆内容
                - layer: 记忆层级 (L1/L2/L3)
                - namespace: 命名空间
                - metadata: 元数据字典
        """
        with self._lock:
            # 按优先级排序
            sorted_rules = sorted(
                [r for r in self._rules.values() if r.enabled],
                key=lambda r: r.priority,
                reverse=True
            )

            matched_tags = []
            for rule in sorted_rules:
                if self._evaluate_single_rule(rule, memory_data):
                    if rule.tag_name not in matched_tags:
                        matched_tags.append(rule.tag_name)

            return matched_tags

    def auto_tag_memory(self, memory_id: str, memory_data: Dict,
                        auto_create: bool = False) -> List[str]:
        """
        自动为记忆打标签

        Args:
            memory_id: 记忆ID
            memory_data: 记忆数据
            auto_create: 是否自动创建不存在的标签

        Returns:
            新添加的标签列表
        """
        matched = self.evaluate_rules(memory_data)
        results = self.tag_memory(memory_id, matched, auto_create=auto_create)
        return [name for name, success in results.items() if success]

    def _evaluate_single_rule(self, rule: TagRule, memory_data: Dict) -> bool:
        """评估单条规则"""
        # 层级过滤
        if rule.layer_filter:
            mem_layer = memory_data.get("layer", "")
            if mem_layer != rule.layer_filter:
                return False

        # 命名空间过滤
        if rule.namespace_filter:
            mem_ns = memory_data.get("namespace", "")
            if mem_ns != rule.namespace_filter:
                return False

        # 获取匹配文本
        field_value = ""
        if rule.field == "content":
            field_value = memory_data.get("content", "")
        elif rule.field == "metadata":
            field_value = str(memory_data.get("metadata", {}))
        elif rule.field == "layer":
            field_value = memory_data.get("layer", "")
        elif rule.field == "namespace":
            field_value = memory_data.get("namespace", "")

        field_value_lower = field_value.lower()

        # 正则匹配
        if rule.pattern:
            try:
                if not re.search(rule.pattern, field_value):
                    return False
            except re.error:
                return False

        # 关键词匹配
        if rule.keyword_list:
            if rule.require_all:
                if not all(kw.lower() in field_value_lower for kw in rule.keyword_list):
                    return False
            else:
                if not any(kw.lower() in field_value_lower for kw in rule.keyword_list):
                    return False

        return True

    # ==================== 层级标签 ====================

    def get_children(self, parent_name: str) -> List[Tag]:
        """获取子标签列表"""
        with self._lock:
            return self._get_children(parent_name)

    def _get_children(self, parent_name: str) -> List[Tag]:
        """内部方法：获取子标签"""
        return [t for t in self._tags.values() if t.parent == parent_name]

    def get_tag_tree(self, root: Optional[str] = None) -> Dict:
        """
        获取标签树结构

        Args:
            root: 根标签名称（None表示所有顶层标签）

        Returns:
            树形字典结构
        """
        with self._lock:
            if root:
                return self._build_subtree(root)
            else:
                top_level = [t for t in self._tags.values() if t.parent is None]
                return {
                    "roots": [self._build_subtree(t.name) for t in top_level],
                    "total_tags": len(self._tags),
                }

    def _build_subtree(self, name: str) -> Dict:
        """递归构建子树"""
        tag = self._tags.get(name)
        if not tag:
            return {}

        children = self._get_children(name)
        return {
            "tag": tag.to_dict(),
            "memory_count": len(self._tag_memories.get(name, set())),
            "children": [self._build_subtree(c.name) for c in children],
        }

    def _get_depth(self, parent_name: Optional[str]) -> int:
        """计算标签层级深度"""
        depth = 0
        current = parent_name
        while current:
            depth += 1
            tag = self._tags.get(current)
            if not tag:
                break
            current = tag.parent
        return depth

    # ==================== 标签统计 ====================

    def get_tag_stats(self, tag_name: str) -> Optional[TagStatistics]:
        """获取单个标签的统计信息"""
        with self._lock:
            if tag_name not in self._tags:
                return None

            memory_ids = self._tag_memories.get(tag_name, set())
            children = self._get_children(tag_name)

            # 查找关联标签（共同出现在同一记忆上的标签）
            related = set()
            for mid in memory_ids:
                if mid in self._memory_tags:
                    related.update(self._memory_tags[mid])
            related.discard(tag_name)

            return TagStatistics(
                tag_name=tag_name,
                total_count=len(memory_ids),
                memory_ids=memory_ids,
                child_tags=[c.name for c in children],
                related_tags=list(related)[:20],
            )

    def get_all_stats(self) -> List[Dict]:
        """获取所有标签的统计信息"""
        with self._lock:
            stats = []
            for name in self._tags:
                s = self.get_tag_stats(name)
                if s:
                    stats.append(s.to_dict())
            return stats

    def get_top_tags(self, limit: int = 10) -> List[Dict]:
        """获取使用最多的标签"""
        with self._lock:
            tag_counts = [
                (name, len(mids))
                for name, mids in self._tag_memories.items()
            ]
            tag_counts.sort(key=lambda x: x[1], reverse=True)
            return [
                {"tag_name": name, "count": count}
                for name, count in tag_counts[:limit]
            ]

    def get_tag_cloud(self) -> List[Dict]:
        """
        获取标签云数据（用于可视化）

        Returns:
            [{"name": tag_name, "weight": count, "color": color_hex}, ...]
        """
        with self._lock:
            cloud = []
            max_count = 1
            counts = {}

            for name, mids in self._tag_memories.items():
                counts[name] = len(mids)
                if len(mids) > max_count:
                    max_count = len(mids)

            for name, count in counts.items():
                tag = self._tags.get(name)
                weight = count / max_count if max_count > 0 else 0
                cloud.append({
                    "name": name,
                    "weight": weight,
                    "count": count,
                    "color": tag.color.value if tag else TagColor.DEFAULT.value,
                })

            cloud.sort(key=lambda x: x["weight"], reverse=True)
            return cloud

    # ==================== 标签操作 ====================

    def merge_tags(self, source: str, target: str) -> Dict:
        """
        合并标签：将source标签的所有记忆转移到target标签

        Args:
            source: 源标签名称
            target: 目标标签名称

        Returns:
            合并结果统计
        """
        with self._lock:
            source = self._normalize_name(source)
            target = self._normalize_name(target)

            if source not in self._tags:
                raise ValueError(f"源标签 '{source}' 不存在")
            if target not in self._tags:
                raise ValueError(f"目标标签 '{target}' 不存在")
            if source == target:
                raise ValueError("源标签和目标标签不能相同")

            memory_ids = self._tag_memories.get(source, set())
            transferred = 0

            for mid in memory_ids:
                if mid in self._memory_tags:
                    self._memory_tags[mid].discard(source)
                    self._memory_tags[mid].add(target)
                    self._tag_memories[target].add(mid)
                    transferred += 1

            # 更新子标签的父指向
            children = self._get_children(source)
            for child in children:
                child.parent = target

            # 删除源标签
            self._tag_memories.pop(source, None)
            del self._tags[source]

            # 更新规则中的标签引用
            for rule in self._rules.values():
                if rule.tag_name == source:
                    rule.tag_name = target

            return {
                "source": source,
                "target": target,
                "transferred_memories": transferred,
                "updated_children": len(children),
                "updated_rules": sum(
                    1 for r in self._rules.values() if r.tag_name == target
                ),
            }

    def find_orphan_tags(self) -> List[Tag]:
        """查找孤立标签（没有关联任何记忆的标签）"""
        with self._lock:
            orphans = []
            for name, tag in self._tags.items():
                if not self._tag_memories.get(name):
                    orphans.append(tag)
            return orphans

    def cleanup_orphan_tags(self) -> int:
        """清理孤立标签（仅限自动和系统类型）"""
        with self._lock:
            orphans = self.find_orphan_tags()
            cleaned = 0
            for tag in orphans:
                if tag.tag_type in (TagType.AUTO, TagType.SYSTEM):
                    self.delete_tag(tag.name)
                    cleaned += 1
            return cleaned

    # ==================== 批量操作 ====================

    def batch_tag(self, mappings: Dict[str, List[str]],
                  auto_create: bool = False) -> Dict[str, int]:
        """
        批量打标签

        Args:
            mappings: {memory_id: [tag_names]}
            auto_create: 是否自动创建标签

        Returns:
            统计信息
        """
        with self._lock:
            total = 0
            success = 0
            for memory_id, tag_names in mappings.items():
                results = self.tag_memory(memory_id, tag_names, auto_create)
                total += len(tag_names)
                success += sum(1 for v in results.values() if v)

            return {
                "total_operations": total,
                "successful": success,
                "failed": total - success,
            }

    def export_tags(self) -> Dict:
        """导出所有标签数据"""
        with self._lock:
            return {
                "tags": {name: tag.to_dict() for name, tag in self._tags.items()},
                "rules": {rid: rule.to_dict() for rid, rule in self._rules.items()},
                "memory_tags": {
                    mid: list(tags) for mid, tags in self._memory_tags.items()
                },
                "statistics": {
                    "total_tags": len(self._tags),
                    "total_rules": len(self._rules),
                    "total_tagged_memories": len(self._memory_tags),
                },
            }

    def import_tags(self, data: Dict, merge: bool = True) -> Dict:
        """
        导入标签数据

        Args:
            data: export_tags() 导出的数据
            merge: 是否合并（True）或替换（False）
        """
        with self._lock:
            if not merge:
                self._tags.clear()
                self._memory_tags.clear()
                self._tag_memories.clear()
                self._rules.clear()
                self._alias_index.clear()

            imported_tags = 0
            imported_rules = 0

            for name, tag_data in data.get("tags", {}).items():
                if name not in self._tags:
                    tag = Tag(
                        name=tag_data["name"],
                        tag_type=TagType(tag_data.get("type", "manual")),
                        color=TagColor(tag_data.get("color", "#34495e")),
                        description=tag_data.get("description", ""),
                        parent=tag_data.get("parent"),
                        aliases=tag_data.get("aliases", []),
                        metadata=tag_data.get("metadata", {}),
                    )
                    self._tags[name] = tag
                    self._tag_memories[name] = set()
                    for alias in tag.aliases:
                        self._alias_index[self._normalize_name(alias)] = name
                    imported_tags += 1

            for rid, rule_data in data.get("rules", {}).items():
                if rid not in self._rules:
                    rule = TagRule(
                        rule_id=rule_data["rule_id"],
                        tag_name=rule_data["tag_name"],
                        field=rule_data.get("field", "content"),
                        pattern=rule_data.get("pattern", ""),
                        keyword_list=rule_data.get("keyword_list", []),
                        require_all=rule_data.get("require_all", False),
                        layer_filter=rule_data.get("layer_filter"),
                        namespace_filter=rule_data.get("namespace_filter"),
                        priority=rule_data.get("priority", 0),
                        enabled=rule_data.get("enabled", True),
                    )
                    self._rules[rid] = rule
                    imported_rules += 1

            return {
                "imported_tags": imported_tags,
                "imported_rules": imported_rules,
                "mode": "merge" if merge else "replace",
            }

    # ==================== 工具方法 ====================

    @staticmethod
    def _normalize_name(name: str) -> str:
        """标准化标签名称"""
        return name.strip().lower().replace(" ", "_")

    def get_summary(self) -> Dict:
        """获取标签系统摘要"""
        with self._lock:
            total_associations = sum(len(mids) for mids in self._tag_memories.values())
            return {
                "total_tags": len(self._tags),
                "total_rules": len(self._rules),
                "tagged_memories": len(self._memory_tags),
                "total_associations": total_associations,
                "orphan_tags": len(self.find_orphan_tags()),
                "tag_types": {
                    t.value: sum(1 for tag in self._tags.values() if tag.tag_type == t)
                    for t in TagType
                },
            }


# ==================== 全局单例 ====================

_global_tag_manager: Optional[TagManager] = None
_global_tag_manager_lock = threading.Lock()


def get_tag_manager() -> TagManager:
    """获取全局标签管理器实例"""
    global _global_tag_manager
    if _global_tag_manager is None:
        with _global_tag_manager_lock:
            if _global_tag_manager is None:
                _global_tag_manager = TagManager()
    return _global_tag_manager
