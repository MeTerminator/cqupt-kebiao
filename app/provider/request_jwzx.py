import httpx
import logging
import os
from typing import Dict, Optional


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 Safari/537.36",
}
BASE_URL = "http://jwzx.cqupt.edu.cn"
logger = logging.getLogger(__name__)


def get_proxy() -> Optional[str]:
    """Return the optional outbound proxy URL configured for JWZX requests."""
    return os.getenv("KEBIAO_REQUEST_PROXY") or None


async def _fetch_jwzx(path: str, params: Optional[Dict[str, str]] = None) -> str:
    """通用的 JWZX 请求封装"""
    try:
        async with httpx.AsyncClient(
            headers=HEADERS,
            timeout=10,
            base_url=BASE_URL,
            proxy=get_proxy(),
        ) as client:
            response = await client.get(path, params=params)
            response.raise_for_status()
            logger.info("JWZX request succeeded: path=%s status=%s", path, response.status_code)
            return response.text
    except httpx.HTTPError as error:
        logger.warning("JWZX request failed: path=%s error=%s", path, error)
        raise


async def request_jwzx_kebiao(student_id: str) -> str:
    return await _fetch_jwzx("/kebiao/kb_stu.php", {"xh": student_id})


async def request_jwzx_next_kebiao(student_id: str) -> str:
    return await _fetch_jwzx("/kebiao/kbgs_stu.php", {"xh": student_id})


async def request_jwzx_ksap(student_id: str) -> str:
    return await _fetch_jwzx("/ksap/showKsap.php", {"type": "stu", "id": student_id})


async def request_jwzx_ksapBk(student_id: str) -> str:
    return await _fetch_jwzx("/ksap/ksapSearch.php", {"searchType": "stuBk", "key": student_id})
