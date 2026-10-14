import unittest
from contextlib import ExitStack
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from fastapi import BackgroundTasks, FastAPI
from fastapi.testclient import TestClient

from app.api.curriculum import router
from app.exceptions.JwzxError import JwzxError
from app.provider.parse_jwzx_kebiao import (
    extract_schedule_metadata,
    parse_jwzx_kebiao,
)
from app.services import get_curriculum as service


STUDENT_ID = "2025216210"
INVALID_ID = "9999999999"


def schedule_html(student_id=STUDENT_ID, name="测试同学", term="2026-2027学年1学期"):
    return f"""<div id="head"><div><ul>
    <li>〉〉{term} 学生课表&gt;&gt;{student_id}{name}</li>
    </ul></div><div>今天是第 6 周 星期 3</div></div>
    <div id="stuPanel"><table><tr><th>星期</th></tr></table></div>"""


class ScheduleIdentityTests(unittest.TestCase):
    def test_valid_name_and_term(self):
        self.assertEqual(
            extract_schedule_metadata(schedule_html(), STUDENT_ID),
            ("测试同学", "2026-2027", 1),
        )
        self.assertEqual(parse_jwzx_kebiao(schedule_html()).student_name, "测试同学")

    def test_missing_name_does_not_capture_week_notice(self):
        html = schedule_html(INVALID_ID, "")
        self.assertIsNone(extract_schedule_metadata(html)[0])
        with self.assertRaises(JwzxError):
            parse_jwzx_kebiao(html)

    def test_identity_outside_header_is_not_accepted(self):
        html = f"<div>{STUDENT_ID}测试同学 2026-2027学年1学期</div>"
        self.assertEqual(extract_schedule_metadata(html), (None, None, None))

    def test_mismatched_student_is_rejected(self):
        self.assertIsNone(extract_schedule_metadata(schedule_html(), INVALID_ID)[0])
        with self.assertRaises(JwzxError):
            parse_jwzx_kebiao(schedule_html(), expected_student_id=INVALID_ID)

    def test_missing_term_is_rejected(self):
        with self.assertRaises(JwzxError):
            parse_jwzx_kebiao(schedule_html(term=""))

    def test_letter_student_id_is_normalized(self):
        data = parse_jwzx_kebiao(schedule_html("l025216210"))
        self.assertEqual(data.student_id, "L025216210")


class CurriculumCacheTests(unittest.IsolatedAsyncioTestCase):
    def mock_requests(self, html):
        stack = ExitStack()
        for request in ("request_jwzx_kebiao", "request_jwzx_next_kebiao"):
            stack.enter_context(patch.object(service, request, AsyncMock(return_value=html)))
        for request in ("request_jwzx_ksap", "request_jwzx_ksapBk"):
            stack.enter_context(patch.object(service, request, AsyncMock(
                return_value='<div id="head">2026-2027学年1学期</div>'
            )))
        return stack

    async def test_invalid_and_mismatched_pages_are_never_cached(self):
        for html in (schedule_html(INVALID_ID, ""), schedule_html()):
            for fetch, save in (
                (service._request_and_cache_current, "save_current_cache"),
                (service._request_and_cache_next, "save_next_cache"),
            ):
                with self.subTest(fetch=fetch.__name__, html=html):
                    with self.mock_requests(html), patch.object(service.database, save, AsyncMock()) as writer:
                        with self.assertRaises(JwzxError):
                            await fetch(INVALID_ID)
                        writer.assert_not_awaited()

    async def test_parse_failure_does_not_write_cache(self):
        for fetch, parser, save, result in (
            (service._request_and_cache_current, "parse_all_data", "save_current_cache", None),
            (service._request_and_cache_next, "parse_next_data", "save_next_cache", JwzxError("无效课表")),
        ):
            options = {"side_effect": result} if isinstance(result, Exception) else {"return_value": result}
            with self.mock_requests(schedule_html()), patch.object(service, parser, **options), patch.object(service.database, save, AsyncMock()) as writer:
                with self.assertRaises(JwzxError):
                    await fetch(STUDENT_ID)
                writer.assert_not_awaited()

    async def test_valid_schedule_is_cached_even_without_courses(self):
        for fetch, save in (
            (service._request_and_cache_current, "save_current_cache"),
            (service._request_and_cache_next, "save_next_cache"),
        ):
            with self.mock_requests(schedule_html()), patch.object(service.database, save, AsyncMock()) as writer:
                await fetch(STUDENT_ID)
                writer.assert_awaited_once()
                self.assertEqual(writer.call_args.kwargs["student_name"], "测试同学")

    async def test_old_invalid_cache_is_ignored(self):
        html = schedule_html(INVALID_ID, "")
        cache = {
            "student_name": "今天是第",
            "kebiao_html": html,
            "ksap_html": "empty",
            "ksapbk_html": "empty",
            "next_kebiao_html": html,
            "kebiao_fetched_at": datetime.now(timezone.utc),
            "next_kebiao_fetched_at": datetime.now(timezone.utc),
        }
        for get_data, read, fetch in (
            (service.get_curriculum_data, "get_latest_current_cache", "_request_and_cache_current"),
            (service.get_next_curriculum_data, "get_latest_next_cache", "_request_and_cache_next"),
        ):
            with patch.object(service.database, read, AsyncMock(return_value=cache)), patch.object(service, fetch, AsyncMock(side_effect=JwzxError("无效课表"))) as requester:
                tasks = BackgroundTasks()
                with self.assertRaises(JwzxError):
                    await get_data(INVALID_ID, tasks)
                requester.assert_awaited_once_with(INVALID_ID)
                self.assertEqual(tasks.tasks, [])


class CurriculumApiTests(unittest.TestCase):
    def test_invalid_student_response_has_no_name_and_no_cache_write(self):
        app = FastAPI()
        app.include_router(router)
        html = schedule_html(INVALID_ID, "")
        with ExitStack() as stack:
            stack.enter_context(patch.object(service.database, "get_latest_current_cache", AsyncMock(return_value=None)))
            writer = stack.enter_context(patch.object(service.database, "save_current_cache", AsyncMock()))
            stack.enter_context(patch.object(service, "request_jwzx_kebiao", AsyncMock(return_value=html)))
            for request in ("request_jwzx_ksap", "request_jwzx_ksapBk"):
                stack.enter_context(patch.object(service, request, AsyncMock(return_value="")))
            client = TestClient(app)
            for endpoint in ("curriculum.json", "curriculum.ics", "overview"):
                response = client.get(f"/api/curriculum/{INVALID_ID}/{endpoint}")
                self.assertEqual(response.status_code, 502)
                self.assertNotIn("student_name", response.json())
                self.assertNotIn("今天是第", response.text)
            writer.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
