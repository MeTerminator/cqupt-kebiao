from typing import Annotated, Optional
from fastapi import APIRouter, HTTPException, Response, Path, BackgroundTasks, Query
import httpx
import os
import json

from app.services.get_curriculum import get_curriculum_data
from app.services.get_overview import get_schedule_overview
from app.provider.generate_ics import generate_ics
from app.schemas.schemas import ScheduleSchema
from app.exceptions.JwzxError import JwzxError


router = APIRouter(prefix="/api/curriculum")


@router.get("/{student_id}/curriculum.ics")
async def get_curriculum_ics(
    student_id: Annotated[str, Path(pattern=r"^[lL\d]\d{9}$")],
    background_tasks: BackgroundTasks,
    first: Optional[int] = Query(None, description="第一优先级提醒时间（分钟）"),
    second: Optional[int] = Query(None, description="第二优先级提醒时间（分钟）")
):
    student_id = student_id.upper()

    # 校验逻辑：first 必须比 second 大
    if first is not None and second is not None:
        if first <= second:
            raise HTTPException(
                status_code=400, detail="first 参数必须大于 second 参数")

    try:
        data = await get_curriculum_data(student_id, background_tasks)
        if not data:
            raise HTTPException(status_code=404, detail="学生不存在")

        # 构造提醒列表
        alarms = []
        if first is not None:
            alarms.append(first)
        if second is not None:
            alarms.append(second)

        # 传入 generate_ics
        ics_text = generate_ics(data, alarms)

        return Response(
            content=ics_text,
            media_type="text/calendar",
            headers={
                "Content-Disposition": f"attachment; filename={student_id}_schedule.ics"}
        )
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="教务在线请求失败")
    except JwzxError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/{student_id}/curriculum.json", response_model=ScheduleSchema)
async def get_curriculum_json(
    student_id: Annotated[str, Path(pattern=r"^[lL\d]\d{9}$")],
    background_tasks: BackgroundTasks
):
    student_id = student_id.upper()

    try:
        data = await get_curriculum_data(student_id, background_tasks)
        if not data:
            raise HTTPException(status_code=404, detail="学生不存在")
        return data
    except JwzxError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/{student_id}/overview")
async def get_curriculum_overview(
    student_id: Annotated[str, Path(pattern=r"^[lL\d]\d{9}$")],
    background_tasks: BackgroundTasks
):
    student_id = student_id.upper()

    try:
        data = await get_curriculum_data(student_id, background_tasks)
        if not data:
            raise HTTPException(status_code=404, detail="学生不存在")

        overview = get_schedule_overview(data)
        return overview

    except JwzxError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"内部错误: {str(e)}")


@router.get("/adjustments")
async def get_curriculum_adjustments():
    base_path = os.getcwd()
    adjust_file = os.path.join(base_path, "adjustments.json")
    if not os.path.exists(adjust_file):
        raise HTTPException(status_code=404, detail="调休配置文件不存在")
    try:
        with open(adjust_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"读取调休配置失败: {str(e)}")
