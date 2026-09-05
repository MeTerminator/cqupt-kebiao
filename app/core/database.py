import os
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import delete, func, inspect, or_, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.models import Base, StudentCurriculumCache


DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/cqupt_kebiao"
)


def _async_database_url(database_url: str) -> str:
    if database_url.startswith("postgresql+asyncpg://"):
        return database_url
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql+asyncpg://", 1)
    return database_url


class Database:
    def __init__(self, database_url: str = DATABASE_URL):
        self.database_url = _async_database_url(database_url)
        self.engine: Optional[AsyncEngine] = None
        self.session_factory: Optional[async_sessionmaker[AsyncSession]] = None

    async def connect(self, initialize_schema: bool = True) -> None:
        if self.engine is not None:
            return

        self.engine = create_async_engine(self.database_url, pool_pre_ping=True)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)
        try:
            if initialize_schema:
                await self._initialize_schema()
        except Exception:
            await self.close()
            raise

    async def _initialize_schema(self) -> None:
        async with self._require_engine().begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

            # 只保留旧版单主键表升级所需的结构迁移。
            await connection.execute(text("""
                ALTER TABLE student_curriculum_cache
                    ADD COLUMN IF NOT EXISTS academic_year VARCHAR(9),
                    ADD COLUMN IF NOT EXISTS semester SMALLINT
            """))
            await connection.execute(text("""
                UPDATE student_curriculum_cache
                SET academic_year = COALESCE(academic_year, '0000-0000'),
                    semester = COALESCE(semester, 0)
                WHERE academic_year IS NULL OR semester IS NULL
            """))
            await connection.execute(text("""
                ALTER TABLE student_curriculum_cache
                    ALTER COLUMN academic_year SET NOT NULL,
                    ALTER COLUMN semester SET NOT NULL
            """))
            result = await connection.execute(text("""
                SELECT attribute.attname
                FROM pg_constraint AS constraint_info
                CROSS JOIN LATERAL unnest(constraint_info.conkey)
                    WITH ORDINALITY AS key_column(attnum, position)
                JOIN pg_attribute AS attribute
                  ON attribute.attrelid = constraint_info.conrelid
                 AND attribute.attnum = key_column.attnum
                WHERE constraint_info.conrelid = 'student_curriculum_cache'::regclass
                  AND constraint_info.contype = 'p'
                ORDER BY key_column.position
            """))
            if list(result.scalars()) != ["student_id", "academic_year", "semester"]:
                await connection.execute(text("""
                    ALTER TABLE student_curriculum_cache
                        DROP CONSTRAINT IF EXISTS student_curriculum_cache_pkey
                """))
                await connection.execute(text("""
                    ALTER TABLE student_curriculum_cache
                        ADD CONSTRAINT student_curriculum_cache_pkey
                        PRIMARY KEY (student_id, academic_year, semester)
                """))

    async def close(self) -> None:
        if self.engine is not None:
            await self.engine.dispose()
        self.engine = None
        self.session_factory = None

    def _require_engine(self) -> AsyncEngine:
        if self.engine is None:
            raise RuntimeError("数据库尚未初始化")
        return self.engine

    def _require_session_factory(self) -> async_sessionmaker[AsyncSession]:
        if self.session_factory is None:
            raise RuntimeError("数据库尚未初始化")
        return self.session_factory

    @staticmethod
    def _as_dict(cache: StudentCurriculumCache) -> Dict[str, Any]:
        return {
            column.name: getattr(cache, column.name)
            for column in StudentCurriculumCache.__table__.columns
        }

    async def table_exists(self) -> bool:
        async with self._require_engine().connect() as connection:
            return await connection.run_sync(
                lambda sync_connection: inspect(sync_connection).has_table(
                    StudentCurriculumCache.__tablename__
                )
            )

    async def get_student_cache(
        self,
        student_id: str,
        academic_year: Optional[str] = None,
        semester: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        if (academic_year is None) != (semester is None):
            raise ValueError("academic_year 和 semester 必须同时指定")

        statement = select(StudentCurriculumCache).where(
            StudentCurriculumCache.student_id == student_id,
            StudentCurriculumCache.student_name.is_not(None),
        )
        if academic_year is not None and semester is not None:
            statement = statement.where(
                StudentCurriculumCache.academic_year == academic_year,
                StudentCurriculumCache.semester == semester,
            )
        else:
            statement = statement.order_by(
                StudentCurriculumCache.academic_year.desc(),
                StudentCurriculumCache.semester.desc(),
            ).limit(1)
        async with self._require_session_factory()() as session:
            cache = await session.scalar(statement)
        return self._as_dict(cache) if cache else None

    async def get_latest_current_cache(
        self, student_id: str
    ) -> Optional[Dict[str, Any]]:
        statement = (
            select(StudentCurriculumCache)
            .where(
                StudentCurriculumCache.student_id == student_id,
                StudentCurriculumCache.student_name.is_not(None),
                StudentCurriculumCache.kebiao_html.is_not(None),
                StudentCurriculumCache.ksap_html.is_not(None),
                StudentCurriculumCache.ksapbk_html.is_not(None),
            )
            .order_by(
                StudentCurriculumCache.academic_year.desc(),
                StudentCurriculumCache.semester.desc(),
            )
            .limit(1)
        )
        async with self._require_session_factory()() as session:
            cache = await session.scalar(statement)
        return self._as_dict(cache) if cache else None

    async def get_latest_next_cache(self, student_id: str) -> Optional[Dict[str, Any]]:
        statement = (
            select(StudentCurriculumCache)
            .where(
                StudentCurriculumCache.student_id == student_id,
                StudentCurriculumCache.student_name.is_not(None),
                StudentCurriculumCache.next_kebiao_html.is_not(None),
            )
            .order_by(
                StudentCurriculumCache.academic_year.desc(),
                StudentCurriculumCache.semester.desc(),
            )
            .limit(1)
        )
        async with self._require_session_factory()() as session:
            cache = await session.scalar(statement)
        return self._as_dict(cache) if cache else None

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

        statement = insert(StudentCurriculumCache).values(
            student_id=student_id,
            academic_year=academic_year,
            semester=semester,
            student_name=student_name,
            kebiao_html=kebiao_html,
            kebiao_fetched_at=kebiao_fetched_at or func.now(),
            ksap_html=ksap_html,
            ksap_fetched_at=ksap_fetched_at or func.now(),
            ksapbk_html=ksapbk_html,
            ksapbk_fetched_at=ksapbk_fetched_at or func.now(),
            updated_at=func.now(),
        )
        key_columns = [
            StudentCurriculumCache.student_id,
            StudentCurriculumCache.academic_year,
            StudentCurriculumCache.semester,
        ]
        if overwrite_existing:
            statement = statement.on_conflict_do_update(
                index_elements=key_columns,
                set_={
                    "student_name": statement.excluded.student_name,
                    "kebiao_html": statement.excluded.kebiao_html,
                    "kebiao_fetched_at": statement.excluded.kebiao_fetched_at,
                    "ksap_html": statement.excluded.ksap_html,
                    "ksap_fetched_at": statement.excluded.ksap_fetched_at,
                    "ksapbk_html": statement.excluded.ksapbk_html,
                    "ksapbk_fetched_at": statement.excluded.ksapbk_fetched_at,
                    "updated_at": func.now(),
                },
            )
        else:
            statement = statement.on_conflict_do_nothing(index_elements=key_columns)

        async with self._require_session_factory().begin() as session:
            result = await session.execute(statement)
        return result.rowcount == 1

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

        statement = insert(StudentCurriculumCache).values(
            student_id=student_id,
            academic_year=academic_year,
            semester=semester,
            student_name=student_name,
            next_kebiao_html=html,
            next_kebiao_fetched_at=fetched_at or func.now(),
            updated_at=func.now(),
        )
        statement = statement.on_conflict_do_update(
            index_elements=[
                StudentCurriculumCache.student_id,
                StudentCurriculumCache.academic_year,
                StudentCurriculumCache.semester,
            ],
            set_={
                "student_name": statement.excluded.student_name,
                "next_kebiao_html": statement.excluded.next_kebiao_html,
                "next_kebiao_fetched_at": statement.excluded.next_kebiao_fetched_at,
                "updated_at": func.now(),
            },
        )
        async with self._require_session_factory().begin() as session:
            await session.execute(statement)

    async def get_nameless_caches(self) -> list[Dict[str, Any]]:
        invalid_name = or_(
            StudentCurriculumCache.student_name.is_(None),
            func.btrim(StudentCurriculumCache.student_name) == "",
        )
        statement = (
            select(StudentCurriculumCache)
            .where(invalid_name)
            .order_by(
                StudentCurriculumCache.student_id,
                StudentCurriculumCache.academic_year,
                StudentCurriculumCache.semester,
            )
        )
        async with self._require_session_factory()() as session:
            rows = (await session.scalars(statement)).all()
        return [self._as_dict(row) for row in rows]

    async def delete_nameless_caches(self) -> int:
        invalid_name = or_(
            StudentCurriculumCache.student_name.is_(None),
            func.btrim(StudentCurriculumCache.student_name) == "",
        )
        async with self._require_session_factory().begin() as session:
            result = await session.execute(
                delete(StudentCurriculumCache).where(invalid_name)
            )
            await session.execute(text("""
                ALTER TABLE student_curriculum_cache
                    ALTER COLUMN student_name SET NOT NULL
            """))
        return result.rowcount


database = Database()
