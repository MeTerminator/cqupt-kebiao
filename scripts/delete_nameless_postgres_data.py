#!/usr/bin/env python3
"""清理 PostgreSQL 中学生姓名为空的课表记录。

默认仅统计；显式传入 --apply 才会删除数据。
"""

import argparse
import asyncio
import os
from pathlib import Path

import asyncpg
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="删除 PostgreSQL 课表表中无学生姓名的记录"
    )
    parser.add_argument(
        "--database-url",
        default=os.getenv("DATABASE_URL"),
        help="PostgreSQL 连接地址，默认读取 DATABASE_URL",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="实际删除数据；不传时仅统计",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="列出将被删除记录的学号、学年和学期",
    )
    args = parser.parse_args()
    if not args.database_url:
        parser.error("未配置 DATABASE_URL，请通过 .env 或 --database-url 提供")
    return args


async def cleanup() -> int:
    args = parse_arguments()
    connection = await asyncpg.connect(args.database_url)

    try:
        table_exists = await connection.fetchval(
            "SELECT to_regclass('student_curriculum_cache') IS NOT NULL"
        )
        if not table_exists:
            print("student_curriculum_cache 表不存在，无需清理。")
            return 0

        invalid_condition = "student_name IS NULL OR BTRIM(student_name) = ''"
        rows = await connection.fetch(
            f"""
            SELECT student_id, academic_year, semester
            FROM student_curriculum_cache
            WHERE {invalid_condition}
            ORDER BY student_id, academic_year, semester
            """
        )

        print(f"发现 {len(rows)} 条无姓名课表记录。")
        if args.verbose:
            for row in rows:
                print(
                    f"- {row['student_id']} "
                    f"{row['academic_year']} 学年第 {row['semester']} 学期"
                )

        if not args.apply:
            print("当前为预览模式；确认后增加 --apply 执行删除。")
            return 0

        async with connection.transaction():
            result = await connection.execute(
                f"""
                DELETE FROM student_curriculum_cache
                WHERE {invalid_condition}
                """
            )
            await connection.execute(
                """
                ALTER TABLE student_curriculum_cache
                    ALTER COLUMN student_name SET NOT NULL
                """
            )

        deleted_count = int(result.rsplit(" ", 1)[-1])
        print(f"已删除 {deleted_count} 条无姓名记录，并启用 student_name NOT NULL 约束。")
        return 0
    finally:
        await connection.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(cleanup()))
