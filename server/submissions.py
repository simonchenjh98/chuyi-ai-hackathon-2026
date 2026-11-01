"""Student project collection. Files and ZIP staging stay in the private data directory."""
from __future__ import annotations

import csv
import hashlib
import hmac
import io
import json
from pathlib import Path
import re
import secrets
import tempfile
import threading
import time
from urllib.parse import quote, unquote, urlsplit
import zipfile

FILE_LIMIT = None
FILE_COUNT = 6
SCHEMA = """
CREATE TABLE IF NOT EXISTS project_submissions (
 team_id TEXT PRIMARY KEY REFERENCES teams(id), token_hash TEXT NOT NULL,
 title TEXT NOT NULL DEFAULT '', summary TEXT NOT NULL DEFAULT '', demo_url TEXT NOT NULL DEFAULT '',
 updated_at INTEGER NOT NULL, created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS project_files (
 id TEXT PRIMARY KEY, team_id TEXT NOT NULL REFERENCES teams(id), name TEXT NOT NULL,
 kind TEXT NOT NULL CHECK(kind IN ('ppt','web')), size INTEGER NOT NULL, created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS project_files_team ON project_files(team_id);
CREATE TABLE IF NOT EXISTS project_submission_tokens (
 token_hash TEXT PRIMARY KEY, team_id TEXT NOT NULL REFERENCES teams(id), created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS project_submission_tokens_team ON project_submission_tokens(team_id);
"""


