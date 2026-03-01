from pydantic import BaseModel, Field
from datetime import datetime
from typing import List, Optional


class ExamInstance(BaseModel):
    course: str = Field(..., description="课程名称")
    teacher: str | None = Field(None, description="教师姓名")
    week: int | None = Field(None, ge=1, le=30, description="周次")
    day: int | None = Field(None, ge=1, le=7, description="星期几")
    periods: list[int] = Field(..., description="节次描述")
    date: str | None = Field(None, description="考试日期")
    start_time: str = Field(..., description="开始时间")
    end_time: str = Field(..., description="结束时间")
    location: str = Field(..., description="考试地点")
    seat: str = Field(..., description="考试座位")
    type: str = Field(..., description="考试类型")


class CourseInstance(BaseModel):
    course: str = Field(..., description="课程名称")
    course_id: Optional[str] = Field(None, description="课程代码")
    class_id: Optional[str] = Field(None, description="教学班号")
    course_type: Optional[str] = Field(None, description="修读类型")
    credit: Optional[str] = Field(None, description="学分")

    teacher: str = Field(..., description="教师姓名")
    week: int | None = Field(..., ge=0, le=30, description="周次")
    day: int | None = Field(..., ge=1, le=7, description="星期几")
    periods: list[int] = Field(..., description="节次列表")

    date: str = Field(..., description="上课日期")
    start_time: str = Field(..., description="起始时间")
    end_time: str = Field(..., description="结束时间")
    location: str = Field(..., description="地点")

    description: str | None = Field(None, description="描述")
    conflicts: Optional[List] = Field(None, description="冲突课程")
    type: str = Field(default="常规", description="日程分类（常规/停课/补课/代课）")


class ScheduleSchema(BaseModel):
    """汇总模型：包含所有课程实例和校历基准时间"""
    student_id: str = Field(..., description="学生学号")
    student_name: str = Field(..., description="学生姓名")
    academic_year: str = Field(..., description="学年")
    semester: str = Field(..., description="学期")
    week_1_monday: datetime = Field(..., description="第一周周一的日期")
    instances: List[CourseInstance] = Field(..., description="所有的课程列表")
