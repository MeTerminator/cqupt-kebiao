import redis.asyncio as redis
import os

# Redis 配置
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')

# 创建连接池
pool = redis.ConnectionPool.from_url(
    REDIS_URL,
    decode_responses=True,
)

# 提供一个全局客户端实例
redis_client = redis.Redis(connection_pool=pool)
