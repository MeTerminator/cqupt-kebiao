import httpx

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 Safari/537.36",
}


async def request_jwzx_kebiao(student_id):
    async with httpx.AsyncClient(headers=HEADERS) as client:
        response = await client.get(f"http://jwzx.cqupt.edu.cn/kebiao/kb_stu.php?xh={student_id}")
        return response.text
