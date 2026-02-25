import httpx
import os
import json

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
}


def get_headers():
    env_headers = os.getenv("KEBIAO_REQUEST_HEADERS")
    if env_headers:
        try:
            # 解析环境变量中的 JSON 字符串
            return json.loads(env_headers)
        except json.JSONDecodeError:
            # 如果配置格式错误，返回默认并打印警告
            print("Warning: KEBIAO_REQUEST_HEADERS is not a valid JSON string.")
            return DEFAULT_HEADERS
    return DEFAULT_HEADERS


async def request_jwzx_kebiao(student_id):
    headers = get_headers()
    async with httpx.AsyncClient(headers=headers, timeout=10) as client:
        response = await client.get(
            f"http://jwzx.cqupt.edu.cn/kebiao/kb_stu.php?xh={student_id}"
        )
        response.raise_for_status()
        return response.text
