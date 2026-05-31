#!/usr/bin/env python3
"""
记忆摘要生成 - 阶段149-151
长文本摘要与关键信息提取
"""

import re
from typing import Dict, List, Any, Optional
from dataclasses import dataclass


@dataclass
class SummaryResult:
    """摘要结果"""
    original_length: int
    summary_length: int
    summary: str
    key_points: List[str]
    entities: List[str]


class MemorySummarizer:
    """
    记忆摘要器
    
    对长文本记忆进行摘要：
    - 提取关键句子
    - 识别实体
    - 生成简洁摘要
    """

    def __init__(self, max_summary_length: int = 200):
        self.max_summary_length = max_summary_length

    def summarize(self, content: str) -> SummaryResult:
        """
        生成摘要
        
        Args:
            content: 原始内容
        
        Returns:
            摘要结果
        """
        original_length = len(content)

        # 提取关键句子
        key_sentences = self._extract_key_sentences(content)

        # 提取实体
        entities = self._extract_entities(content)

        # 生成摘要
        summary = self._generate_summary(key_sentences, content)

        # 提取关键点
        key_points = self._extract_key_points(content)

        return SummaryResult(
            original_length=original_length,
            summary_length=len(summary),
            summary=summary,
            key_points=key_points,
            entities=entities
        )

    def _extract_key_sentences(self, content: str) -> List[str]:
        """提取关键句子"""
        # 按句号、问号、感叹号分割
        sentences = re.split(r'[。！？.!?]', content)
        sentences = [s.strip() for s in sentences if s.strip()]

        if not sentences:
            return []

        # 评分：长度适中、包含关键词的句子得分更高
        scored = []
        keywords = ["重要", "关键", "核心", "主要", "必须", "需要", "问题", "解决"]

        for sent in sentences:
            score = 0
            # 长度评分（20-100字符最佳）
            length = len(sent)
            if 20 <= length <= 100:
                score += 2
            elif length > 100:
                score += 1

            # 关键词评分
            for kw in keywords:
                if kw in sent:
                    score += 2

            # 数字评分（包含具体数据）
            if re.search(r'\d+', sent):
                score += 1

            scored.append((sent, score))

        # 返回得分最高的句子
        scored.sort(key=lambda x: x[1], reverse=True)
        return [s for s, _ in scored[:5]]

    def _extract_entities(self, content: str) -> List[str]:
        """提取实体（简化版）"""
        entities = []

        # 提取中文人名模式（2-4个字的姓名）
        name_pattern = r'[\u4e00-\u9fa5]{2,4}(?=说|认为|表示|指出|提到)'
        names = re.findall(name_pattern, content)
        entities.extend(names[:5])

        # 提取数字+单位
        number_pattern = r'\d+(?:\.\d+)?(?:个|次|天|小时|分钟|秒|年|月|周|元|万|亿|%|%)'
        numbers = re.findall(number_pattern, content)
        entities.extend(numbers[:5])

        # 提取专有名词（大写字母开头）
        proper_pattern = r'[A-Z][a-zA-Z]+'
        proper = re.findall(proper_pattern, content)
        entities.extend(proper[:5])

        return list(dict.fromkeys(entities))[:10]  # 去重保留顺序

    def _generate_summary(self, key_sentences: List[str], content: str) -> str:
        """生成摘要"""
        if not key_sentences:
            # 无关键句子，截取前N个字符
            return content[:self.max_summary_length]

        # 拼接关键句子
        summary = "。".join(key_sentences[:3])
        if len(summary) > self.max_summary_length:
            summary = summary[:self.max_summary_length] + "..."

        return summary

    def _extract_key_points(self, content: str) -> List[str]:
        """提取关键点"""
        points = []

        # 查找列表项（以数字、字母、符号开头）
        list_patterns = [
            r'[1-9][\.、．]\s*([^\n]+)',  # 数字列表
            r'[a-zA-Z][\.、．]\s*([^\n]+)',  # 字母列表
            r'[•·\-－]\s*([^\n]+)',  # 符号列表
        ]

        for pattern in list_patterns:
            matches = re.findall(pattern, content)
            points.extend(matches[:3])

        # 查找"关键点："等引导词后的内容
        guide_patterns = [
            r'关键点[：:]\s*([^\n]+)',
            r'要点[：:]\s*([^\n]+)',
            r'重点[：:]\s*([^\n]+)',
        ]

        for pattern in guide_patterns:
            matches = re.findall(pattern, content)
            points.extend(matches[:2])

        return [p.strip()[:50] for p in points if p.strip()][:5]

    def batch_summarize(
        self,
        contents: List[str],
        min_length: int = 100
    ) -> List[SummaryResult]:
        """
        批量摘要

        Args:
            contents: 内容列表
            min_length: 最小长度（小于此长度不摘要）

        Returns:
            摘要结果列表
        """
        results = []
        for content in contents:
            if len(content) < min_length:
                # 短文本不摘要
                results.append(SummaryResult(
                    original_length=len(content),
                    summary_length=len(content),
                    summary=content,
                    key_points=[],
                    entities=[]
                ))
            else:
                results.append(self.summarize(content))
        return results

    def get_stats(self, result: SummaryResult) -> Dict[str, Any]:
        """获取摘要统计"""
        compression_ratio = (
            (result.original_length - result.summary_length) / result.original_length * 100
            if result.original_length > 0 else 0
        )
        return {
            "original_length": result.original_length,
            "summary_length": result.summary_length,
            "compression_ratio": f"{compression_ratio:.1f}%",
            "key_points_count": len(result.key_points),
            "entities_count": len(result.entities),
        }
