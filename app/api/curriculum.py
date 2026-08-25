import json
from pathlib import Path as FilePath
from typing import Annotated, Optional

import httpx
from fastapi import APIRouter, BackgroundTasks, HTTPException, Path, Query, Response
from fastapi.responses import JSONResponse

from app.core.config import next_curriculum_enabled
from app.exceptions.JwzxError import JwzxError
from app.provider.generate_ics import generate_ics
from app.schemas.schemas import ScheduleSchema
from app.services.get_curriculum import get_curriculum_data, get_next_curriculum_data
from app.services.get_overview import get_schedule_overview


router = APIRouter(prefix="/api/curriculum")
PROJECT_ROOT = FilePath(__file__).resolve().parents[2]


def _validate_alarms(first: Optional[int], second: Optional[int]) -> list[int]:
    if first is not None and second is not None and first <= second:
        raise HTTPException(status_code=400, detail="first 参数必须大于 second 参数")
    return [value for value in (first, second) if value is not None]


def _next_curriculum_disabled_response() -> Optional[JSONResponse]:
    if next_curriculum_enabled():
        return None
    return JSONResponse(
        status_code=503,
        content={
            "enabled": False,
            "message": "下学期课表查询功能暂未开启",
        },
    )


@router.get("/{student_id}/curriculum.ics")
async def get_curriculum_ics(
    student_id: Annotated[str, Path(pattern=r"^[lL\d]\d{9}$")],
    background_tasks: BackgroundTasks,
    first: Optional[int] = Query(None, description="第一优先级提醒时间（分钟）"),
    second: Optional[int] = Query(None, description="第二优先级提醒时间（分钟）"),
):
    student_id = student_id.upper()
    alarms = _validate_alarms(first, second)

    try:
        data = await get_curriculum_data(student_id, background_tasks)
        if not data:
            raise HTTPException(status_code=404, detail="学生不存在")

        return Response(
            content=generate_ics(data, alarms),
            media_type="text/calendar",
            headers={
                "Content-Disposition": f"attachment; filename={student_id}_schedule.ics"
            },
        )
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="教务在线请求失败")
    except JwzxError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.get("/{student_id}/curriculum-next.ics")
async def get_next_curriculum_ics(
    student_id: Annotated[str, Path(pattern=r"^[lL\d]\d{9}$")],
    background_tasks: BackgroundTasks,
    first: Optional[int] = Query(None, description="第一优先级提醒时间（分钟）"),
    second: Optional[int] = Query(None, description="第二优先级提醒时间（分钟）"),
):
    disabled_response = _next_curriculum_disabled_response()
    if disabled_response is not None:
        return disabled_response
    student_id = student_id.upper()
    alarms = _validate_alarms(first, second)

    try:
        data = await get_next_curriculum_data(student_id, background_tasks)
        if data.student_id != student_id:
            raise HTTPException(status_code=404, detail="学生不存在或暂无下学期课表")

        return Response(
            content=generate_ics(data, alarms),
            media_type="text/calendar",
            headers={
                "Content-Disposition": (
                    f"attachment; filename={student_id}_schedule_next.ics"
                )
            },
        )
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="教务在线请求失败")
    except JwzxError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.get("/{student_id}/curriculum.json", response_model=ScheduleSchema)
async def get_curriculum_json(
    student_id: Annotated[str, Path(pattern=r"^[lL\d]\d{9}$")],
    background_tasks: BackgroundTasks,
):
    student_id = student_id.upper()

    try:
        data = await get_curriculum_data(student_id, background_tasks)
        if not data:
            raise HTTPException(status_code=404, detail="学生不存在")
        return data
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="教务在线请求失败")
    except JwzxError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.get("/{student_id}/curriculum-next.json", response_model=ScheduleSchema)
async def get_next_curriculum_json(
    student_id: Annotated[str, Path(pattern=r"^[lL\d]\d{9}$")],
    background_tasks: BackgroundTasks,
):
    disabled_response = _next_curriculum_disabled_response()
    if disabled_response is not None:
        return disabled_response
    student_id = student_id.upper()

    try:
        data = await get_next_curriculum_data(student_id, background_tasks)
        if data.student_id != student_id:
            raise HTTPException(status_code=404, detail="学生不存在或暂无下学期课表")
        return data
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="教务在线请求失败")
    except JwzxError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.get("/{student_id}/overview")
async def get_curriculum_overview(
    student_id: Annotated[str, Path(pattern=r"^[lL\d]\d{9}$")],
    background_tasks: BackgroundTasks,
):
    student_id = student_id.upper()

    try:
        data = await get_curriculum_data(student_id, background_tasks)
        if not data:
            raise HTTPException(status_code=404, detail="学生不存在")
        return get_schedule_overview(data)
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="教务在线请求失败")
    except JwzxError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.get("/adjustments")
async def get_curriculum_adjustments():
    adjust_file = PROJECT_ROOT / "adjustments.json"
    if not adjust_file.exists():
        raise HTTPException(status_code=404, detail="调休配置文件不存在")
    try:
        with adjust_file.open("r", encoding="utf-8") as file:
            return json.load(file)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"读取调休配置失败: {exc}")
