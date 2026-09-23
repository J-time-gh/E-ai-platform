"""创建、复用 Redis Client"""

from functools import lru_cache

from redis import Redis

from app.core.config import settings


# 整个 FastAPI 进程 共用一个 Redis Client（最多缓存一个返回结果）
@lru_cache(maxsize=1)
def get_redis_client() -> Redis:
    """返回进程内复用的 Redis Client。"""
    return Redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_connect_timeout=settings.redis_socket_timeout_seconds,
        socket_timeout=settings.redis_socket_timeout_seconds,
    )


@lru_cache(maxsize=1)
def get_rq_redis_client() -> Redis:
    """供 RQ 读写二进制 Job 数据使用。"""
    return Redis.from_url(
        settings.redis_url,
        decode_responses=False,
        socket_connect_timeout=settings.redis_socket_timeout_seconds,
        socket_timeout=settings.redis_socket_timeout_seconds,
    )
