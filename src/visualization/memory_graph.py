#!/usr/bin/env python3
"""
记忆关联图谱 - 阶段119-121
生成记忆之间的关系图谱，支持可视化展示
"""

import json
from typing import Dict, List, Any, Set, Tuple
from collections import defaultdict
from dataclasses import dataclass, asdict


@dataclass
class GraphNode:
    """图谱节点"""
    id: str
    label: str
    type: str  # "memory" | "entity" | "keyword"
    size: int = 1
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


@dataclass
class GraphEdge:
    """图谱边"""
    source: str
    target: str
    label: str
    weight: float = 1.0


class MemoryGraphBuilder:
    """
    记忆图谱构建器
    
    从记忆数据构建关联图谱，支持多种关联类型
    """
    
    def __init__(self):
        self.nodes: Dict[str, GraphNode] = {}
        self.edges: List[GraphEdge] = []
    
    def add_memory_node(self, memory_id: str, content: str, **metadata):
        """添加记忆节点"""
        # 截断内容作为标签
        label = content[:30] + "..." if len(content) > 30 else content
        self.nodes[memory_id] = GraphNode(
            id=memory_id,
            label=label,
            type="memory",
            metadata=metadata
        )
    
    def add_entity_node(self, entity: str, entity_type: str = "entity"):
        """添加实体节点"""
        node_id = f"entity:{entity}"
        if node_id not in self.nodes:
            self.nodes[node_id] = GraphNode(
                id=node_id,
                label=entity,
                type=entity_type
            )
    
    def add_keyword_node(self, keyword: str):
        """添加关键词节点"""
        node_id = f"keyword:{keyword}"
        if node_id not in self.nodes:
            self.nodes[node_id] = GraphNode(
                id=node_id,
                label=keyword,
                type="keyword"
            )
    
    def add_edge(self, source: str, target: str, label: str = "related", weight: float = 1.0):
        """添加边"""
        self.edges.append(GraphEdge(
            source=source,
            target=target,
            label=label,
            weight=weight
        ))
    
    def build_from_memories(self, memories: List[Dict[str, Any]]):
        """
        从记忆列表构建图谱
        
        Args:
            memories: 记忆列表，每项包含id、content等
        """
        # 添加记忆节点
        for mem in memories:
            mem_id = mem.get("memory_id", mem.get("id", str(id(mem))))
            content = mem.get("content", "")
            self.add_memory_node(mem_id, content, **mem)
        
        # 提取关键词并建立关联
        for i, mem1 in enumerate(memories):
            mem1_id = mem1.get("memory_id", mem1.get("id", str(id(mem1))))
            content1 = mem1.get("content", "")
            
            # 提取关键词
            keywords1 = self._extract_keywords(content1)
            
            # 添加关键词节点和边
            for kw in keywords1:
                self.add_keyword_node(kw)
                self.add_edge(mem1_id, f"keyword:{kw}", "contains", 0.8)
            
            # 与其他记忆建立关联
            for j, mem2 in enumerate(memories[i+1:], i+1):
                mem2_id = mem2.get("memory_id", mem2.get("id", str(id(mem2))))
                content2 = mem2.get("content", "")
                
                similarity = self._calculate_similarity(content1, content2)
                if similarity > 0.3:  # 相似度阈值
                    self.add_edge(mem1_id, mem2_id, "similar", similarity)
    
    def _extract_keywords(self, content: str) -> List[str]:
        """提取关键词（简化版）"""
        # 简单的关键词提取：2-4个字的词组
        keywords = []
        for i in range(len(content) - 1):
            for length in [2, 3, 4]:
                if i + length <= len(content):
                    word = content[i:i+length]
                    # 过滤纯数字和纯标点
                    if any(c.isalpha() or '\u4e00' <= c <= '\u9fff' for c in word):
                        keywords.append(word)
        # 去重并限制数量
        return list(dict.fromkeys(keywords))[:5]
    
    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """计算文本相似度（Jaccard系数）"""
        set1 = set(text1)
        set2 = set(text2)
        if not set1 or not set2:
            return 0.0
        intersection = len(set1 & set2)
        union = len(set1 | set2)
        return intersection / union if union > 0 else 0.0
    
    def to_cytoscape_format(self) -> Dict[str, Any]:
        """
        转换为Cytoscape.js格式
        
        适用于前端可视化库
        """
        elements = []
        
        # 节点
        for node in self.nodes.values():
            elements.append({
                "data": {
                    "id": node.id,
                    "label": node.label,
                    "type": node.type,
                    "size": node.size,
                    **node.metadata
                }
            })
        
        # 边
        for edge in self.edges:
            elements.append({
                "data": {
                    "source": edge.source,
                    "target": edge.target,
                    "label": edge.label,
                    "weight": edge.weight
                }
            })
        
        return {"elements": elements}
    
    def to_d3_format(self) -> Dict[str, Any]:
        """
        转换为D3.js格式
        """
        nodes = []
        for node in self.nodes.values():
            nodes.append({
                "id": node.id,
                "name": node.label,
                "group": node.type,
                "size": node.size
            })
        
        links = []
        for edge in self.edges:
            links.append({
                "source": edge.source,
                "target": edge.target,
                "value": edge.weight
            })
        
        return {"nodes": nodes, "links": links}
    
    def to_gexf_format(self) -> str:
        """
        转换为GEXF格式（Gephi兼容）
        """
        lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<gexf xmlns="http://www.gexf.net/1.2draft" version="1.2">',
            '  <graph mode="static" defaultedgetype="undirected">',
            '    <nodes>'
        ]
        
        for node in self.nodes.values():
            lines.append(f'      <node id="{node.id}" label="{node.label}" />')
        
        lines.append('    </nodes>')
        lines.append('    <edges>')
        
        for i, edge in enumerate(self.edges):
            lines.append(
                f'      <edge id="{i}" source="{edge.source}" target="{edge.target}" '
                f'weight="{edge.weight}" />'
            )
        
        lines.extend([
            '    </edges>',
            '  </graph>',
            '</gexf>'
        ])
        
        return '\n'.join(lines)
    
    def export_to_file(self, filepath: str, format: str = "json"):
        """
        导出图谱到文件
        
        Args:
            filepath: 输出文件路径
            format: 输出格式 (json/cytoscape/d3/gexf)
        """
        if format == "json":
            data = {
                "nodes": [asdict(n) for n in self.nodes.values()],
                "edges": [asdict(e) for e in self.edges]
            }
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        
        elif format == "cytoscape":
            data = self.to_cytoscape_format()
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        
        elif format == "d3":
            data = self.to_d3_format()
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        
        elif format == "gexf":
            content = self.to_gexf_format()
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
    
    def get_stats(self) -> Dict[str, int]:
        """获取图谱统计"""
        return {
            "nodes": len(self.nodes),
            "edges": len(self.edges),
            "memory_nodes": sum(1 for n in self.nodes.values() if n.type == "memory"),
            "keyword_nodes": sum(1 for n in self.nodes.values() if n.type == "keyword"),
        }


class MemoryGraphVisualizer:
    """
    记忆图谱可视化器
    
    提供图谱生成和导出功能
    """
    
    def __init__(self, memory_system):
        self.memory_system = memory_system
        self.builder = MemoryGraphBuilder()
    
    def visualize_task(self, task_id: str) -> Dict[str, Any]:
        """
        为指定任务生成记忆图谱
        
        Args:
            task_id: 任务标识
        
        Returns:
            图谱数据（Cytoscape格式）
        """
        # 召回该任务的所有记忆
        memories = self.memory_system.recall("", task_id=task_id, top_k=1000)
        
        # 构建图谱
        self.builder = MemoryGraphBuilder()  # 重置
        self.builder.build_from_memories(memories)
        
        return self.builder.to_cytoscape_format()
    
    def export_graph(self, filepath: str, format: str = "cytoscape"):
        """导出当前图谱"""
        self.builder.export_to_file(filepath, format)
