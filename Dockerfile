FROM python:3.10-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 安装Python依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目代码
COPY . .

# 创建数据目录
RUN mkdir -p data/l1 data/l2 data/l3 logs

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python -c "from api.memory_system import AgentMemorySystem; s = AgentMemorySystem(); exit(0 if s.health_check()['status'] == 'healthy' else 1)"

# 默认命令
CMD ["python", "-m", "api.memory_system"]
