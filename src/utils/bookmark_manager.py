"""
Agent可靠记忆系统 - 记忆收藏与书签系统
阶段164-166: 收藏夹、书签、收藏夹组织与管理

设计原则:
- 确定性规则驱动，无模型依赖
- 线程安全（RLock）
- 全局单例模式
- 支持收藏夹分组、书签注解、收藏搜索
"""

import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple


class BookmarkType(Enum):
    """书签类型"""
    FAVORITE = "favorite"        # 收藏
    IMPORTANT = "important"      # 重要标记
    READ_LATER = "read_later"    # 稍后阅读
    ARCHIVED = "archived"        # 已归档
    PINNED = "pinned"            # 置顶
    CUSTOM = "custom"            # 自定义


class FolderType(Enum):
    """收藏夹类型"""
    SYSTEM = "system"            # 系统预设
    USER = "user"                # 用户创建
    SMART = "smart"              # 智能收藏夹（基于规则）


@dataclass
class Bookmark:
    """书签数据结构"""
    memory_id: str                           # 关联的记忆ID
    bookmark_type: BookmarkType = BookmarkType.FAVORITE
    note: str = ""                           # 书签注解
    tags: List[str] = field(default_factory=list)  # 书签标签
    priority: int = 0                        # 优先级（越大越靠前）
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    metadata: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "memory_id": self.memory_id,
            "type": self.bookmark_type.value,
            "note": self.note,
            "tags": self.tags,
            "priority": self.priority,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": self.metadata,
        }


@dataclass
class Folder:
    """收藏夹数据结构"""
    name: str                               # 收藏夹名称
    folder_type: FolderType = FolderType.USER
    description: str = ""
    parent: Optional[str] = None            # 父收藏夹
    icon: str = "📁"                        # 图标
    color: str = "#3498db"                  # 颜色
    sort_order: int = 0                     # 排序顺序
    is_collapsed: bool = False              # 是否折叠
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    # 智能收藏夹规则
    smart_rules: Dict = field(default_factory=dict)
    smart_rules_cache: Set[str] = field(default_factory=set)  # 缓存匹配的记忆ID
    smart_rules_updated: float = 0          # 上次更新缓存时间

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "type": self.folder_type.value,
            "description": self.description,
            "parent": self.parent,
            "icon": self.icon,
            "color": self.color,
            "sort_order": self.sort_order,
            "is_collapsed": self.is_collapsed,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "is_smart": self.folder_type == FolderType.SMART,
            "smart_rules": self.smart_rules if self.folder_type == FolderType.SMART else None,
            "memory_count": len(self.smart_rules_cache) if self.folder_type == FolderType.SMART else 0,
        }


@dataclass
class CollectionStats:
    """收藏统计"""
    total_bookmarks: int = 0
    by_type: Dict[str, int] = field(default_factory=dict)
    total_folders: int = 0
    folder_sizes: Dict[str, int] = field(default_factory=dict)
    recent_bookmarks: List[Dict] = field(default_factory=list)
    most_bookmarked: List[Dict] = field(default_factory=list)


