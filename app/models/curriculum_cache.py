from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, SmallInteger, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class StudentCurriculumCache(Base):
    __tablename__ = "student_curriculum_cache"

    student_id: Mapped[str] = mapped_column(String(10), primary_key=True)
    academic_year: Mapped[str] = mapped_column(String(9), primary_key=True)
    semester: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    student_name: Mapped[str] = mapped_column(Text, nullable=False)
    kebiao_html: Mapped[Optional[str]] = mapped_column(Text)
    kebiao_fetched_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )
    ksap_html: Mapped[Optional[str]] = mapped_column(Text)
    ksap_fetched_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    ksapbk_html: Mapped[Optional[str]] = mapped_column(Text)
    ksapbk_fetched_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )
    next_kebiao_html: Mapped[Optional[str]] = mapped_column(Text)
    next_kebiao_fetched_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
