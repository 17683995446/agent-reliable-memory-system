#!/usr/bin/env python3
"""
Agent可靠记忆系统 - 使用示例（阶段98）
演示系统核心功能的完整使用流程
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.memory_system import AgentMemorySystem


def example_basic_usage():
    """示例1: 基本使用"""
    print("=" * 50)
    print("示例1: 基本使用 - 记忆存储与召回")
    print("=" * 50)
    
    system = AgentMemorySystem()
    task_id = "example_basic"
    
    # 存储记忆
    memories = [
        "用户是一名Python开发者，有5年经验",
        "用户偏好使用VS Code编辑器",
        "用户正在开发一个机器学习项目",
    ]
    
    for mem in memories:
        result = system.remember(mem, task_id=task_id)
        print(f"  存储: {mem[:20]}... -> {result['message']}")
    
    # 召回记忆
    print(f"\n  召回 'Python开发':")
    results = system.recall("Python开发", task_id=task_id, top_k=3)
    for r in results:
        print(f"    - {r.get('content', r)[:50]}...")
    
    print()


def example_privacy_control():
    """示例2: 隐私控制"""
    print("=" * 50)
    print("示例2: 隐私控制 - 多用户记忆隔离")
    print("=" * 50)
    
    system = AgentMemorySystem()
    
    # 用户A存储私有记忆
    result = system.remember(
        "用户A的私密信息",
        task_id="privacy_example",
        visibility="private",
        owner_id="user_a"
    )
    mem_id = result["memory_id"]
    print(f"  用户A存储私有记忆: {result['message']}")
    
    # 用户A存储公开记忆
    result = system.remember(
        "这是一条公开的共享知识",
        task_id="privacy_example",
        visibility="public",
        owner_id="user_a"
    )
    print(f"  用户A存储公开记忆: {result['message']}")
    
    # 共享私有记忆给用户B
    share_result = system.share_memory(mem_id, "user_a", "user_b")
    print(f"  用户A共享记忆给用户B: {share_result.get('message', '')}")
    
    print()


def example_task_review():
    """示例3: 任务回顾"""
    print("=" * 50)
    print("示例3: 任务回顾 - 提取规则与摘要")
    print("=" * 50)
    
    system = AgentMemorySystem()
    task_id = "review_example"
    
    # 模拟一个对话任务的记忆
    conversation_memories = [
        "用户询问了如何优化数据库查询性能",
        "我建议用户添加索引并优化SQL语句",
        "用户反馈优化后查询速度提升了10倍",
        "用户还问了关于缓存策略的问题",
        "我推荐了Redis作为缓存方案",
    ]
    
    for mem in conversation_memories:
        system.remember(mem, task_id=task_id)
    
    print(f"  已存储 {len(conversation_memories)} 条对话记忆")
    
    # 任务回顾
    review = system.review_task(task_id)
    print(f"  回顾结果: {review}")
    
    print()


def example_health_check():
    """示例4: 系统健康检查"""
    print("=" * 50)
    print("示例4: 系统健康检查")
    print("=" * 50)
    
    system = AgentMemorySystem()
    
    # 健康检查
    health = system.health_check()
    print(f"  系统状态: {health['status']}")
    for module, status in health['checks'].items():
        print(f"    {module}: {status}")
    
    # 系统统计
    stats = system.get_stats()
    print(f"\n  系统统计:")
    print(f"    初始化时间: {stats['initialized_at']}")
    print(f"    总存储量: {stats['total_stored']}")
    print(f"    总召回量: {stats['total_recalled']}")
    
    print()


def example_config_management():
    """示例5: 配置管理"""
    print("=" * 50)
    print("示例5: 配置管理")
    print("=" * 50)
    
    system = AgentMemorySystem()
    
    # 读取配置
    top_k = system.get_config("recall.top_k", 5)
    print(f"  当前 top_k: {top_k}")
    
    # 修改配置
    system.set_config("recall.top_k", 10)
    new_top_k = system.get_config("recall.top_k")
    print(f"  修改后 top_k: {new_top_k}")
    
    # 恢复默认
    system.set_config("recall.top_k", 5)
    print(f"  已恢复默认值")
    
    print()


def main():
    """运行所有示例"""
    print("\n")
    print("*" * 50)
    print("  Agent可靠记忆系统 - 使用示例")
    print("*" * 50)
    print()
    
    example_basic_usage()
    example_privacy_control()
    example_task_review()
    example_health_check()
    example_config_management()
    
    print("*" * 50)
    print("  所有示例运行完毕")
    print("*" * 50)


if __name__ == "__main__":
    main()