class BookmarkManager:
    """
    记忆收藏与书签管理器

    功能:
    - 书签CRUD（收藏、重要、稍后读、置顶等）
    - 收藏夹管理（分组、层级、智能收藏夹）
    - 书签搜索与过滤
    - 收藏统计与分析
    - 批量操作
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._bookmarks: Dict[str, Dict[str, Bookmark]] = {}   # memory_id -> {type -> Bookmark}
        self._folders: Dict[str, Folder] = {}                   # folder_name -> Folder
        self._folder_memories: Dict[str, Set[str]] = {}         # folder_name -> set of memory_ids
        self._memory_folders: Dict[str, Set[str]] = {}          # memory_id -> set of folder_names
        self._bookmark_counter: int = 0

        # 创建系统预设收藏夹
        self._init_system_folders()

    def _init_system_folders(self):
        """初始化系统预设收藏夹"""
        system_folders = [
            ("favorites", "⭐", "#f1c40f", "我的收藏"),
            ("important", "🔴", "#e74c3c", "重要标记"),
            ("read_later", "📖", "#3498db", "稍后阅读"),
            ("archived", "📦", "#95a5a6", "已归档"),
            ("pinned", "📌", "#e67e22", "置顶记忆"),
        ]
        for name, icon, color, desc in system_folders:
            folder = Folder(
                name=name,
                folder_type=FolderType.SYSTEM,
                description=desc,
                icon=icon,
                color=color,
                sort_order=len(self._folders),
            )
            self._folders[name] = folder
            self._folder_memories[name] = set()

    # ==================== 书签操作 ====================

    def add_bookmark(self, memory_id: str,
                     bookmark_type: BookmarkType = BookmarkType.FAVORITE,
                     note: str = "", tags: Optional[List[str]] = None,
                     priority: int = 0,
                     folders: Optional[List[str]] = None,
                     metadata: Optional[Dict] = None) -> Bookmark:
        """
        添加书签

        Args:
            memory_id: 记忆ID
            bookmark_type: 书签类型
            note: 书签注解
            tags: 书签标签
            priority: 优先级
            folders: 放入的收藏夹列表
            metadata: 额外元数据
        """
        with self._lock:
            self._bookmark_counter += 1
            bookmark = Bookmark(
                memory_id=memory_id,
                bookmark_type=bookmark_type,
                note=note,
                tags=tags or [],
                priority=priority,
                metadata=metadata or {},
            )

            if memory_id not in self._bookmarks:
                self._bookmarks[memory_id] = {}
            self._bookmarks[memory_id][bookmark_type.value] = bookmark

            # 添加到收藏夹
            if folders:
                for folder_name in folders:
                    self._add_to_folder(memory_id, folder_name)
            else:
                # 默认添加到对应类型的系统收藏夹
                default_folder = self._get_default_folder(bookmark_type)
                if default_folder:
                    self._add_to_folder(memory_id, default_folder)

            return bookmark

    def remove_bookmark(self, memory_id: str,
                        bookmark_type: Optional[BookmarkType] = None) -> bool:
        """
        移除书签

        Args:
            memory_id: 记忆ID
            bookmark_type: 指定类型（None则移除所有类型）
        """
        with self._lock:
            if memory_id not in self._bookmarks:
                return False

            if bookmark_type:
                removed = self._bookmarks[memory_id].pop(bookmark_type.value, None)
                if removed:
                    if not self._bookmarks[memory_id]:
                        del self._bookmarks[memory_id]
                    return True
                return False
            else:
                # 移除所有类型
                del self._bookmarks[memory_id]
                # 从所有收藏夹中移除
                for folder_name in list(self._memory_folders.get(memory_id, set())):
                    self._remove_from_folder(memory_id, folder_name)
                return True

    def get_bookmark(self, memory_id: str,
                     bookmark_type: Optional[BookmarkType] = None) -> Optional[Bookmark]:
        """获取书签"""
        with self._lock:
            if memory_id not in self._bookmarks:
                return None
            if bookmark_type:
                return self._bookmarks[memory_id].get(bookmark_type.value)
            # 返回第一个书签
            bookmarks = list(self._bookmarks[memory_id].values())
            return bookmarks[0] if bookmarks else None

    def get_all_bookmarks(self, memory_id: str) -> List[Bookmark]:
        """获取记忆的所有书签"""
        with self._lock:
            if memory_id not in self._bookmarks:
                return []
            return list(self._bookmarks[memory_id].values())

    def update_bookmark(self, memory_id: str,
                        bookmark_type: Optional[BookmarkType] = None,
                        note: Optional[str] = None,
                        tags: Optional[List[str]] = None,
                        priority: Optional[int] = None) -> Optional[Bookmark]:
        """更新书签"""
        with self._lock:
            bookmark = self.get_bookmark(memory_id, bookmark_type)
            if not bookmark:
                return None

            if note is not None:
                bookmark.note = note
            if tags is not None:
                bookmark.tags = tags
            if priority is not None:
                bookmark.priority = priority

            bookmark.updated_at = time.time()
            return bookmark

    def is_bookmarked(self, memory_id: str,
                      bookmark_type: Optional[BookmarkType] = None) -> bool:
        """检查记忆是否已收藏"""
        with self._lock:
            if memory_id not in self._bookmarks:
                return False
            if bookmark_type:
                return bookmark_type.value in self._bookmarks[memory_id]
            return len(self._bookmarks[memory_id]) > 0

    def _get_default_folder(self, bookmark_type: BookmarkType) -> Optional[str]:
        """获取书签类型对应的默认收藏夹"""
        mapping = {
            BookmarkType.FAVORITE: "favorites",
            BookmarkType.IMPORTANT: "important",
            BookmarkType.READ_LATER: "read_later",
            BookmarkType.ARCHIVED: "archived",
            BookmarkType.PINNED: "pinned",
        }
        return mapping.get(bookmark_type)

    # ==================== 收藏夹操作 ====================

    def create_folder(self, name: str, description: str = "",
                      parent: Optional[str] = None, icon: str = "📁",
                      color: str = "#3498db",
                      sort_order: Optional[int] = None) -> Folder:
        """
        创建收藏夹

        Args:
            name: 收藏夹名称
            description: 描述
            parent: 父收藏夹
            icon: 图标
            color: 颜色
            sort_order: 排序
        """
        with self._lock:
            if name in self._folders:
                raise ValueError(f"收藏夹 '{name}' 已存在")
            if parent and parent not in self._folders:
                raise ValueError(f"父收藏夹 '{parent}' 不存在")

            folder = Folder(
                name=name,
                folder_type=FolderType.USER,
                description=description,
                parent=parent,
                icon=icon,
                color=color,
                sort_order=sort_order if sort_order is not None else len(self._folders),
            )
            self._folders[name] = folder
            self._folder_memories[name] = set()
            return folder

    def create_smart_folder(self, name: str, rules: Dict,
                            description: str = "", icon: str = "🤖",
                            color: str = "#9b59b6") -> Folder:
        """
        创建智能收藏夹

        Args:
            name: 收藏夹名称
            rules: 规则字典，支持:
                - bookmark_types: [BookmarkType values] - 书签类型过滤
                - tags: [str] - 书签标签过滤（任一匹配）
                - require_all_tags: bool - 是否需要所有标签
                - min_priority: int - 最低优先级
                - created_after: float - 创建时间之后
                - created_before: float - 创建时间之前
                - note_contains: str - 注解包含文本
                - memory_layer: str - 记忆层级过滤
                - limit: int - 最大数量
        """
        with self._lock:
            if name in self._folders:
                raise ValueError(f"收藏夹 '{name}' 已存在")

            folder = Folder(
                name=name,
                folder_type=FolderType.SMART,
                description=description,
                icon=icon,
                color=color,
                smart_rules=rules,
            )
            self._folders[name] = folder
            self._folder_memories[name] = set()

            # 立即计算一次
            self._update_smart_folder(folder)
            return folder

    def delete_folder(self, name: str, cascade: bool = False) -> bool:
        """删除收藏夹"""
        with self._lock:
            folder = self._folders.get(name)
            if not folder:
                return False

            if folder.folder_type == FolderType.SYSTEM:
                raise ValueError("系统预设收藏夹不能删除")

            children = [f for f in self._folders.values() if f.parent == name]
            if children and not cascade:
                raise ValueError(
                    f"收藏夹 '{name}' 有 {len(children)} 个子收藏夹"
                )

            if cascade:
                for child in children:
                    self.delete_folder(child.name, cascade=True)

            # 移除记忆关联
            memory_ids = self._folder_memories.pop(name, set())
            for mid in memory_ids:
                if mid in self._memory_folders:
                    self._memory_folders[mid].discard(name)

            del self._folders[name]
            return True

    def get_folder(self, name: str) -> Optional[Folder]:
        """获取收藏夹"""
        with self._lock:
            return self._folders.get(name)

    def list_folders(self, folder_type: Optional[FolderType] = None,
                     parent: Optional[str] = None,
                     search: Optional[str] = None) -> List[Folder]:
        """列出收藏夹"""
        with self._lock:
            folders = list(self._folders.values())

            if folder_type:
                folders = [f for f in folders if f.folder_type == folder_type]
            if parent is not None:
                folders = [f for f in folders if f.parent == parent]
            if search:
                search_lower = search.lower()
                folders = [f for f in folders if
                           search_lower in f.name.lower() or
                           search_lower in f.description.lower()]

            folders.sort(key=lambda f: f.sort_order)
            return folders

    def rename_folder(self, old_name: str, new_name: str) -> bool:
        """重命名收藏夹"""
        with self._lock:
            folder = self._folders.get(old_name)
            if not folder:
                return False
            if folder.folder_type == FolderType.SYSTEM:
                raise ValueError("系统预设收藏夹不能重命名")
            if new_name in self._folders:
                raise ValueError(f"收藏夹 '{new_name}' 已存在")

            # 更新子收藏夹的父引用
            for f in self._folders.values():
                if f.parent == old_name:
                    f.parent = new_name

            # 更新记忆关联
            memories = self._folder_memories.pop(old_name, set())
            self._folders[new_name] = folder
            self._folders[new_name].name = new_name
            self._folder_memories[new_name] = memories

            for mid in memories:
                if mid in self._memory_folders:
                    self._memory_folders[mid].discard(old_name)
                    self._memory_folders[mid].add(new_name)

            del self._folders[old_name]
            return True

    def _add_to_folder(self, memory_id: str, folder_name: str):
        """将记忆添加到收藏夹"""
        if folder_name not in self._folders:
            return

        if folder_name not in self._folder_memories:
            self._folder_memories[folder_name] = set()
        self._folder_memories[folder_name].add(memory_id)

        if memory_id not in self._memory_folders:
            self._memory_folders[memory_id] = set()
        self._memory_folders[memory_id].add(folder_name)

    def _remove_from_folder(self, memory_id: str, folder_name: str):
        """从收藏夹移除记忆"""
        if folder_name in self._folder_memories:
            self._folder_memories[folder_name].discard(memory_id)
        if memory_id in self._memory_folders:
            self._memory_folders[memory_id].discard(folder_name)

    def add_to_folder(self, memory_id: str, folder_names: List[str]) -> int:
        """将记忆添加到指定收藏夹"""
        with self._lock:
            count = 0
            for name in folder_names:
                if name in self._folders:
                    self._add_to_folder(memory_id, name)
                    count += 1
            return count

    def remove_from_folder(self, memory_id: str, folder_names: List[str]) -> int:
        """从收藏夹移除记忆"""
        with self._lock:
            count = 0
            for name in folder_names:
                self._remove_from_folder(memory_id, name)
                count += 1
            return count

    def get_folder_memories(self, folder_name: str,
                            sort_by: str = "created_at",
                            ascending: bool = False,
                            offset: int = 0,
                            limit: int = 50) -> List[str]:
        """
        获取收藏夹中的记忆ID列表

        Args:
            folder_name: 收藏夹名称
            sort_by: 排序字段 (created_at/updated_at/priority)
            ascending: 是否升序
            offset: 偏移
            limit: 限制数量
        """
        with self._lock:
            folder = self._folders.get(folder_name)
            if not folder:
                return []

            # 智能收藏夹需要更新缓存
            if folder.folder_type == FolderType.SMART:
                self._update_smart_folder(folder)

            memory_ids = list(self._folder_memories.get(folder_name, set()))

            # 排序
            if sort_by == "priority":
                memory_ids.sort(
                    key=lambda mid: self._get_bookmark_priority(mid),
                    reverse=not ascending
                )
            elif sort_by == "updated_at":
                memory_ids.sort(
                    key=lambda mid: self._get_bookmark_updated(mid),
                    reverse=not ascending
                )
            else:  # created_at
                memory_ids.sort(
                    key=lambda mid: self._get_bookmark_created(mid),
                    reverse=not ascending
                )

            return memory_ids[offset:offset + limit]

    def _get_bookmark_priority(self, memory_id: str) -> int:
        bookmarks = self._bookmarks.get(memory_id, {})
        if not bookmarks:
            return 0
        return max(b.priority for b in bookmarks.values())

    def _get_bookmark_created(self, memory_id: str) -> float:
        bookmarks = self._bookmarks.get(memory_id, {})
        if not bookmarks:
            return 0
        return min(b.created_at for b in bookmarks.values())

    def _get_bookmark_updated(self, memory_id: str) -> float:
        bookmarks = self._bookmarks.get(memory_id, {})
        if not bookmarks:
            return 0
        return max(b.updated_at for b in bookmarks.values())

    # ==================== 智能收藏夹 ====================

    def _update_smart_folder(self, folder: Folder):
        """更新智能收藏夹的缓存"""
        rules = folder.smart_rules
        matched = set()

        for memory_id, type_bookmarks in self._bookmarks.items():
            bookmarks = list(type_bookmarks.values())
            if not bookmarks:
                continue

            bookmark = bookmarks[0]  # 取第一个书签

            # 类型过滤
            type_filter = rules.get("bookmark_types")
            if type_filter:
                if not any(b.bookmark_type.value in type_filter for b in bookmarks):
                    continue

            # 标签过滤
            tag_filter = rules.get("tags")
            if tag_filter:
                all_tags = set()
                for b in bookmarks:
                    all_tags.update(b.tags)
                require_all = rules.get("require_all_tags", False)
                if require_all:
                    if not all(t in all_tags for t in tag_filter):
                        continue
                else:
                    if not any(t in all_tags for t in tag_filter):
                        continue

            # 优先级过滤
            min_priority = rules.get("min_priority")
            if min_priority is not None:
                if not any(b.priority >= min_priority for b in bookmarks):
                    continue

            # 时间过滤
            created_after = rules.get("created_after")
            if created_after is not None:
                if not any(b.created_at >= created_after for b in bookmarks):
                    continue

            created_before = rules.get("created_before")
            if created_before is not None:
                if not any(b.created_at <= created_before for b in bookmarks):
                    continue

            # 注解过滤
            note_contains = rules.get("note_contains")
            if note_contains:
                if not any(note_contains.lower() in b.note.lower() for b in bookmarks):
                    continue

            matched.add(memory_id)

        # 限制数量
        limit = rules.get("limit")
        if limit and len(matched) > limit:
            # 按优先级排序后截断
            sorted_ids = sorted(
                matched,
                key=lambda mid: self._get_bookmark_priority(mid),
                reverse=True
            )
            matched = set(sorted_ids[:limit])

        folder.smart_rules_cache = matched
        folder.smart_rules_updated = time.time()

    def refresh_smart_folders(self) -> int:
        """刷新所有智能收藏夹"""
        with self._lock:
            count = 0
            for folder in self._folders.values():
                if folder.folder_type == FolderType.SMART:
                    self._update_smart_folder(folder)
                    count += 1
            return count

    # ==================== 搜索与查询 ====================

    def search_bookmarks(self, query: str,
                         bookmark_type: Optional[BookmarkType] = None,
                         folder: Optional[str] = None,
                         tags: Optional[List[str]] = None,
                         sort_by: str = "created_at",
                         ascending: bool = False,
                         offset: int = 0,
                         limit: int = 50) -> Tuple[List[Bookmark], int]:
        """
        搜索书签

        Args:
            query: 搜索文本（匹配注解和标签）
            bookmark_type: 类型过滤
            folder: 收藏夹过滤
            tags: 标签过滤
            sort_by: 排序字段
            ascending: 升序
            offset: 偏移
            limit: 限制

        Returns:
            (书签列表, 总数)
        """
        with self._lock:
            results = []

            for memory_id, type_bookmarks in self._bookmarks.items():
                for bt, bookmark in type_bookmarks.items():
                    # 类型过滤
                    if bookmark_type and bookmark.bookmark_type != bookmark_type:
                        continue

                    # 收藏夹过滤
                    if folder:
                        if memory_id not in self._folder_memories.get(folder, set()):
                            continue

                    # 标签过滤
                    if tags:
                        if not any(t in bookmark.tags for t in tags):
                            continue

                    # 文本搜索
                    if query:
                        query_lower = query.lower()
                        if not (query_lower in bookmark.note.lower() or
                                any(query_lower in t.lower() for t in bookmark.tags) or
                                query_lower in memory_id.lower()):
                            continue

                    results.append(bookmark)

            # 排序
            if sort_by == "priority":
                results.sort(key=lambda b: b.priority, reverse=not ascending)
            elif sort_by == "updated_at":
                results.sort(key=lambda b: b.updated_at, reverse=not ascending)
            else:
                results.sort(key=lambda b: b.created_at, reverse=not ascending)

            total = len(results)
            return results[offset:offset + limit], total

    def get_recent_bookmarks(self, limit: int = 20) -> List[Bookmark]:
        """获取最近添加的书签"""
        results, _ = self.search_bookmarks(
            "", sort_by="created_at", ascending=False, limit=limit
        )
        return results

    def get_pinned_bookmarks(self) -> List[Bookmark]:
        """获取所有置顶书签"""
        results, _ = self.search_bookmarks(
            "", bookmark_type=BookmarkType.PINNED,
            sort_by="priority", ascending=False
        )
        return results

    # ==================== 统计 ====================

    def get_stats(self) -> CollectionStats:
        """获取收藏统计信息"""
        with self._lock:
            stats = CollectionStats()

            # 按类型统计
            type_counts: Dict[str, int] = {}
            for memory_id, type_bookmarks in self._bookmarks.items():
                for bt, bookmark in type_bookmarks.items():
                    type_counts[bookmark.bookmark_type.value] = \
                        type_counts.get(bookmark.bookmark_type.value, 0) + 1

            stats.total_bookmarks = sum(type_counts.values())
            stats.by_type = type_counts
            stats.total_folders = len(self._folders)

            # 收藏夹大小
            for name, memories in self._folder_memories.items():
                stats.folder_sizes[name] = len(memories)

            # 最近书签
            all_bookmarks = []
            for type_bookmarks in self._bookmarks.values():
                all_bookmarks.extend(type_bookmarks.values())
            all_bookmarks.sort(key=lambda b: b.created_at, reverse=True)
            stats.recent_bookmarks = [b.to_dict() for b in all_bookmarks[:10]]

            # 最多书签的记忆（即有最多书签类型的记忆）
            multi_bookmarked = [
                (mid, len(tbs))
                for mid, tbs in self._bookmarks.items()
                if len(tbs) > 1
            ]
            multi_bookmarked.sort(key=lambda x: x[1], reverse=True)
            stats.most_bookmarked = [
                {"memory_id": mid, "bookmark_count": count}
                for mid, count in multi_bookmarked[:5]
            ]

            return stats

    def get_memory_folders(self, memory_id: str) -> List[str]:
        """获取记忆所在的收藏夹列表"""
        with self._lock:
            return list(self._memory_folders.get(memory_id, set()))

    # ==================== 批量操作 ====================

    def batch_add_bookmarks(self, memory_ids: List[str],
                            bookmark_type: BookmarkType = BookmarkType.FAVORITE,
                            folder: Optional[str] = None) -> Dict:
        """批量添加书签"""
        with self._lock:
            success = 0
            failed = 0
            for mid in memory_ids:
                try:
                    self.add_bookmark(
                        mid, bookmark_type=bookmark_type,
                        folders=[folder] if folder else None
                    )
                    success += 1
                except Exception:
                    failed += 1
            return {
                "total": len(memory_ids),
                "success": success,
                "failed": failed,
            }

    def batch_remove_bookmarks(self, memory_ids: List[str]) -> int:
        """批量移除书签"""
        with self._lock:
            count = 0
            for mid in memory_ids:
                if self.remove_bookmark(mid):
                    count += 1
            return count

    def export_bookmarks(self) -> Dict:
        """导出书签数据"""
        with self._lock:
            bookmarks_data = {}
            for mid, type_bookmarks in self._bookmarks.items():
                bookmarks_data[mid] = {
                    bt: b.to_dict() for bt, b in type_bookmarks.items()
                }

            folders_data = {
                name: folder.to_dict() for name, folder in self._folders.items()
            }

            return {
                "bookmarks": bookmarks_data,
                "folders": folders_data,
                "folder_memories": {
                    name: list(mids)
                    for name, mids in self._folder_memories.items()
                },
                "statistics": {
                    "total_bookmarks": sum(
                        len(tbs) for tbs in self._bookmarks.values()
                    ),
                    "total_folders": len(self._folders),
                    "tagged_memories": len(self._bookmarks),
                },
            }

    def get_summary(self) -> Dict:
        """获取收藏系统摘要"""
        with self._lock:
            stats = self.get_stats()
            return {
                "total_bookmarks": stats.total_bookmarks,
                "by_type": stats.by_type,
                "total_folders": stats.total_folders,
                "user_folders": sum(
                    1 for f in self._folders.values()
                    if f.folder_type == FolderType.USER
                ),
                "smart_folders": sum(
                    1 for f in self._folders.values()
                    if f.folder_type == FolderType.SMART
                ),
                "bookmarked_memories": len(self._bookmarks),
            }


# ==================== 全局单例 ====================

_global_bookmark_manager: Optional[BookmarkManager] = None
_global_bookmark_manager_lock = threading.Lock()


def get_bookmark_manager() -> BookmarkManager:
    """获取全局书签管理器实例"""
    global _global_bookmark_manager
    if _global_bookmark_manager is None:
        with _global_bookmark_manager_lock:
            if _global_bookmark_manager is None:
                _global_bookmark_manager = BookmarkManager()
    return _global_bookmark_manager
