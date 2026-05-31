#!/usr/bin/env python3
"""
Web API服务器 - 阶段101-103
基于FastAPI的HTTP RESTful API接口
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime
import uvicorn

try:
    from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    print("[警告] FastAPI未安装，将使用Flask作为备选")
    from flask import Flask, request, jsonify

from api.memory_system import AgentMemorySystem


# 数据模型
class RememberRequest(BaseModel):
    """存储记忆请求"""
    content: str = Field(..., min_length=1, max_length=10000, description="记忆内容")
    task_id: str = Field(..., min_length=1, max_length=100, description="任务标识")
    visibility: str = Field(default="private", description="可见性: public/private/shared")
    owner_id: Optional[str] = Field(default=None, description="所有者ID")


class RecallRequest(BaseModel):
    """召回记忆请求"""
    query: str = Field(..., min_length=1, max_length=1000, description="查询内容")
    task_id: str = Field(..., min_length=1, max_length=100, description="任务标识")
    top_k: int = Field(default=5, ge=1, le=50, description="返回数量上限")
    user_id: Optional[str] = Field(default=None, description="用户ID（用于隐私过滤）")


class ForgetRequest(BaseModel):
    """删除记忆请求"""
    memory_id: str = Field(..., description="记忆ID")
    task_id: str = Field(..., description="任务标识")


class ShareRequest(BaseModel):
    """共享记忆请求"""
    memory_id: str = Field(..., description="记忆ID")
    owner_id: str = Field(..., description="所有者ID")
    target_user_id: str = Field(..., description="目标用户ID")


class APIResponse(BaseModel):
    """统一API响应"""
    success: bool
    data: Optional[Any] = None
    message: str
    timestamp: str


# 全局系统实例
_memory_system: Optional[AgentMemorySystem] = None


def get_memory_system() -> AgentMemorySystem:
    """获取或创建记忆系统实例"""
    global _memory_system
    if _memory_system is None:
        _memory_system = AgentMemorySystem()
    return _memory_system


if FASTAPI_AVAILABLE:
    # FastAPI实现
    app = FastAPI(
        title="Agent可靠记忆系统 API",
        description="基于第一性原理的Agent记忆管理HTTP API",
        version="1.0.0"
    )
    
    # CORS中间件
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    @app.get("/")
    async def root():
        """根路径 - 服务信息"""
        return {
            "name": "Agent可靠记忆系统",
            "version": "1.0.0",
            "status": "running"
        }
    
    @app.get("/health")
    async def health_check():
        """健康检查"""
        system = get_memory_system()
        health = system.health_check()
        return APIResponse(
            success=health["status"] == "healthy",
            data=health,
            message="系统健康" if health["status"] == "healthy" else "系统异常",
            timestamp=datetime.now().isoformat()
        )
    
    @app.post("/remember", response_model=APIResponse)
    async def remember(request: RememberRequest):
        """
        存储记忆
        
        - **content**: 记忆内容
        - **task_id**: 任务标识
        - **visibility**: 可见性 (public/private/shared)
        - **owner_id**: 所有者ID（可选）
        """
        try:
            system = get_memory_system()
            result = system.remember(
                content=request.content,
                task_id=request.task_id,
                visibility=request.visibility,
                owner_id=request.owner_id
            )
            return APIResponse(
                success=result["success"],
                data=result,
                message=result.get("message", "操作完成"),
                timestamp=datetime.now().isoformat()
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.post("/recall", response_model=APIResponse)
    async def recall(request: RecallRequest):
        """
        召回记忆
        
        - **query**: 查询内容
        - **task_id**: 任务标识
        - **top_k**: 返回数量上限
        - **user_id**: 用户ID（可选，用于隐私过滤）
        """
        try:
            system = get_memory_system()
            results = system.recall(
                query=request.query,
                task_id=request.task_id,
                top_k=request.top_k,
                user_id=request.user_id
            )
            return APIResponse(
                success=True,
                data={"results": results, "count": len(results)},
                message=f"召回{len(results)}条记忆",
                timestamp=datetime.now().isoformat()
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.post("/forget", response_model=APIResponse)
    async def forget(request: ForgetRequest):
        """删除记忆"""
        try:
            system = get_memory_system()
            result = system.forget(request.memory_id, request.task_id)
            return APIResponse(
                success=result["success"],
                data=result,
                message=result.get("message", "操作完成"),
                timestamp=datetime.now().isoformat()
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.post("/share", response_model=APIResponse)
    async def share(request: ShareRequest):
        """共享记忆"""
        try:
            system = get_memory_system()
            result = system.share_memory(
                request.memory_id,
                request.owner_id,
                request.target_user_id
            )
            return APIResponse(
                success=result.get("success", False),
                data=result,
                message=result.get("message", "操作完成"),
                timestamp=datetime.now().isoformat()
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.get("/stats")
    async def get_stats():
        """获取系统统计信息"""
        try:
            system = get_memory_system()
            stats = system.get_stats()
            return APIResponse(
                success=True,
                data=stats,
                message="统计信息获取成功",
                timestamp=datetime.now().isoformat()
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.post("/review/{task_id}")
    async def review_task(task_id: str):
        """任务回顾"""
        try:
            system = get_memory_system()
            result = system.review_task(task_id)
            return APIResponse(
                success=True,
                data=result,
                message="任务回顾完成",
                timestamp=datetime.now().isoformat()
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

else:
    # Flask备选实现
    app = Flask(__name__)
    
    @app.route('/')
    def root():
        return jsonify({
            "name": "Agent可靠记忆系统",
            "version": "1.0.0",
            "status": "running",
            "mode": "flask"
        })
    
    @app.route('/health')
    def health_check():
        system = get_memory_system()
        health = system.health_check()
        return jsonify({
            "success": health["status"] == "healthy",
            "data": health,
            "message": "系统健康" if health["status"] == "healthy" else "系统异常",
            "timestamp": datetime.now().isoformat()
        })
    
    @app.route('/remember', methods=['POST'])
    def remember():
        data = request.get_json()
        system = get_memory_system()
        result = system.remember(
            content=data.get('content'),
            task_id=data.get('task_id'),
            visibility=data.get('visibility', 'private'),
            owner_id=data.get('owner_id')
        )
        return jsonify({
            "success": result["success"],
            "data": result,
            "message": result.get("message", "操作完成"),
            "timestamp": datetime.now().isoformat()
        })
    
    @app.route('/recall', methods=['POST'])
    def recall():
        data = request.get_json()
        system = get_memory_system()
        results = system.recall(
            query=data.get('query'),
            task_id=data.get('task_id'),
            top_k=data.get('top_k', 5),
            user_id=data.get('user_id')
        )
        return jsonify({
            "success": True,
            "data": {"results": results, "count": len(results)},
            "message": f"召回{len(results)}条记忆",
            "timestamp": datetime.now().isoformat()
        })
    
    @app.route('/stats')
    def get_stats():
        system = get_memory_system()
        stats = system.get_stats()
        return jsonify({
            "success": True,
            "data": stats,
            "message": "统计信息获取成功",
            "timestamp": datetime.now().isoformat()
        })


def start_server(host: str = "0.0.0.0", port: int = 8000, reload: bool = False):
    """启动Web服务器"""
    if FASTAPI_AVAILABLE:
        uvicorn.run("web_api.server:app", host=host, port=port, reload=reload)
    else:
        app.run(host=host, port=port, debug=reload)


if __name__ == "__main__":
    start_server()
