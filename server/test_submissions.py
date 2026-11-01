"""Isolated HTTP coverage for project collection; never modifies live event records."""
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.parse import quote
import zipfile

from app import EventHTTPServer, EventService
from test_api import Client


class SubmissionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="chuyi-submissions-test-")
        root = Path(self.temp.name)
        self.service = EventService(data_dir=root / "private", static_root=root, origin="http://127.0.0.1")
        self.server = EventHTTPServer(("127.0.0.1", 0), self.service)
        self.service.origin = "http://127.0.0.1:" + str(self.server.server_port)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.admin, self.public = Client(self.server), Client(self.server)
        code = (self.service.data_dir / "admin-access.txt").read_text().splitlines()[1]
        self.assertEqual(self.admin.post("/api/login", {"role": "admin", "code": code})[0], 200)
        self.ids = {}
        for number in [12, 2, 1]:
            status, value, _ = self.admin.post("/api/admin/teams", {"number": number, "name": f"队伍{number}", "project": "原项目", "track": "AI"})
            self.assertEqual(status, 200)
            self.ids[number] = value["team"]["id"]

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        self.temp.cleanup()

    def login(self, number=1):
        status, value, _ = self.public.post("/api/submissions/login", {"teamId": self.ids[number], "code": "000000"})
        self.assertEqual(status, 200, value)
        return value["token"]

    def request(self, method, path, token, payload=None, raw=None, headers=None):
        return self.public.request(method, "/api/submissions/" + path, payload=payload, raw=raw,
                                   headers={"Authorization": "Bearer " + token, "Origin": self.service.origin, **(headers or {})})

    def upload(self, token, name="演示.html", kind="web", raw=b"<!doctype html><h1>demo</h1>"):
        return self.request("POST", "upload/" + kind, token, raw=raw,
                            headers={"Content-Type": "application/octet-stream", "X-File-Name": quote(name)})

    def test_sorted_public_status_and_receipt_protection(self):
        status, data, _ = self.public.get("/api/submissions/teams")
        self.assertEqual(status, 200)
        self.assertEqual([t["number"] for t in data["teams"]], [1, 2, 12])
        self.assertNotIn("submission", data["teams"][0])
        token = self.login()
        self.assertEqual(self.public.post("/api/submissions/login", {"teamId": self.ids[1], "code": "000000"})[0], 409)
        status, value, _ = self.public.post("/api/submissions/login", {"teamId": self.ids[1], "code": "000000", "receipt": token})
        self.assertEqual(status, 200)
        self.assertEqual(value["token"], token)
        self.assertEqual(self.public.post("/api/submissions/login", {"teamId": self.ids[2], "code": "wrong"})[0], 401)

    def test_metadata_drafts_link_validation_and_persistence(self):
        token = self.login()
        saved = self.request("POST", "save", token, {"title": "新作品", "summary": "简介", "demoUrl": ""})
        self.assertEqual(saved[0], 200)
        self.assertFalse(saved[1]["team"]["submitted"])
        self.assertEqual(self.request("POST", "save", token, {"title": "新作品", "demoUrl": "javascript:alert(1)"})[0], 400)
        saved = self.request("POST", "save", token, {"title": "新作品", "demoUrl": "https://example.com/game?a=1"})
        self.assertEqual(saved[0], 200)
        self.assertTrue(saved[1]["team"]["submitted"])
        other = EventService(data_dir=self.service.data_dir, static_root=self.service.root, origin=self.service.origin)
        with other.db() as db:
            self.assertEqual(other.submissions.rows(db)[0]["submission"]["title"], "新作品")

    def test_upload_download_authorization_delete_and_file_limit(self):
        token, other = self.login(), self.login(2)
        uploaded = self.upload(token)
        self.assertEqual(uploaded[0], 200, uploaded[1])
        self.assertTrue(uploaded[1]["team"]["submitted"])
        file_id = uploaded[1]["files"][0]["id"]
        self.assertEqual(self.public.get("/api/submissions/files/" + file_id)[0], 401)
        self.assertEqual(self.request("GET", "files/" + file_id, other)[0], 403)
        status, data, headers = self.request("GET", "files/" + file_id, token)
        self.assertEqual(status, 200)
        self.assertIn(b"<h1>demo</h1>", data)
        self.assertEqual(headers["Content-Type"], "application/octet-stream")
        self.assertIn("attachment;", headers["Content-Disposition"])
        self.assertEqual(self.admin.get("/api/submissions/files/" + file_id)[0], 200)
        for index in range(5):
            self.assertEqual(self.upload(token, name=f"game{index}.html")[0], 200)
        self.assertEqual(self.upload(token)[0], 409)
        self.assertEqual(self.request("DELETE", "files/" + file_id, other)[0], 404)
        self.assertEqual(self.request("DELETE", "files/" + file_id, token)[0], 200)
        self.assertEqual(self.public.get("/api/submissions/files/" + file_id)[0], 404)

    def test_file_validation_origin_and_limits(self):
        token = self.login()
        self.assertEqual(self.upload(token, name="../secret.html")[0], 400)
        self.assertEqual(self.upload(token, name="script.exe")[0], 400)
        self.assertEqual(self.upload(token, raw=b"")[0], 400)
        self.assertEqual(self.request("POST", "upload/web", token, raw=b"x", headers={"Content-Type": "application/octet-stream", "X-File-Name": "demo.html", "Content-Length": str(100*1024*1024+1)})[0], 413)
        self.assertEqual(self.public.request("POST", "/api/submissions/save", {"title": "x"}, headers={"Authorization": "Bearer " + token}, origin=False)[0], 403)

    def test_multiple_team_zip_and_kind_filters(self):
        one, two = self.login(1), self.login(2)
        self.assertEqual(self.upload(one)[0], 200)
        self.assertEqual(self.upload(one, name="汇报.pptx", kind="ppt", raw=b"PPTX-test")[0], 200)
        self.assertEqual(self.upload(two, name="游戏.zip", raw=b"ZIP-test")[0], 200)
        self.assertEqual(self.request("POST", "save", two, {"title": "第二队作品", "demoUrl": "https://example.com/demo"})[0], 200)
        self.assertEqual(self.public.get("/api/submissions/admin")[0], 401)
        self.assertEqual(self.public.post("/api/submissions/download", {"teamIds": [self.ids[1]], "kind": "all"})[0], 401)
        payload = {"teamIds": [self.ids[2], self.ids[1]], "kind": "all"}
        status, data, headers = self.admin.post("/api/submissions/download", payload)
        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "application/zip")
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = archive.namelist()
            self.assertTrue(names[0].startswith("01_"))
            self.assertTrue(any("演示.html" in n for n in names))
            self.assertTrue(any("汇报.pptx" in n for n in names))
            self.assertTrue(any(n.endswith(".url") for n in names))
            self.assertIn("提交清单.csv", names)
            self.assertIn("第二队作品", archive.read("提交清单.csv").decode("utf-8-sig"))
        payload["kind"] = "ppt"
        status, data, _ = self.admin.post("/api/submissions/download", payload)
        self.assertEqual(status, 200)
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            self.assertTrue(any("汇报.pptx" in n for n in archive.namelist()))
            self.assertFalse(any(n.endswith((".html", ".url", ".zip")) for n in archive.namelist()))

    def test_admin_reset_preserves_work_and_invalidates_old_receipt(self):
        token = self.login()
        self.assertEqual(self.upload(token)[0], 200)
        self.assertEqual(self.admin.post("/api/submissions/admin/reset", {"teamId": self.ids[1]})[0], 200)
        self.assertEqual(self.request("GET", "mine", token)[0], 401)
        replacement = self.login()
        self.assertNotEqual(token, replacement)
        result = self.request("GET", "mine", replacement)
        self.assertEqual(len(result[1]["files"]), 1)

    def test_zip_preserves_long_filename_suffix_and_csv_is_safe(self):
        token = self.login()
        self.assertEqual(self.upload(token, name="长" * 100 + ".html")[0], 200)
        self.assertEqual(self.request("POST", "save", token, {"title": "=SUM(1,2)"})[0], 200)
        status, data, _ = self.admin.post("/api/submissions/download", {"teamIds": [self.ids[1]], "kind": "all"})
        self.assertEqual(status, 200)
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            self.assertTrue(any(n.endswith(".html") for n in archive.namelist()))
            self.assertIn("'=SUM(1,2)", archive.read("提交清单.csv").decode("utf-8-sig"))
        self.assertEqual(self.admin.post("/api/submissions/download", {"teamIds": [self.ids[1]], "kind": []})[0], 400)


if __name__ == "__main__":
    unittest.main()