class SubmissionService:
    def __init__(self, service, error_type):
        self.service, self.error = service, error_type
        self.directory = service.data_dir / "project-files"
        self.directory.mkdir(mode=0o700, exist_ok=True)
        self.upload_slots = threading.BoundedSemaphore(4)
        self.download_slots = threading.BoundedSemaphore(2)
        self.files_lock = threading.Lock()
        with service.db() as db:
            db.executescript(SCHEMA)

    def field(self, value, label, limit, required=False):
        if not isinstance(value, str):
            raise self.error(400, label + "必须为文字")
        value = value.strip()
        try:
            value.encode("utf-8")
        except UnicodeError:
            raise self.error(400, label + "含无效字符")
        if len(value) > limit or (required and not value) or any(ord(c) < 32 and c not in "\n\t" for c in value):
            raise self.error(400, label + "长度或内容不正确")
        return value

    def token(self, handler):
        value = handler.headers.get("Authorization", "")
        if not value.startswith("Bearer ") or not re.fullmatch(r"[A-Za-z0-9_-]{40,100}", value[7:]):
            raise self.error(401, "请先选择队伍并登录提交平台")
        return hashlib.sha256(value[7:].encode()).hexdigest()

    def student(self, db, handler):
        hashed = self.token(handler)
        row = db.execute("SELECT team_id FROM project_submissions WHERE token_hash=? UNION ALL SELECT team_id FROM project_submission_tokens WHERE token_hash=? LIMIT 1", (hashed, hashed)).fetchone()
        if not row:
            raise self.error(401, "提交凭证已失效，请重新登录或联系老师")
        return row["team_id"]

    def admin(self, db, handler):
        actor = self.service.account(db, handler.headers.get("Cookie", ""))
        self.service.require(actor, "admin")
        return actor

    def length(self, handler, maximum=16384):
        if handler.headers.get("Transfer-Encoding") or len(handler.headers.get_all("Content-Length", [])) != 1:
            raise self.error(400, "请求长度不正确")
        try:
            size = int(handler.headers.get("Content-Length", "-1"))
        except ValueError:
            raise self.error(400, "请求长度不正确")
        if size < 0:
            raise self.error(400, "请求长度不正确")
        if maximum is not None and size > maximum:
            raise self.error(413, "请求内容超过限制")
        return size

    def read_json(self, handler):
        length = self.length(handler)
        if handler.headers.get_content_type() != "application/json":
            raise self.error(415, "请使用JSON请求")
        try:
            value = json.loads(handler.rfile.read(length).decode("utf-8"), parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        except (ValueError, UnicodeError):
            raise self.error(400, "JSON格式不正确")
        if not isinstance(value, dict):
            raise self.error(400, "请求必须为对象")
        return value

    def rows(self, db):
        result = []
        for team in db.execute("SELECT id,number,name,project FROM teams ORDER BY number"):
            item = dict(team)
            row = db.execute("SELECT title,summary,demo_url,updated_at FROM project_submissions WHERE team_id=?", (team["id"],)).fetchone()
            item["submission"] = ({"title": row["title"], "summary": row["summary"], "demoUrl": row["demo_url"], "updatedAt": row["updated_at"]} if row else None)
            item["files"] = [dict(f) for f in db.execute("SELECT id,name,kind,size,created_at AS createdAt FROM project_files WHERE team_id=? ORDER BY kind,created_at,id", (team["id"],))]
            item["submitted"] = bool(item["files"] or (row and row["demo_url"]))
            result.append(item)
        return result

    def mine(self, db, team_id):
        item = next((r for r in self.rows(db) if r["id"] == team_id), None)
        if not item:
            raise self.error(404, "队伍不存在")
        return {"team": {k: item[k] for k in ("id", "number", "name", "project", "submitted")}, "submission": item["submission"], "files": item["files"]}

    def handle(self, handler, path):
        method = handler.command
        if method not in {"GET", "POST", "DELETE"}:
            raise self.error(405, "请求方法不支持")
        if method in {"POST", "DELETE"}:
            if handler.headers.get("Origin") != self.service.origin or handler.headers.get("Sec-Fetch-Site") not in {None, "same-origin", "none"}:
                raise self.error(403, "仅允许本站发起操作")
        if method == "POST" and path.startswith("/api/submissions/upload/"):
            return self.upload(handler, path.rsplit("/", 1)[-1])
        body = self.read_json(handler) if method == "POST" else {}
        if method == "POST" and path == "/api/submissions/download":
            return self.download(handler, body)
        if path.startswith("/api/submissions/files/"):
            file_id = path.rsplit("/", 1)[-1]
            if not re.fullmatch(r"[a-f0-9]{32}", file_id):
                raise self.error(404, "附件不存在")
            if method == "GET":
                return self.file_download(handler, file_id)
            if method == "DELETE":
                with self.files_lock, self.service.db() as db:
                    db.execute("BEGIN IMMEDIATE")
                    team_id = self.student(db, handler)
                    row = db.execute("SELECT * FROM project_files WHERE id=? AND team_id=?", (file_id, team_id)).fetchone()
                    if not row:
                        raise self.error(404, "附件不存在或无权删除")
                    db.execute("DELETE FROM project_files WHERE id=?", (file_id,))
                    db.execute("UPDATE project_submissions SET updated_at=? WHERE team_id=?", (int(time.time()*1000), team_id))
                (self.directory / file_id).unlink(missing_ok=True)
                handler.respond(200, {"ok": True})
                return
            raise self.error(405, "请求方法不支持")
        with self.service.db() as db:
            if method == "POST":
                db.execute("BEGIN IMMEDIATE")
            if method == "GET" and path == "/api/submissions/teams":
                value = {"teams": [{k: row[k] for k in ("id", "number", "name", "project", "submitted")} for row in self.rows(db)], "maxFileSize": FILE_LIMIT, "maxFiles": FILE_COUNT}
            elif method == "POST" and path == "/api/submissions/login":
                self.service.rate_limit(handler.client_address[0], "student", per_ip_limit=100)
                team_id = self.field(body.get("teamId"), "队伍", 80, True)
                if not db.execute("SELECT 1 FROM teams WHERE id=?", (team_id,)).fetchone():
                    raise self.error(404, "队伍不存在")
                existing = db.execute("SELECT token_hash FROM project_submissions WHERE team_id=?", (team_id,)).fetchone()
                receipt = body.get("receipt", "")
                if existing and existing["token_hash"] and isinstance(receipt, str) and re.fullmatch(r"[A-Za-z0-9_-]{40,100}", receipt) and hmac.compare_digest(hashlib.sha256(receipt.encode()).hexdigest(), existing["token_hash"]):
                    token = receipt
                else:
                    token = secrets.token_urlsafe(36)
                    hashed = hashlib.sha256(token.encode()).hexdigest()
                    at = int(time.time()*1000)
                    db.execute("INSERT OR IGNORE INTO project_submissions(team_id,token_hash,updated_at,created_at) VALUES (?,?,?,?)", (team_id, hashed, at, at))
                    db.execute("INSERT INTO project_submission_tokens(token_hash,team_id,created_at) VALUES (?,?,?)", (hashed, team_id, at))
                value = {"token": token, "receipt": token, **self.mine(db, team_id)}
            elif method == "GET" and path == "/api/submissions/mine":
                value = self.mine(db, self.student(db, handler))
            elif method == "POST" and path == "/api/submissions/save":
                team_id = self.student(db, handler)
                title = self.field(body.get("title", ""), "作品名称", 140, True)
                summary = self.field(body.get("summary", ""), "作品说明", 2000)
                demo = self.field(body.get("demoUrl", ""), "网页链接", 2048)
                if demo:
                    parsed = urlsplit(demo)
                    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or any(c.isspace() for c in demo):
                        raise self.error(400, "演示链接必须为完整http或https网址")
                db.execute("UPDATE project_submissions SET title=?,summary=?,demo_url=?,updated_at=? WHERE team_id=?", (title, summary, demo, int(time.time()*1000), team_id))
                value = {"ok": True, **self.mine(db, team_id)}
            elif method == "GET" and path == "/api/submissions/admin":
                self.admin(db, handler)
                value = {"teams": self.rows(db)}
            elif method == "POST" and path == "/api/submissions/admin/reset":
                actor = self.admin(db, handler)
                team_id = self.field(body.get("teamId"), "队伍", 80, True)
                if not db.execute("SELECT 1 FROM teams WHERE id=?", (team_id,)).fetchone():
                    raise self.error(404, "队伍不存在")
                db.execute("UPDATE project_submissions SET token_hash='' WHERE team_id=?", (team_id,))
                db.execute("DELETE FROM project_submission_tokens WHERE team_id=?", (team_id,))
                self.service.audit(db, actor, "submission.reset", target=team_id)
                value = {"ok": True}
            else:
                raise self.error(404, "接口不存在")
        handler.respond(200, value)

    def upload(self, handler, kind):
        if kind not in {"ppt", "web"}:
            raise self.error(400, "附件类型不正确")
        size = self.length(handler, FILE_LIMIT)
        if size == 0:
            raise self.error(400, "附件不能为空")
        name = self.field(unquote(handler.headers.get("X-File-Name", "")), "文件名", 180, True)
        if "/" in name or "\\" in name or any(ord(c) < 32 for c in name) or name in {".", ".."}:
            raise self.error(400, "文件名不正确")
        suffix = Path(name).suffix.lower()
        if suffix not in ({".ppt", ".pptx", ".pdf"} if kind == "ppt" else {".html", ".htm", ".zip"}):
            raise self.error(400, "PPT支持ppt/pptx/pdf；网页支持html/htm/zip")
        with self.service.db() as db:
            team_id = self.student(db, handler)
        if not self.upload_slots.acquire(blocking=False):
            raise self.error(503, "上传通道繁忙，请稍后重试")
        temporary = None
        file_id = secrets.token_hex(16)
        try:
            handler.connection.settimeout(3600)
            with tempfile.NamedTemporaryFile(dir=self.directory, prefix=".upload-", delete=False) as stream:
                temporary = Path(stream.name)
                remaining = size
                while remaining:
                    block = handler.rfile.read(min(1024*1024, remaining))
                    if not block:
                        raise self.error(400, "附件传输中断，请重新上传")
                    stream.write(block)
                    remaining -= len(block)
            with self.files_lock, self.service.db() as db:
                db.execute("BEGIN IMMEDIATE")
                if self.student(db, handler) != team_id:
                    raise self.error(401, "提交凭证已变更，请重新登录")
                if db.execute("SELECT COUNT(*) FROM project_files WHERE team_id=?", (team_id,)).fetchone()[0] >= FILE_COUNT:
                    raise self.error(409, "每队最多6个附件，请先删除旧附件")
                at = int(time.time()*1000)
                temporary.replace(self.directory / file_id)
                temporary = self.directory / file_id
                db.execute("INSERT INTO project_files VALUES (?,?,?,?,?,?)", (file_id, team_id, name, kind, size, at))
                db.execute("UPDATE project_submissions SET updated_at=? WHERE team_id=?", (at, team_id))
                value = {"ok": True, **self.mine(db, team_id)}
            temporary = None
            handler.respond(200, value)
        finally:
            if temporary:
                temporary.unlink(missing_ok=True)
            self.upload_slots.release()

    def file_download(self, handler, file_id):
        with self.service.db() as db:
            row = db.execute("SELECT * FROM project_files WHERE id=?", (file_id,)).fetchone()
            if not row:
                raise self.error(404, "附件不存在")
            actor = self.service.account(db, handler.headers.get("Cookie", ""))
            if not actor or actor["role"] != "admin":
                if self.student(db, handler) != row["team_id"]:
                    raise self.error(403, "只能下载本队附件")
        try:
            stream = (self.directory / file_id).open("rb")
        except FileNotFoundError:
            raise self.error(404, "附件文件不存在，请联系老师")
        with stream:
            handler.headers_out(200, "application/octet-stream", row["size"], extra={"Content-Disposition": "attachment; filename=project-file; filename*=UTF-8''" + quote(row["name"], safe="")})
            while block := stream.read(1024*1024):
                handler.wfile.write(block)

    @staticmethod
    def safe_part(value):
        cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value).strip(" .")
        return cleaned[:80] or "作品"

    @classmethod
    def safe_filename(cls, value):
        suffix = Path(value).suffix.lower()
        return cls.safe_part(Path(value).stem) + suffix

    @staticmethod
    def csv_safe(value):
        value = str(value)
        return "'" + value if value.lstrip().startswith(("=", "+", "-", "@")) or value.startswith(("\t", "\r", "\n")) else value

    def download(self, handler, body):
        ids, kind = body.get("teamIds"), body.get("kind", "all")
        if not isinstance(ids, list) or not ids or len(ids) > 999 or any(not isinstance(i, str) for i in ids) or len(set(ids)) != len(ids):
            raise self.error(400, "请选择至少一支队伍，队伍编号不能重复")
        if not isinstance(kind, str) or kind not in {"all", "ppt", "web"}:
            raise self.error(400, "下载类型不正确")
        with self.service.db() as db:
            self.admin(db, handler)
            teams = [row for row in self.rows(db) if row["id"] in ids]
        if len(teams) != len(ids):
            raise self.error(400, "所选队伍已变化，请刷新后重试")
        if not self.download_slots.acquire(blocking=False):
            raise self.error(503, "下载打包繁忙，请稍后重试")
        try:
            handler.connection.settimeout(180)
            with tempfile.TemporaryFile(dir=self.directory, prefix=".bundle-") as stream:
                manifest = io.StringIO(newline="")
                writer = csv.writer(manifest)
                writer.writerow(["队号", "队伍", "作品", "演示网址", "附件数量", "提交状态"])
                with self.files_lock, zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as package:
                    for team in teams:
                        sub = team["submission"] or {}
                        folder = f'{team["number"]:02d}_{self.safe_part(team["name"])}'
                        selected = [f for f in team["files"] if kind == "all" or f["kind"] == kind]
                        writer.writerow([self.csv_safe(value) for value in [team["number"], team["name"], sub.get("title", ""), sub.get("demoUrl", ""), len(selected), "已提交" if team["submitted"] else "未提交"]])
                        description = (f'第{team["number"]:02d}队：{team["name"]}\n作品：{sub.get("title") or team["project"] or "未命名"}\n说明：{sub.get("summary", "")}\n演示网址：{sub.get("demoUrl", "")}\n'
                                       '在线网址仅保存链接，完整离线运行请使用同学上传的HTML或ZIP；引用外部服务的作品仍需联网。\n')
                        package.writestr(folder + "/作品说明.txt", description.encode("utf-8-sig"))
                        if kind in {"all", "web"} and sub.get("demoUrl"):
                            package.writestr(folder + "/打开在线演示.url", ("[InternetShortcut]\r\nURL=" + sub["demoUrl"] + "\r\n").encode("utf-8-sig"))
                        for index, file in enumerate(selected, 1):
                            source = self.directory / file["id"]
                            if not source.is_file():
                                raise self.error(409, "有附件缺失，请联系老师核对后重试")
                            category = "PPT" if file["kind"] == "ppt" else "网页与游戏"
                            package.write(source, folder + f'/{category}/{index:02d}_' + self.safe_filename(file["name"]))
                    package.writestr("提交清单.csv", manifest.getvalue().encode("utf-8-sig"))
                size = stream.tell()
                stream.seek(0)
                filename = f"初一黑客松_{len(teams)}组_{kind}.zip"
                handler.headers_out(200, "application/zip", size, extra={"Content-Disposition": "attachment; filename=chuyi-projects.zip; filename*=UTF-8''" + quote(filename, safe="")})
                while block := stream.read(1024*1024):
                    handler.wfile.write(block)
        finally:
            self.download_slots.release()
