from typing import Annotated
from fastapi import APIRouter, HTTPException, Response, Path, BackgroundTasks
import httpx

from app.services.get_curriculum import get_curriculum_data
from app.provider.generate_ics import generate_ics
from app.schemas.schedule_instances import ScheduleSchema
from app.exceptions.JwzxError import JwzxError


router = APIRouter(prefix="/api/curriculum")


@router.get("/{student_id}/curriculum.ics")
async def get_curriculum_ics(
    student_id: Annotated[str, Path(pattern=r"^\d{10}$")],
    background_tasks: BackgroundTasks
):
    try:
        data = await get_curriculum_data(student_id, background_tasks)
        if not data:
            raise HTTPException(status_code=404, detail="学生不存在")

        ics_text = generate_ics(data)
        return Response(
            content=ics_text,
            media_type="text/calendar",
            headers={"Content-Disposition": f"attachment; filename=schedule.ics"}
        )
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="教务在线请求失败")
    except JwzxError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/{student_id}/curriculum.json", response_model=ScheduleSchema)
async def get_curriculum_json(
    student_id: Annotated[str, Path(pattern=r"^\d{10}$")],
    background_tasks: BackgroundTasks
):
    try:
        data = await get_curriculum_data(student_id, background_tasks)
        if not data:
            raise HTTPException(status_code=404, detail="学生不存在")
        return data
    except JwzxError as e:
        raise HTTPException(status_code=502, detail=str(e))
