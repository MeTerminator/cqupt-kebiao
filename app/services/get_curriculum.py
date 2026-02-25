from datetime import datetime
from typing import Optional
from fastapi import BackgroundTasks

from app.core.redis import redis_client
from app.provider.request_jwzx_kebiao import request_jwzx_kebiao
from app.provider.parse_jwzx_kebiao import parse_jwzx_kebiao
from app.schemas.schedule_instances import ScheduleSchema


async def update_cache(student_id: str):
    """后台更新缓存的任务"""
    try:
        html = await request_jwzx_kebiao(student_id)
        now_dt = datetime.now()
        schedule_data = parse_jwzx_kebiao(html, request_at=now_dt)
        if schedule_data.student_id == student_id:
            # 使用 pipeline 可以一次性发送多个命令，稍微提升效率
            async with redis_client.pipeline(transaction=True) as pipe:
                # 每一行都在往缓冲区填命令，但不 await 它们
                pipe.set(f"kebiao_html:{student_id}", html, ex=3600)
                pipe.set(f"kebiao_html_ts:{student_id}",
                         now_dt.timestamp())
                await pipe.execute()
    except Exception:
        pass  # 满足“请求失败不重试”


async def get_curriculum_data(student_id: str, background_tasks: BackgroundTasks) -> Optional[ScheduleSchema]:
    # 1. 尝试从 Redis 获取缓存
    cached_html = await redis_client.get(f"kebiao_html:{student_id}")
    last_update_ts = await redis_client.get(f"kebiao_html_ts:{student_id}")

    now_ts = datetime.now().timestamp()

    # 2. 存在缓存的情况 (Stale-While-Revalidate)
    if cached_html and last_update_ts:
        last_update_ts = float(last_update_ts)
        last_update_dt = datetime.fromtimestamp(float(last_update_ts))
        if (now_ts - last_update_ts) > 5:
            # 超过 5s，触发后台异步刷新
            background_tasks.add_task(update_cache, student_id)

        # 无论是否过期，都先返回旧数据
        return parse_jwzx_kebiao(cached_html, request_at=last_update_dt)

    # 3. 无缓存情况：阻塞请求
    try:
        html = await request_jwzx_kebiao(student_id)
        now_dt = datetime.now()
        schedule_data = parse_jwzx_kebiao(html, request_at=now_dt)

        if schedule_data.student_id != student_id:
            return None

        # 首次拉取成功，写入缓存
        async with redis_client.pipeline(transaction=True) as pipe:
            pipe.set(f"kebiao_html:{student_id}", html, ex=3600)
            pipe.set(f"kebiao_html_ts:{student_id}",
                     now_dt.timestamp())
            await pipe.execute()
        return schedule_data
    except Exception:
        # 如果教务在线挂了且没缓存，抛出异常让上层捕获
        raise
