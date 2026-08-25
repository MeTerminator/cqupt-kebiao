#!/usr/bin/env python3
"""将旧版 Redis 课表缓存复制到 PostgreSQL。

默认仅扫描和预览；显式传入 --apply 才会写入 PostgreSQL。
脚本不会删除或修改 Redis 中的任何键。
"""

import argparse
import asyncio
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set

from dotenv import load_dotenv
from redis.asyncio import Redis


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / ".env")

from app.core.database import DATABASE_URL, Database  # noqa: E402
from app.provider.parse_jwzx_kebiao import extract_schedule_metadata  # noqa: E402


STUDENT_ID_PATTERN = re.compile(r"^[Ll\d]\d{9}$")
HTML_PREFIXES = ("kebiao_html", "ksap_html", "ksapbk_html")
REDIS_FIELDS = (
    "kebiao_html",
    "ksap_html",
    "ksapbk_html",
    "kebiao_html_ts",
    "ksap_html_ts",
    "ksapbk_html_ts",
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="将旧版 CQUPT 课表 Redis 缓存迁移到 PostgreSQL"
    )
    parser.add_argument(
        "--redis-url",
        default=os.getenv("REDIS_URL"),
        help="Redis 连接地址，默认读取 REDIS_URL",
    )
    parser.add_argument(
        "--database-url",
        default=os.getenv("DATABASE_URL", DATABASE_URL),
        help="PostgreSQL 连接地址，默认读取 DATABASE_URL",
    )
    parser.add_argument(
        "--student-id",
        help="仅迁移指定学号；不指定时扫描全部旧缓存",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="实际写入 PostgreSQL；不传时仅预览",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="输出每个学号的迁移结果",
    )
    args = parser.parse_args()
    if not args.redis_url:
        parser.error("未配置 REDIS_URL，请通过 .env 或 --redis-url 提供")
    if args.student_id:
        args.student_id = args.student_id.upper()
        if not STUDENT_ID_PATTERN.fullmatch(args.student_id):
            parser.error("--student-id 必须为 10 位重邮学号")
    return args


def parse_timestamp(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return None


async def discover_student_ids(redis_client: Redis) -> List[str]:
    student_ids: Set[str] = set()
    for prefix in HTML_PREFIXES:
        async for key in redis_client.scan_iter(match=f"{prefix}:*", count=500):
            _, _, student_id = key.partition(":")
            student_id = student_id.upper()
            if STUDENT_ID_PATTERN.fullmatch(student_id):
                student_ids.add(student_id)
    return sorted(student_ids)


async def read_legacy_cache(redis_client: Redis, student_id: str) -> Dict[str, Optional[str]]:
    keys = [f"{field}:{student_id}" for field in REDIS_FIELDS]
    values = await redis_client.mget(keys)
    return dict(zip(REDIS_FIELDS, values))


async def migrate() -> int:
    args = parse_arguments()
    redis_client = Redis.from_url(args.redis_url, decode_responses=True)
    database: Optional[Database] = None

    migrated = 0
    skipped = 0
    invalid_pages = 0

    try:
        await redis_client.ping()
        student_ids = (
            [args.student_id]
            if args.student_id
            else await discover_student_ids(redis_client)
        )
        mode = "写入" if args.apply else "预览"
        print(f"[{mode}] 发现 {len(student_ids)} 个学号的旧 Redis 缓存")

        if args.apply:
            database = Database(args.database_url)
            await database.connect()

        for student_id in student_ids:
            cache = await read_legacy_cache(redis_client, student_id)
            if not any(cache[field] for field in HTML_PREFIXES):
                skipped += 1
                if args.verbose:
                    print(f"[skip] {student_id}: 没有可迁移的 HTML")
                continue

            student_name, academic_year, semester = extract_schedule_metadata(
                cache["kebiao_html"] or ""
            )
            if not student_name or academic_year is None or semester is None:
                skipped += 1
                invalid_pages += 1
                if args.verbose:
                    print(
                        f"[skip] {student_id}: 无法读取姓名或学期，"
                        "不是有效课表"
                    )
                continue

            if args.apply and database is not None:
                inserted = await database.save_current_cache(
                    student_id=student_id,
                    academic_year=academic_year,
                    semester=semester,
                    student_name=student_name,
                    kebiao_html=cache["kebiao_html"],
                    ksap_html=cache["ksap_html"],
                    ksapbk_html=cache["ksapbk_html"],
                    kebiao_fetched_at=parse_timestamp(cache["kebiao_html_ts"]),
                    ksap_fetched_at=parse_timestamp(cache["ksap_html_ts"]),
                    ksapbk_fetched_at=parse_timestamp(cache["ksapbk_html_ts"]),
                    overwrite_existing=False,
                )
                if not inserted:
                    skipped += 1
                    if args.verbose:
                        print(
                            f"[skip] {student_id}: PostgreSQL 已存在 "
                            f"{academic_year} 学年第 {semester} 学期"
                        )
                    continue

            migrated += 1
            if args.verbose:
                name = student_name or "未知姓名"
                print(
                    f"[ok] {student_id} {name}: "
                    f"{academic_year} 学年第 {semester} 学期"
                )

        action = "已迁移" if args.apply else "可迁移"
        print(
            f"{action} {migrated} 条，跳过 {skipped} 条，"
            f"无效课表 {invalid_pages} 条"
        )
        if not args.apply:
            print("确认预览结果后，增加 --apply 执行写入。")
        return 0
    finally:
        if database is not None:
            await database.close()
        await redis_client.aclose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(migrate()))
