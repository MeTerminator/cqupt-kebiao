import unittest
from unittest.mock import patch

import httpx

from app.provider import request_jwzx


class JwzxRequestTests(unittest.IsolatedAsyncioTestCase):
    async def fetch_with_transport(self, fetch, handler):
        client_class = httpx.AsyncClient

        def create_client(**kwargs):
            return client_class(**kwargs, transport=httpx.MockTransport(handler))

        with patch.object(request_jwzx, "get_proxy", return_value=None), patch.object(
            request_jwzx.httpx, "AsyncClient", side_effect=create_client
        ):
            return await fetch()

    async def test_all_endpoints_use_https_and_preserve_query_parameters(self):
        student_id = "2026000000"
        cases = (
            (request_jwzx.request_jwzx_kebiao, "/kebiao/kb_stu.php", {"xh": student_id}),
            (request_jwzx.request_jwzx_next_kebiao, "/kebiao/kbgs_stu.php", {"xh": student_id}),
            (request_jwzx.request_jwzx_ksap, "/ksap/showKsap.php", {"type": "stu", "id": student_id}),
            (request_jwzx.request_jwzx_ksapBk, "/ksap/ksapSearch.php", {"searchType": "stuBk", "key": student_id}),
        )
        for fetch, path, params in cases:
            with self.subTest(path=path):
                requests = []

                def handler(request):
                    requests.append(request)
                    return httpx.Response(200, text="测试页面")

                result = await self.fetch_with_transport(lambda: fetch(student_id), handler)
                self.assertEqual(result, "测试页面")
                self.assertEqual(len(requests), 1)
                self.assertEqual(requests[0].url.scheme, "https")
                self.assertEqual(requests[0].url.host, "jwzx.cqupt.edu.cn")
                self.assertEqual(requests[0].url.path, path)
                self.assertEqual(dict(requests[0].url.params), params)

    async def test_follows_redirect_and_returns_final_page(self):
        requests = []

        def handler(request):
            requests.append(request)
            if len(requests) == 1:
                return httpx.Response(301, headers={"Location": "/new/kb_stu.php?xh=2026000000"})
            return httpx.Response(200, text="课表页面")

        result = await self.fetch_with_transport(
            lambda: request_jwzx.request_jwzx_kebiao("2026000000"), handler
        )
        self.assertEqual(result, "课表页面")
        self.assertEqual(len(requests), 2)
        self.assertEqual(str(requests[-1].url), "https://jwzx.cqupt.edu.cn/new/kb_stu.php?xh=2026000000")

    async def test_final_http_error_is_still_raised(self):
        def handler(request):
            return httpx.Response(503)

        with self.assertRaises(httpx.HTTPStatusError):
            await self.fetch_with_transport(
                lambda: request_jwzx.request_jwzx_kebiao("2026000000"), handler
            )


if __name__ == "__main__":
    unittest.main()
