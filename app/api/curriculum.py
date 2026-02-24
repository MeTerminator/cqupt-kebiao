from typing import Annotated
from fastapi import APIRouter, HTTPException, Response, Path
import httpx

from app.provider.request_jwzx_kebiao import request_jwzx_kebiao
from app.parser.jwzx_kebiao import parse_jwzx_kebiao
from app.services.generate_ics import generate_ics

router = APIRouter(prefix="/api/curriculum")


@router.get("/{student_id}/schedule.ics")
async def get_schedule(
    student_id: Annotated[
        str,
        Path(
            description="学生学号，必须为10位数字",
            pattern=r"^\d{10}$"
        )
    ]
):
    try:
        jwzx_html = await request_jwzx_kebiao(student_id)
        schedule_data = parse_jwzx_kebiao(jwzx_html)
        ics_text = generate_ics(schedule_data)

        return Response(
            content=ics_text,
            media_type="text/calendar",
            headers={
                "Content-Disposition": f"attachment; filename=schedule.ics",
                "Cache-Control": "no-cache"
            }
        )
    except httpx.ReadTimeout:
        raise HTTPException(
            status_code=500, detail="教务在线请求超时")
    except httpx.HTTPStatusError:
        raise HTTPException(
            status_code=500, detail="教务在线请求失败")
