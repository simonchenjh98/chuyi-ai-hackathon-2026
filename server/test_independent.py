"""Independent final judging, device-scoped roadshow logins and scheduled opening."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import unittest
from unittest.mock import patch

from app import EventService
import test_api as api_helpers
import test_stages as stage_helpers

TEST_SHARED_CODE = "445566"
OPEN_AT = 1793509200000  # 2026-11-01 13:00 Asia/Shanghai.
CLOSE_AT = 1793520600000  # 2026-11-01 16:10 Asia/Shanghai.


class IndependentTests(unittest.TestCase):
    tearDown = api_helpers.APITests.tearDown
    team = api_helpers.APITests.team
    invitation = stage_helpers.TwoStageTests.invitation
    settings = stage_helpers.TwoStageTests.settings
    score = stage_helpers.TwoStageTests.score

    def setUp(self):
        api_helpers.APITests.setUp(self)
        self.settings(finalIndependent=True)

    def restart(self):
        previous = self.service
        self.service = EventService(data_dir=previous.data_dir, base_path=previous.base_path,
                                    origin=previous.origin, static_root=previous.root)
        self.server.service = self.service

    def shared_roadshow(self):
        (self.service.data_dir / "shared-login-codes.json").write_text(json.dumps({"judge": TEST_SHARED_CODE}), encoding="utf-8")
        self.restart()

    def device_login(self, token, client=None, code=TEST_SHARED_CODE):
        client = client or api_helpers.Client(self.server)
        return client, client.post("/api/login", {"role": "judge", "judgeStage": "roadshow", "code": code, "deviceToken": token})

    def test_device_identity_isolation_reuse_revocation_and_final_selection(self):
        self.shared_roadshow()
        a_token, b_token = "a" * 64, "b" * 64
        first, result = self.device_login(a_token)
        self.assertEqual(result[0], 200)
        self.assertNotIn("selectAccount", result[1])
        second, result = self.device_login(b_token)
        self.assertEqual(result[0], 200)
        self.assertNotEqual(first.get("/api/session")[1]["name"], second.get("/api/session")[1]["name"])
        team = self.team()
        self.settings(scoringOpen=True)
        self.assertEqual(self.score(first, team, [20, 20, 20, 15, 15, 10])[0], 200)
        self.assertEqual(self.score(second, team, [16, 16, 16, 12, 12, 8])[0], 200)
        self.assertEqual(self.public.get("/api/board")[1]["teams"][0]["score"], 90)
        self.assertEqual(first.get("/api/judge/roadshow")[1]["myScores"][0]["scores"], [20, 20, 20, 15, 15, 10])
        self.assertEqual(second.get("/api/judge/roadshow")[1]["myScores"][0]["scores"], [16, 16, 16, 12, 12, 8])
        self.restart()
        again, result = self.device_login(a_token)
        self.assertEqual(result[0], 200)
        self.assertEqual(again.get("/api/judge/roadshow")[1]["myScores"], first.get("/api/judge/roadshow")[1]["myScores"])
        with self.service.db() as db:
            mapping = db.execute("SELECT * FROM roadshow_devices WHERE device_hash=?", (hashlib.sha256(a_token.encode()).hexdigest(),)).fetchone()
            self.assertEqual(db.execute("SELECT COUNT(*) FROM roadshow_devices").fetchone()[0], 2)
            dump = "\n".join(db.iterdump())
            self.assertNotIn(a_token, dump)
        self.assertEqual(self.admin.post("/api/admin/revoke", {"id": mapping["account_id"], "role": "judge"})[0], 200)
        self.assertEqual(self.device_login(a_token)[1][0], 401)
        with self.service.db() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM roadshow_devices").fetchone()[0], 2)
        for invalid in ["short", "x" * 129, "!" * 64, None, 1]:
            self.assertEqual(self.device_login(invalid)[1][0], 400)
        self.assertEqual(self.device_login("c" * 64, code="wrong-code")[1][0], 401)
        # Final identity selection includes final judges only, even with auto-created roadshow people.
        final_ids = []
        for i in range(2):
            result = self.admin.post("/api/admin/invitations", {"role": "judge", "judgeStage": "final", "name": f"Final {i}"})
            final_ids.append(result[1]["id"])
        candidate = api_helpers.Client(self.server)
        selection = candidate.post("/api/login", {"role": "judge", "judgeStage": "final", "code": TEST_SHARED_CODE})
        self.assertEqual(selection[0], 200)
        self.assertEqual({a["id"] for a in selection[1]["accounts"]}, set(final_ids))
        self.assertTrue(all(a["judgeStage"] == "final" for a in selection[1]["accounts"]))

    def test_device_concurrent_login_creates_one_identity_and_allows_school_nat(self):
        self.shared_roadshow()
        token = "d" * 64
        with ThreadPoolExecutor(max_workers=8) as pool:
            replies = list(pool.map(lambda _: self.device_login(token)[1], range(8)))
        self.assertTrue(all(reply[0] == 200 and "selectAccount" not in reply[1] for reply in replies))
        self.assertEqual(len({reply[1]["name"] for reply in replies}), 1)
        for i in range(23):
            self.assertEqual(self.device_login(f"{i:064x}")[1][0], 200)
        with self.service.db() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM roadshow_devices").fetchone()[0], 24)
        # The same school IP must still be able to select and log in final judges.
        final_ids = []
        for i in range(2):
            invitation = self.admin.post("/api/admin/invitations", {"role": "judge", "judgeStage": "final", "name": f"NAT final {i}"})
            self.assertEqual(invitation[0], 200)
            final_ids.append(invitation[1]["id"])
        final = api_helpers.Client(self.server)
        selection = final.post("/api/login", {"role": "judge", "judgeStage": "final", "code": TEST_SHARED_CODE})
        self.assertEqual(selection[0], 200)
        self.assertEqual({a["id"] for a in selection[1]["accounts"]}, set(final_ids))
        selected = final.post("/api/login", {"role": "judge", "judgeStage": "final", "code": TEST_SHARED_CODE, "accountId": final_ids[0]})
        self.assertEqual(selected[0], 200)
        self.assertEqual(final.get("/api/session")[1]["judgeStage"], "final")

    def test_scheduled_open_exact_boundary_once_manual_reclose_and_restart(self):
        judge, _ = self.invitation("roadshow")
        with patch("app.now_ms", return_value=OPEN_AT - 1000):
            self.settings(scoringOpen=False, roadshowOpensAt=OPEN_AT)
            before = judge.get("/api/judge/status")[1]
            self.assertFalse(before["scoringOpen"])
            self.assertFalse(before["roadshowAutoOpenDone"])
            self.assertEqual(before["roadshowOpensAt"], OPEN_AT)
        with patch("app.now_ms", return_value=OPEN_AT):
            with ThreadPoolExecutor(max_workers=6) as pool:
                replies = list(pool.map(lambda _: api_helpers.Client(self.server).get("/api/board"), range(6)))
            self.assertTrue(all(reply[0] == 200 and reply[1]["config"]["scoringOpen"] for reply in replies))
            self.assertTrue(judge.get("/api/judge/status")[1]["roadshowAutoOpenDone"])
            self.settings(scoringOpen=False)
        self.restart()
        with patch("app.now_ms", return_value=OPEN_AT + 1000):
            self.assertFalse(judge.get("/api/judge/status")[1]["scoringOpen"])
            self.settings(roadshowOpensAt=OPEN_AT)
            self.assertFalse(judge.get("/api/judge/status")[1]["scoringOpen"])
            with self.service.db() as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM audit WHERE action='roadshow.auto-open'").fetchone()[0], 1)
            self.settings(roadshowOpensAt=None)
            self.assertIsNone(judge.get("/api/judge/status")[1]["roadshowOpensAt"])
        for invalid in [True, "1793509200000", -1, 1.5, [], 9007199254740992]:
            self.assertEqual(self.admin.post("/api/admin/settings", {"roadshowOpensAt": invalid})[0], 400)

    def test_schedule_survives_restart_before_deadline_and_due_setting_opens_now(self):
        with patch("app.now_ms", return_value=OPEN_AT - 1000):
            self.settings(scoringOpen=False, roadshowOpensAt=OPEN_AT)
            self.restart()
            self.assertFalse(self.public.get("/api/board")[1]["config"]["scoringOpen"])
        with patch("app.now_ms", return_value=OPEN_AT + 1000):
            self.assertTrue(self.public.get("/api/board")[1]["config"]["scoringOpen"])
            self.settings(scoringOpen=False, roadshowOpensAt=None)
            self.assertTrue(self.settings(roadshowOpensAt=OPEN_AT)["config"]["scoringOpen"])

    def test_roadshow_close_boundary_preserves_scores_but_final_and_upload_continue(self):
        team = self.team()
        second_team = self.team(2)
        road, _ = self.invitation("roadshow")
        final, _ = self.invitation("final")
        with patch("app.now_ms", return_value=CLOSE_AT - 1):
            self.settings(scoringOpen=True, finalScoringOpen=True, roadshowClosesAt=CLOSE_AT)
            self.assertEqual(self.score(road, team, [16, 16, 16, 12, 12, 8])[0], 200)
            self.assertEqual(self.score(road, second_team, [0] * 6, status="draft")[0], 200)
            status = road.get("/api/judge/status")[1]
            self.assertTrue(status["scoringOpen"])
            self.assertEqual(status["roadshowClosesAt"], CLOSE_AT)
            self.assertFalse(status["roadshowAutoCloseDone"])
            with self.service.db() as db:
                original = [tuple(row) for row in db.execute("SELECT * FROM scores ORDER BY team_id")]
        # The first request at the boundary is a denied revision. Its timer
        # transition must be committed even though the score transaction fails.
        with patch("app.now_ms", return_value=CLOSE_AT):
            self.assertEqual(self.score(road, team, [20, 20, 20, 15, 15, 10])[0], 409)
            with self.service.db() as db:
                self.assertEqual(json.loads(db.execute("SELECT value FROM settings WHERE key='scoringOpen'").fetchone()[0]), False)
                self.assertTrue(json.loads(db.execute("SELECT value FROM settings WHERE key='roadshowAutoCloseDone'").fetchone()[0]))
                self.assertEqual(db.execute("SELECT COUNT(*) FROM audit WHERE action='roadshow.auto-close'").fetchone()[0], 1)
            for target in [team, second_team]:
                for state in ["submitted", "draft", "recused"]:
                    self.assertEqual(self.score(road, target, [0] * 6, status=state)[0], 409)
            self.assertEqual(self.score(final, team, [25] * 4, "final")[0], 200)
            workbench = road.get("/api/judge/roadshow")[1]
            self.assertFalse(workbench["scoringOpen"])
            self.assertTrue(workbench["roadshowAutoCloseDone"])
            self.assertEqual(workbench["config"]["roadshowClosesAt"], CLOSE_AT)
            status, upload_session, _ = self.public.post("/api/submissions/login", {"teamId": team})
            self.assertEqual(status, 200)
            uploaded = self.public.request("POST", "/api/submissions/upload/web", raw=b"<!doctype html><h1>still open</h1>",
                                           headers={"Authorization": "Bearer " + upload_session["token"], "Content-Type": "application/octet-stream", "X-File-Name": "demo.html"})
            self.assertEqual(uploaded[0], 200)
        with patch("app.now_ms", return_value=CLOSE_AT + 1000):
            self.assertEqual(self.score(road, team, [0] * 6)[0], 409)
            with self.service.db() as db:
                self.assertEqual([tuple(row) for row in db.execute("SELECT * FROM scores ORDER BY team_id")], original)
            self.assertEqual(self.public.get("/api/board")[1]["teams"][0]["score"], 80)

    def test_close_wins_over_old_open_plan_and_admin_must_extend_or_clear(self):
        with patch("app.now_ms", return_value=CLOSE_AT + 1):
            state = self.settings(scoringOpen=False, roadshowOpensAt=OPEN_AT, roadshowClosesAt=CLOSE_AT)["config"]
            self.assertFalse(state["scoringOpen"])
            self.assertTrue(state["roadshowAutoCloseDone"])
            self.assertEqual(self.admin.post("/api/admin/settings", {"scoringOpen": True})[0], 409)
            state = self.settings(roadshowOpensAt=OPEN_AT + 1)["config"]
            self.assertFalse(state["scoringOpen"])
            with self.service.db() as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM audit WHERE action='roadshow.auto-open'").fetchone()[0], 0)
                self.assertEqual(db.execute("SELECT COUNT(*) FROM audit WHERE action='roadshow.auto-close'").fetchone()[0], 1)
            extended = self.settings(roadshowClosesAt=CLOSE_AT + 60_000, scoringOpen=True)["config"]
            self.assertTrue(extended["scoringOpen"])
            self.assertFalse(extended["roadshowAutoCloseDone"])
        with patch("app.now_ms", return_value=CLOSE_AT + 60_000):
            self.assertFalse(self.public.get("/api/board")[1]["config"]["scoringOpen"])
            cleared = self.settings(roadshowClosesAt=None, scoringOpen=True)["config"]
            self.assertTrue(cleared["scoringOpen"])
            self.assertFalse(cleared["roadshowAutoCloseDone"])
            self.assertIsNone(cleared["roadshowClosesAt"])
        for invalid in [True, "1793520600000", -1, 1.5, [], 9007199254740992]:
            self.assertEqual(self.admin.post("/api/admin/settings", {"roadshowClosesAt": invalid})[0], 400)

    def test_close_survives_restart_manual_early_close_and_concurrent_audit_once(self):
        road, _ = self.invitation("roadshow")
        with patch("app.now_ms", return_value=CLOSE_AT - 1000):
            self.settings(scoringOpen=True, roadshowOpensAt=OPEN_AT, roadshowClosesAt=CLOSE_AT)
            self.settings(scoringOpen=False)
            self.restart()
            state = road.get("/api/judge/status")[1]
            self.assertFalse(state["scoringOpen"])
            self.assertFalse(state["roadshowAutoCloseDone"])
        with patch("app.now_ms", return_value=CLOSE_AT):
            with ThreadPoolExecutor(max_workers=8) as pool:
                replies = list(pool.map(lambda _: api_helpers.Client(self.server).get("/api/board"), range(8)))
            self.assertTrue(all(reply[0] == 200 and not reply[1]["config"]["scoringOpen"] and reply[1]["config"]["roadshowAutoCloseDone"] for reply in replies))
            with self.service.db() as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM audit WHERE action='roadshow.auto-close'").fetchone()[0], 1)
        self.restart()
        with patch("app.now_ms", return_value=CLOSE_AT + 1000):
            state = self.settings(roadshowClosesAt=CLOSE_AT)["config"]
            self.assertTrue(state["roadshowAutoCloseDone"])
            self.assertFalse(state["scoringOpen"])
            self.assertEqual(self.admin.post("/api/admin/settings", {"scoringOpen": True})[0], 409)
            with self.service.db() as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM audit WHERE action='roadshow.auto-close'").fetchone()[0], 1)

    def test_all_teams_selectable_without_qualification_and_only_participants_gate_awards(self):
        ids = [self.team(i + 1) for i in range(23)]
        judges = [self.invitation("final", f"Final {i}")[0] for i in range(6)]
        road, _ = self.invitation("roadshow")
        self.settings(scoringOpen=True, finalScoringOpen=True, activeStage="roadshow", resultsPublished=False)
        self.assertEqual(len(judges[0].get("/api/judge/final")[1]["teams"]), 23)
        self.assertEqual(self.score(road, ids[22], [20, 20, 20, 15, 15, 10])[0], 200)
        self.assertEqual(self.score(judges[0], ids[22], [25] * 4, "final")[0], 200)
        partial = self.public.get("/api/board")[1]
        self.assertEqual(len(partial["finalists"]), 23)
        self.assertEqual(partial["finalParticipationCount"], 1)
        self.assertEqual(partial["mvp"]["score"], 100)
        self.assertTrue(all(t["score"] is None for t in partial["teams"]))
        self.assertEqual(self.admin.post("/api/admin/settings", {"finalIndependent": False})[0], 409)
        self.assertEqual(self.score(judges[0], ids[0], [25] * 4, "final", "draft")[0], 200)
        for judge in judges[1:]:
            self.assertEqual(self.score(judge, ids[22], [25] * 4, "final")[0], 200)
        self.settings(finalScoringOpen=False)
        board = self.public.get("/api/board")[1]
        self.assertEqual(board["finalParticipationCount"], 1)
        self.assertTrue(board["mvp"]["ready"])
        self.assertEqual(board["mvp"]["score"], 600)
        self.assertEqual(self.admin.post("/api/admin/awards", {"awardId": "mvp", "teamId": ids[22]})[0], 200)
        self.assertEqual(self.admin.post("/api/admin/unqualify", {})[0], 200)
        retained = self.public.get("/api/board")[1]
        self.assertEqual(retained["mvp"]["winner"], ids[22])
        self.assertEqual(retained["mvp"]["score"], 600)
        self.settings(finalResultsPublished=False)
        hidden = self.public.get("/api/board")[1]
        self.assertIsNone(hidden["mvp"]["score"])
        self.assertTrue(all(t["finalTotal"] is None for t in hidden["finalists"]))

    def test_legacy_award_fk_migrates_to_teams_without_losing_winner(self):
        ids = [self.team(i + 1) for i in range(6)]
        with self.service.db() as db:
            db.execute("INSERT INTO finalists VALUES (?,?,?,?,?)", (ids[0], 1, 100, 1, 0))
            db.execute("DROP TABLE award_winners")
            db.execute("CREATE TABLE award_winners (award_id TEXT PRIMARY KEY,team_id TEXT NOT NULL REFERENCES finalists(team_id),confirmed_at INTEGER NOT NULL)")
            db.execute("INSERT INTO award_winners VALUES ('mvp',?,0)", (ids[0],))
        self.restart()
        with self.service.db() as db:
            self.assertEqual(db.execute("PRAGMA foreign_key_list(award_winners)").fetchone()["table"], "teams")
            self.assertEqual(db.execute("SELECT team_id FROM award_winners WHERE award_id='mvp'").fetchone()[0], ids[0])
        self.assertEqual(self.admin.post("/api/admin/unqualify", {})[0], 200)
        with self.service.db() as db:
            self.assertEqual(db.execute("SELECT team_id FROM award_winners WHERE award_id='mvp'").fetchone()[0], ids[0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
