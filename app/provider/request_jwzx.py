import httpx
import os
import json
import functools
from typing import Dict, Optional


DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
}
BASE_URL = "http://jwzx.cqupt.edu.cn"


@functools.lru_cache()
def get_headers() -> Dict[str, str]:
    env_headers = os.getenv("KEBIAO_REQUEST_HEADERS")
    if env_headers:
        try:
            return json.loads(env_headers)
        except json.JSONDecodeError:
            print("Warning: KEBIAO_REQUEST_HEADERS is not a valid JSON string.")
    return DEFAULT_HEADERS


async def _fetch_jwzx(path: str, params: Optional[Dict[str, str]] = None) -> str:
    """通用的 JWZX 请求封装"""
    headers = get_headers()
    async with httpx.AsyncClient(headers=headers, timeout=10, base_url=BASE_URL) as client:
        response = await client.get(path, params=params)
        response.raise_for_status()
        return response.text


async def request_jwzx_kebiao(student_id: str) -> str:
    return await _fetch_jwzx("/kebiao/kb_stu.php", {"xh": student_id})


async def request_jwzx_ksap(student_id: str) -> str:
    return await _fetch_jwzx("/ksap/showKsap.php", {"type": "stu", "id": student_id})


async def request_jwzx_ksapBk(student_id: str) -> str:
    return await _fetch_jwzx("/ksap/ksapSearch.php", {"searchType": "stuBk", "key": student_id})
