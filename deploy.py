#!/usr/bin/env python3
"""
Agent可靠记忆系统 - 一键部署脚本（阶段97）
"""

import os
import sys
import subprocess


def check_python_version():
    """检查Python版本"""
    version = sys.version_info
    if version.major < 3 or (version.major == 3 and version.minor < 8):
        print("[错误] 需要Python 3.8+")
        return False
    print(f"[OK] Python {version.major}.{version.minor}.{version.micro}")
    return True


def install_dependencies():
    """安装依赖"""
    req_file = os.path.join(os.path.dirname(__file__), "requirements.txt")
    if not os.path.exists(req_file):
        print("[警告] requirements.txt 不存在，跳过依赖安装")
        return True
    
    print("[安装] 正在安装依赖...")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "-r", req_file, "--break-system-packages"],
        capture_output=True, text=True
    )
    
    if result.returncode == 0:
        print("[OK] 依赖安装成功")
        return True
    else:
        print(f"[错误] 依赖安装失败: {result.stderr}")
        return False


def create_directories():
    """创建必要的目录"""
    dirs = [
        "data/l1",
        "data/l2",
        "data/l3",
        "logs",
    ]
    
    base_dir = os.path.dirname(__file__)
    for d in dirs:
        path = os.path.join(base_dir, d)
        os.makedirs(path, exist_ok=True)
        print(f"[OK] 目录已创建: {d}")
    
    return True


def verify_structure():
    """验证项目结构"""
    base_dir = os.path.dirname(__file__)
    
    required_files = [
        "api/memory_system.py",
        "src/preprocessing/filter.py",
        "src/memory/router.py",
        "src/recall/engine.py",
        "src/governance/governor.py",
        "src/utils/logger.py",
        "config/system.yaml",
    ]
    
    all_ok = True
    for f in required_files:
        path = os.path.join(base_dir, f)
        if os.path.exists(path):
            print(f"[OK] {f}")
        else:
            print(f"[缺失] {f}")
            all_ok = False
    
    return all_ok


def run_quick_test():
    """运行快速验证测试"""
    print("\n[测试] 运行快速验证...")
    
    try:
        sys.path.insert(0, os.path.dirname(__file__))
        from api.memory_system import AgentMemorySystem
        
        system = AgentMemorySystem()
        
        # 存储测试
        result = system.remember("部署验证测试内容", task_id="deploy_test")
        if not result["success"]:
            print("[错误] 记忆存储失败")
            return False
        
        # 召回测试
        results = system.recall("验证测试", task_id="deploy_test")
        
        # 健康检查
        health = system.health_check()
        print(f"[OK] 系统状态: {health['status']}")
        
        # 清理
        system.forget(result["memory_id"], "deploy_test")
        
        print("[OK] 快速验证通过")
        return True
        
    except Exception as e:
        print(f"[错误] 快速验证失败: {e}")
        return False


def main():
    """主部署流程"""
    print("=" * 50)
    print("Agent可靠记忆系统 - 部署脚本")
    print("=" * 50)
    
    steps = [
        ("检查Python版本", check_python_version),
        ("安装依赖", install_dependencies),
        ("创建目录", create_directories),
        ("验证项目结构", verify_structure),
        ("快速验证测试", run_quick_test),
    ]
    
    results = {}
    for name, func in steps:
        print(f"\n>>> {name}")
        results[name] = func()
    
    # 汇总
    print("\n" + "=" * 50)
    print("部署结果汇总")
    print("=" * 50)
    
    all_passed = all(results.values())
    for name, passed in results.items():
        status = "通过" if passed else "失败"
        print(f"  [{status}] {name}")
    
    if all_passed:
        print("\n部署成功！系统已就绪。")
        print("使用方式: from api.memory_system import AgentMemorySystem")
    else:
        print("\n部署存在问题，请检查上述失败项。")
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
