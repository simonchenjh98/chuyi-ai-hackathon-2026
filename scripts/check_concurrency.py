"""Disposable HTTP concurrency and score-correctness check (stdlib only).

Run from any directory: python -B scripts/check_concurrency.py
Uses its own temporary SQLite database and an ephemeral 127.0.0.1 HTTP port.
Never reads event credentials, connects to production, or changes project data.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import http.client
import json
import math
from pathlib import Path
import secrets
import sys
import tempfile
import threading
import time

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))
from app import EventHTTPServer, EventService, now_ms  # noqa: E402


class Check:
    def __init__(self, temporary):
        public = Path(temporary) / "public"
        public.mkdir()
        self.service = EventService(data_dir=Path(temporary) / "private", base_path="/qa",
                                    origin="http://127.0.0.1", static_root=public)
        self.server = EventHTTPServer(("127.0.0.1", 0), self.service)
        self.service.origin = f"http://127.0.0.1:{self.server.server_port}"
        self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.server_thread.start()
        self.timings = []
        self.timing_lock = threading.Lock()
        self.poll_errors = []
        with self.service.db() as db:
            admin_id = db.execute("SELECT id FROM accounts WHERE role='admin'").fetchone()[0]
            self.admin = self.session(db, admin_id)
            for number in range(1, 24):
                db.execute("INSERT INTO teams VALUES (?,?,?,?,?,?)",
                           (f"qa-team-{number}", number, f"QA Team {number}",
                            f"QA Project {number}", "现实问题", now_ms()))
        self.road = [self.judge("roadshow", i) for i in range(6)]
        self.final = [self.judge("final", i) for i in range(6)]

    @staticmethod
    def session(db, account_id):
        token = secrets.token_urlsafe(32)
        db.execute("INSERT INTO sessions VALUES (?,?,?)",
                   (hashlib.sha256(token.encode()).hexdigest(), account_id,
                    now_ms() + 3600_000))
        return "chuyi_session=" + token

    def judge(self, stage, index):
        with self.service.db() as db:
            account, _ = self.service.create_account(db, "judge", f"QA {stage} {index}", stage)
            return self.session(db, account["id"])

    def request(self, path, body=None, cookie="", expected=(200,)):
        method = "GET" if body is None else "POST"
        headers = {"Cookie": cookie}
        payload = None
        if body is not None:
            headers.update({"Origin": self.service.origin, "Content-Type": "application/json"})
            payload = json.dumps(body).encode()
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=20)
        start = time.perf_counter()
        status = 0
        try:
            conn.request(method, "/qa" + path, payload, headers)
            response = conn.getresponse()
            status = response.status
            data = json.loads(response.read())
            assert status in expected, f"{method} {path}: HTTP {status}: {data.get('error', '')}"
            return status, data
        finally:
            elapsed = (time.perf_counter() - start) * 1000
            group = "poll" if path == "/api/board" else "score" if path == "/api/score" else "control"
            with self.timing_lock:
                self.timings.append((group, elapsed, status))
            conn.close()

    def settings(self, **values):
        return self.request("/api/admin/settings", values, self.admin)[1]

    def board(self):
        return self.request("/api/board")[1]

    def score(self, cookie, number, values, stage, status="submitted", expected=(200,)):
        return self.request("/api/score", {"stage": stage, "teamId": f"qa-team-{number}",
                            "scores": [v / 10 for v in values], "status": status,
                            "feedback": "Synthetic concurrency fixture"}, cookie, expected)

    def phase(self, workers, tasks):
        """Run parallel writers while three independent screens poll the board."""
        stop = threading.Event()

        def poll():
            while not stop.is_set():
                try:
                    board = self.board()
                    assert len(board["teams"]) == 23
                    assert isinstance(board["serverTime"], int)
                except Exception as error:
                    self.poll_errors.append(str(error))
                    stop.set()
                stop.wait(0.025)

        polls = [threading.Thread(target=poll, daemon=True) for _ in range(3)]
        for thread in polls:
            thread.start()
        try:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                results = list(pool.map(lambda task: task(), tasks))
        finally:
            stop.set()
            for thread in polls:
                thread.join(timeout=25)
            assert not any(thread.is_alive() for thread in polls), "A board poll did not finish"
        assert not self.poll_errors, self.poll_errors
        return results

    @staticmethod
    def road_values(number, judge, revision=False):
        values = [190 - 3 * number + judge, 180 - 2 * number + judge,
                  170 - number + judge, 140 - number, 130 - number + judge,
                  90 - number + judge]
        if revision:
            values[0] += 3
            values[3] -= 1
        return values

    @staticmethod
    def final_values(number, judge, revision=False):
        values = [240 - 5 * number + judge, 230 - 3 * number + judge,
                  220 - 2 * number + judge, 210 - number + judge]
        if revision and number == 1:
            values[3] += 2
        return values

    @staticmethod
    def mean(tenths):
        return float((Decimal(sum(tenths)) / len(tenths) / 10).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP))

    def roadshow(self):
        self.settings(scoringOpen=True, minJudges=1, finalistCount=6)
        for revision in (False, True):
            def write(judge):
                for number in range(1, 24):
                    self.score(self.road[judge], number,
                               self.road_values(number, judge, revision), "roadshow")
            self.phase(6, [lambda j=j: write(j) for j in range(6)])
            board = self.board()
            for team in board["teams"]:
                number = team["number"]
                expected = self.mean([sum(self.road_values(number, j, revision)) for j in range(6)])
                assert team["judgeCount"] == 6, (number, team["judgeCount"])
                assert team["score"] == expected, (number, team["score"], expected)
                assert team["rank"] == number
        # A late draft must not replace an already submitted score.
        self.score(self.road[0], 1, [0] * 6, "roadshow", "draft", expected=(409,))
        self.settings(scoringOpen=False)
        _, qualified = self.request("/api/admin/qualify", {}, self.admin)
        assert qualified["qualification"]["teamIds"] == [f"qa-team-{n}" for n in range(1, 7)]

    def finals(self):
        self.settings(activeStage="final", finalScoringOpen=True, finalMinJudges=6)

        def write(judge):
            for number in range(1, 7):
                self.score(self.final[judge], number, self.final_values(number, judge), "final")
        self.phase(6, [lambda j=j: write(j) for j in range(6)])
        # Editing an existing ballot remains legal with all six slots occupied.
        self.phase(6, [lambda j=j: self.score(self.final[j], 1,
                    self.final_values(1, j, True), "final") for j in range(6)])
        board = self.board()
        for team in board["finalists"]:
            number = team["number"]
            ballots = [self.final_values(number, j, True) for j in range(6)]
            totals = [sum(v[i] for v in ballots) / 10 for i in range(4)]
            means = [self.mean([v[i] for v in ballots]) for i in range(4)]
            assert team["finalJudgeCount"] == 6 and team["finalReady"]
            assert team["finalTotals"] == totals, (number, team["finalTotals"], totals)
            assert team["finalScores"] == means, (number, team["finalScores"], means)
            assert team["finalTotal"] == sum(sum(v) for v in ballots) / 10
        first = next(t for t in board["finalists"] if t["number"] == 1)
        for index, award in enumerate(board["awards"]):
            assert award["max"] == 150 and award["ballotMax"] == 25
            assert award["leaders"] == ["qa-team-1"]
            assert award["score"] == first["finalTotals"][index]
        assert board["mvp"]["max"] == 600
        assert board["mvp"]["score"] == first["finalTotal"]
        assert board["mvp"]["leaders"] == ["qa-team-1"]
        self.settings(finalScoringOpen=False)
        for award in [*board["awards"], board["mvp"]]:
            self.request("/api/admin/awards", {"awardId": award["id"], "teamId": "qa-team-1"}, self.admin)
        confirmed = self.board()
        assert confirmed["mvp"]["winnerConfirmed"] and confirmed["mvp"]["winner"] == "qa-team-1"
        assert all(a["winnerConfirmed"] for a in confirmed["awards"])

    def six_ballot_race(self):
        self.settings(finalScoringOpen=True)
        extra = self.judge("final", 6)
        self.phase(6, [lambda c=c: self.score(c, 6, [], "final", "recused") for c in self.final])
        assert next(t for t in self.board()["finalists"] if t["number"] == 6)["finalJudgeCount"] == 0
        barrier = threading.Barrier(7)

        def contend(cookie):
            barrier.wait(timeout=15)
            return self.score(cookie, 6, [100, 110, 120, 130], "final", expected=(200, 409))[0]

        statuses = self.phase(7, [lambda c=c: contend(c) for c in [*self.final, extra]])
        assert statuses.count(200) == 6 and statuses.count(409) == 1, statuses
        team = next(t for t in self.board()["finalists"] if t["number"] == 6)
        assert team["finalJudgeCount"] == 6
        assert team["finalTotals"] == [60, 66, 72, 78]
        assert team["finalTotal"] == 276
        with self.service.db() as db:
            assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            assert db.execute("SELECT COUNT(*) FROM scores WHERE status='submitted'").fetchone()[0] == 138
            assert db.execute("SELECT COUNT(*) FROM final_scores WHERE status='submitted'").fetchone()[0] == 36

    def report(self):
        def stats(group):
            values = sorted(ms for kind, ms, status in self.timings if group is None or kind == group)
            return {"requests": len(values), "p95_ms": round(values[max(0, math.ceil(len(values) * .95) - 1)], 1),
                    "max_ms": round(values[-1], 1)}
        return {"ok": True, "scope": "temporary DB + loopback HTTP only", "teams": 23,
                "roadshow_judges": 6, "final_judges": 6, "unexpected_errors": 0,
                "checks": ["138 concurrent roadshow ballots + 138 revisions", "exact means + ranks",
                           "freeze top six", "36 final ballots + 6 revisions", "four totals + MVP",
                           "confirm five awards", "seven-way race admits exactly six", "SQLite integrity"],
                "all": stats(None), "scores": stats("score"), "board_polls": stats("poll"),
                "expected_conflicts": sum(status == 409 for _, _, status in self.timings)}

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.server_thread.join(timeout=5)


def main():
    with tempfile.TemporaryDirectory(prefix="chuyi-isolated-concurrency-") as temporary:
        check = Check(temporary)
        try:
            check.roadshow()
            check.finals()
            check.six_ballot_race()
            print(json.dumps(check.report(), ensure_ascii=False))
        finally:
            check.close()


if __name__ == "__main__":
    main()
