import os
from datetime import datetime
from typing import Any, Dict, Optional

import asyncpg


DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/cqupt_kebiao"
)


class Database:
    def __init__(self, database_url: str = DATABASE_URL):
        self.database_url = database_url
        self.pool: Optional[asyncpg.Pool] = None

    async def connect(self) -> None:
        if self.pool is not None:
            return

        self.pool = await asyncpg.create_pool(self.database_url)
        try:
            async with self.pool.acquire() as connection:
                async with connection.transaction():
                    await connection.execute(
                        """
                        CREATE TABLE IF NOT EXISTS student_curriculum_cache (
                            student_id VARCHAR(10) NOT NULL,
                            academic_year VARCHAR(9) NOT NULL,
                            semester SMALLINT NOT NULL,
                            student_name TEXT NOT NULL,
                            kebiao_html TEXT,
                            kebiao_fetched_at TIMESTAMPTZ,
                            ksap_html TEXT,
                            ksap_fetched_at TIMESTAMPTZ,
                            ksapbk_html TEXT,
                            ksapbk_fetched_at TIMESTAMPTZ,
                            next_kebiao_html TEXT,
                            next_kebiao_fetched_at TIMESTAMPTZ,
                            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            PRIMARY KEY (student_id, academic_year, semester)
                        )
                        """
                    )

                    # 兼容从旧版“仅以学号为主键”的表结构升级。
                    await connection.execute(
                        """
                        ALTER TABLE student_curriculum_cache
                            ADD COLUMN IF NOT EXISTS academic_year VARCHAR(9),
                            ADD COLUMN IF NOT EXISTS semester SMALLINT
                        """
                    )
                    await connection.execute(
                        """
                        UPDATE student_curriculum_cache
                        SET academic_year = COALESCE(academic_year, '0000-0000'),
                            semester = COALESCE(semester, 0)
                        WHERE academic_year IS NULL OR semester IS NULL
                        """
                    )
                    await connection.execute(
                        """
                        ALTER TABLE student_curriculum_cache
                            ALTER COLUMN academic_year SET NOT NULL,
                            ALTER COLUMN semester SET NOT NULL
                        """
                    )

                    primary_key_columns = await connection.fetch(
                        """
                        SELECT attribute.attname
                        FROM pg_constraint AS constraint_info
                        CROSS JOIN LATERAL unnest(constraint_info.conkey)
                            WITH ORDINALITY AS key_column(attnum, position)
                        JOIN pg_attribute AS attribute
                          ON attribute.attrelid = constraint_info.conrelid
                         AND attribute.attnum = key_column.attnum
                        WHERE constraint_info.conrelid =
                                  'student_curriculum_cache'::regclass
                          AND constraint_info.contype = 'p'
                        ORDER BY key_column.position
                        """
                    )
                    column_names = [row["attname"] for row in primary_key_columns]
                    expected_columns = ["student_id", "academic_year", "semester"]
                    if column_names != expected_columns:
                        await connection.execute(
                            """
                            ALTER TABLE student_curriculum_cache
                                DROP CONSTRAINT IF EXISTS student_curriculum_cache_pkey;
                            ALTER TABLE student_curriculum_cache
                                ADD CONSTRAINT student_curriculum_cache_pkey
                                PRIMARY KEY (student_id, academic_year, semester)
                            """
                        )
        except Exception:
            await self.pool.close()
            self.pool = None
            raise

    async def close(self) -> None:
        if self.pool is not None:
            await self.pool.close()
            self.pool = None

    def _require_pool(self) -> asyncpg.Pool:
        if self.pool is None:
            raise RuntimeError("数据库尚未初始化")
        return self.pool

    async def get_student_cache(
        self,
        student_id: str,
        academic_year: Optional[str] = None,
        semester: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        查询某学期缓存。未指定学年学期时，默认返回最新学期。
        """
        if (academic_year is None) != (semester is None):
            raise ValueError("academic_year 和 semester 必须同时指定")

        if academic_year is not None and semester is not None:
            row = await self._require_pool().fetchrow(
                """
                SELECT * FROM student_curriculum_cache
                WHERE student_id = $1
                  AND academic_year = $2
                  AND semester = $3
                  AND student_name IS NOT NULL
                """,
                student_id,
                academic_year,
                semester,
            )
        else:
            row = await self._require_pool().fetchrow(
                """
                SELECT * FROM student_curriculum_cache
                WHERE student_id = $1 AND student_name IS NOT NULL
                ORDER BY academic_year DESC, semester DESC
                LIMIT 1
                """,
                student_id,
            )
        return dict(row) if row else None

    async def get_latest_current_cache(
        self, student_id: str
    ) -> Optional[Dict[str, Any]]:
        """返回同时具备课表、考试和补考页的最新学期。"""
        row = await self._require_pool().fetchrow(
            """
            SELECT * FROM student_curriculum_cache
            WHERE student_id = $1
              AND student_name IS NOT NULL
              AND kebiao_html IS NOT NULL
              AND ksap_html IS NOT NULL
              AND ksapbk_html IS NOT NULL
            ORDER BY academic_year DESC, semester DESC
            LIMIT 1
            """,
            student_id,
        )
        return dict(row) if row else None

    async def get_latest_next_cache(
        self, student_id: str
    ) -> Optional[Dict[str, Any]]:
        """返回有效的最新下学期公示课表。"""
        row = await self._require_pool().fetchrow(
            """
            SELECT * FROM student_curriculum_cache
            WHERE student_id = $1
              AND student_name IS NOT NULL
              AND next_kebiao_html IS NOT NULL
            ORDER BY academic_year DESC, semester DESC
            LIMIT 1
            """,
            student_id,
        )
        return dict(row) if row else None

    async def save_current_cache(
        self,
        student_id: str,
        academic_year: str,
        semester: int,
        student_name: Optional[str],
        kebiao_html: Optional[str],
        ksap_html: Optional[str],
        ksapbk_html: Optional[str],
        kebiao_fetched_at: Optional[datetime] = None,
        ksap_fetched_at: Optional[datetime] = None,
        ksapbk_fetched_at: Optional[datetime] = None,
        overwrite_existing: bool = True,
    ) -> bool:
        if not student_name or not student_name.strip():
            raise ValueError("学生姓名为空，拒绝写入课表缓存")

        conflict_action = (
            """
            DO UPDATE SET
                student_name = COALESCE(EXCLUDED.student_name, student_curriculum_cache.student_name),
                kebiao_html = EXCLUDED.kebiao_html,
                kebiao_fetched_at = EXCLUDED.kebiao_fetched_at,
                ksap_html = EXCLUDED.ksap_html,
                ksap_fetched_at = EXCLUDED.ksap_fetched_at,
                ksapbk_html = EXCLUDED.ksapbk_html,
                ksapbk_fetched_at = EXCLUDED.ksapbk_fetched_at,
                updated_at = NOW()
            """
            if overwrite_existing
            else "DO NOTHING"
        )
        result = await self._require_pool().execute(
            f"""
            INSERT INTO student_curriculum_cache (
                student_id, academic_year, semester, student_name,
                kebiao_html, kebiao_fetched_at,
                ksap_html, ksap_fetched_at,
                ksapbk_html, ksapbk_fetched_at,
                updated_at
            ) VALUES (
                $1, $2, $3, $4,
                $5, COALESCE($6, NOW()),
                $7, COALESCE($8, NOW()),
                $9, COALESCE($10, NOW()),
                NOW()
            )
            ON CONFLICT (student_id, academic_year, semester) {conflict_action}
            """,
            student_id,
            academic_year,
            semester,
            student_name,
            kebiao_html,
            kebiao_fetched_at,
            ksap_html,
            ksap_fetched_at,
            ksapbk_html,
            ksapbk_fetched_at,
        )
        return result == "INSERT 0 1"

    async def save_next_cache(
        self,
        student_id: str,
        academic_year: str,
        semester: int,
        student_name: Optional[str],
        html: str,
        fetched_at: Optional[datetime] = None,
    ) -> None:
        if not student_name or not student_name.strip():
            raise ValueError("学生姓名为空，拒绝写入课表缓存")

        await self._require_pool().execute(
            """
            INSERT INTO student_curriculum_cache (
                student_id, academic_year, semester, student_name,
                next_kebiao_html, next_kebiao_fetched_at,
                updated_at
            ) VALUES ($1, $2, $3, $4, $5, COALESCE($6, NOW()), NOW())
            ON CONFLICT (student_id, academic_year, semester) DO UPDATE SET
                student_name = COALESCE(EXCLUDED.student_name, student_curriculum_cache.student_name),
                next_kebiao_html = EXCLUDED.next_kebiao_html,
                next_kebiao_fetched_at = EXCLUDED.next_kebiao_fetched_at,
                updated_at = NOW()
            """,
            student_id,
            academic_year,
            semester,
            student_name,
            html,
            fetched_at,
        )


database = Database()
