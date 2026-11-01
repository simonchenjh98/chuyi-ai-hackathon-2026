"""Two-stage eligibility, award selection and publication integration tests.

All HTTP requests target a disposable fixture server and temporary SQLite database.
"""
import csv
import io
import json
import unittest

from app import AWARDS, EventService
import test_api as helpers


class TwoStageTests(unittest.TestCase):
    setUp = helpers.APITests.setUp
    tearDown = helpers.APITests.tearDown
    team = helpers.APITests.team

    def invitation(self, stage="roadshow", name="Private judge"):
        status, result, _ = self.admin.post("/api/admin/invitations", {"role": "judge", "name": name, "judgeStage": stage})
        self.assertEqual(status, 200, result)
        client = helpers.Client(self.server)
        self.assertEqual(client.post("/api/login", {"role": "judge", "code": result["code"]})[0], 200)
        self.assertEqual(client.get("/api/session")[1]["judgeStage"], stage)
        return client, result

    def settings(self, **values):
        status, result, _ = self.admin.post("/api/admin/settings", values)
        self.assertEqual(status, 200, result)
        return result

    def score(self, judge, team, values, stage="roadshow", status="submitted"):
        return judge.post("/api/score", {"stage": stage, "teamId": team, "scores": values,
                                         "status": status, "feedback": "PRIVATE stage feedback"})

    def roadshow(self, count=8, last_values=None, limit=6):
        ids = [self.team(i + 1, f"Team {i+1}") for i in range(count)]
        judge, invitation = self.invitation()
        self.settings(minJudges=1, finalistCount=limit, scoringOpen=True)
        values = last_values or [10 - i for i in range(count)]
        for team_id, last in zip(ids, values):
            self.assertEqual(self.score(judge, team_id, [20, 20, 20, 15, 15, last])[0], 200)
        return ids, judge, invitation

    def qualify(self, **body):
        self.settings(scoringOpen=False)
        status, result, _ = self.admin.post("/api/admin/qualify", body)
        self.assertEqual(status, 200, result)
        return result

    def test_stage_isolation_validation_and_invitation_contract(self):
        road, _ = self.invitation("roadshow")
        final, _ = self.invitation("final")
        for client, own, other in [(road, "roadshow", "final"), (final, "final", "roadshow")]:
            self.assertEqual(client.get("/api/judge/" + own)[0], 200)
            self.assertEqual(client.get("/api/judge/" + other)[0], 403)
            self.assertEqual(client.get("/api/judge")[1]["stage"], own)
            self.assertEqual(client.get("/api/judge/invalid")[0], 400)
            self.assertEqual(self.score(client, "missing", [0] * 6, stage=other)[0], 403)
        for stage in [None, "invalid", [], {}, True, 1]:
            self.assertEqual(road.request("POST", "/api/score", {"stage": stage, "teamId": "missing"})[0], 400)
        self.assertEqual(road.request("POST", "/api/score", {"teamId": "missing"})[0], 400)
        self.assertEqual(road.request("POST", "/api/score", {"phase": "final", "stage": "roadshow"})[0], 400)
        for value in [[], {}, True, 1]:
            self.assertEqual(self.public.post("/api/login", {"role": value, "code": "invalid"})[0], 400)
            self.assertEqual(self.admin.post("/api/admin/invitations", {"role": value, "name": "invalid"})[0], 400)
        self.assertEqual(self.public.post("/api/score", {"stage": "final"})[0], 401)
        self.assertEqual(self.public.post("/api/admin/qualify", {})[0], 401)
        self.assertEqual(road.post("/api/admin/awards", {})[0], 403)
        self.assertEqual(self.admin.post("/api/admin/invitations", {"role": "judge", "name": "missing stage"})[0], 400)
        self.assertEqual(self.admin.post("/api/admin/invitations", {"role": "judge", "name": "bad stage", "judgeStage": []})[0], 400)
        self.assertEqual(self.admin.post("/api/admin/settings", {"activeStage": "final", "finalScoringOpen": True})[0], 409)
        self.assertEqual({j["judgeStage"] for j in self.admin.get("/api/admin")[1]["judges"]}, {"roadshow", "final"})

    def test_qualification_requires_every_team_then_freezes_six(self):
        ids, judge, _ = self.roadshow()
        self.assertEqual(self.admin.post("/api/admin/qualify", {})[0], 409)
        self.settings(scoringOpen=False, minJudges=2)
        self.assertFalse(self.admin.get("/api/admin")[1]["qualification"]["ready"])
        self.assertEqual(self.admin.post("/api/admin/qualify", {})[0], 409)
        self.settings(minJudges=1)
        result = self.qualify()
        self.assertEqual(set(result["qualification"]["teamIds"]), set(ids[:6]))
        self.assertEqual(result["qualification"]["version"], 1)
        self.assertTrue(result["qualification"]["confirmed"])
        self.assertEqual(self.admin.post("/api/admin/qualify", {})[0], 409)
        self.assertEqual(self.admin.post("/api/admin/settings", {"scoringOpen": True})[0], 409)
        self.assertEqual(self.admin.post("/api/admin/settings", {"finalistCount": 8})[0], 409)
        self.assertEqual(self.score(judge, ids[0], [0] * 6)[0], 409)
        self.assertEqual(self.admin.post("/api/admin/teams", {"number": 9, "name": "Late team"})[0], 409)
        self.assertEqual(self.admin.post("/api/admin/teams", {"id": ids[0], "number": 1, "name": "Renamed"})[0], 200)
        self.assertEqual(self.admin.post("/api/admin/unqualify", {})[0], 200)
        self.assertFalse(self.admin.get("/api/admin")[1]["qualification"]["confirmed"])
        self.settings(scoringOpen=True)
        self.assertEqual(self.score(judge, ids[0], [0] * 6)[0], 200)

    def test_six_eight_setting_and_boundary_tie_requires_legal_selection(self):
        ids, _, _ = self.roadshow(9, [10, 9, 8, 7, 6, 5, 5, 5, 0], 6)
        self.settings(scoringOpen=False)
        q = self.public.get("/api/board")[1]["qualification"]
        self.assertEqual(q["limit"], 6)
        self.assertEqual(q["cutoff"], 95)
        self.assertTrue(q["tieAtCutoff"])
        self.assertEqual(q["suggestedTeamIds"], [])
        self.assertEqual(self.admin.post("/api/admin/qualify", {})[0], 409)
        # A tie breaker may choose among the cutoff tie only, never drop a higher score.
        for invalid in [ids[1:7], ids[:5] + [ids[-1]], ids[:5] + [ids[0]], ids[:5]]:
            self.assertEqual(self.admin.post("/api/admin/qualify", {"teamIds": invalid})[0], 400)
        chosen = ids[:5] + [ids[7]]
        self.assertEqual(self.admin.post("/api/admin/qualify", {"teamIds": chosen})[0], 200)
        self.assertEqual(set(self.public.get("/api/board")[1]["qualification"]["teamIds"]), set(chosen))
        self.assertEqual(self.admin.post("/api/admin/unqualify", {})[0], 200)
        self.settings(finalistCount=8)
        self.assertEqual(self.admin.post("/api/admin/qualify", {})[0], 200)
        self.assertEqual(len(self.public.get("/api/board")[1]["finalists"]), 8)
        self.assertEqual(self.public.get("/api/board")[1]["qualification"]["version"], 2)
        for bad in [0, 7, True, "6", [], 6.0]:
            self.assertEqual(self.admin.post("/api/admin/settings", {"finalistCount": bad})[0], 400)

    def test_final_awards_threshold_ties_confirmation_reopen_and_privacy(self):
        ids, _, _ = self.roadshow()
        self.qualify()
        final1, _ = self.invitation("final", "PRIVATE FINAL 1")
        final2, invitation2 = self.invitation("final", "PRIVATE FINAL 2")
        self.settings(activeStage="final", finalScoringOpen=True, finalMinJudges=2)
        self.assertEqual(len(final1.get("/api/judge/final")[1]["teams"]), 6)
        self.assertEqual(self.score(final1, ids[6], [20] * 4, "final")[0], 403)
        # Two top teams tie on creativity and technology; first wins both remaining directions.
        scores = [[22, 23, 25, 24], [22, 23, 20, 19]] + [[15, 15, 15, 15]] * 4
        for team, values in zip(ids[:6], scores):
            self.assertEqual(self.score(final1, team, values, "final")[0], 200)
            self.assertEqual(self.score(final2, team, values, "final", "draft")[0], 200)
        self.assertTrue(all(t["finalScores"] == [None] * 4 for t in self.public.get("/api/board")[1]["finalists"]))
        self.assertEqual(self.public.get("/api/board")[1]["finalists"][0]["finalTotals"], scores[0])
        self.assertEqual(self.public.get("/api/board")[1]["mvp"]["score"], 94)
        self.assertEqual(self.admin.post("/api/admin/awards", {"awardId": AWARDS[0]["id"], "teamId": ids[0]})[0], 409)
        self.settings(finalScoringOpen=False)
        self.assertEqual(self.admin.post("/api/admin/awards", {"awardId": AWARDS[0]["id"], "teamId": ids[0]})[0], 409)
        self.settings(finalScoringOpen=True)
        for team, values in zip(ids[:6], scores):
            self.assertEqual(self.score(final2, team, values, "final")[0], 200)
        self.assertEqual(self.score(final2, ids[0], [0] * 4, "final", "draft")[0], 409)
        self.settings(finalScoringOpen=False)
        board = self.public.get("/api/board")[1]
        self.assertEqual({a["id"] for a in board["awards"]}, {"creativity", "technology", "potential", "care"})
        self.assertEqual(board["awards"][0]["leaders"], ids[:2])
        self.assertTrue(board["awards"][0]["tied"])
        self.assertTrue(all(a["winner"] is None for a in board["awards"]))
        self.assertEqual(self.admin.post("/api/admin/awards", {"awardId": AWARDS[0]["id"], "teamId": ids[2]})[0], 400)
        for award in AWARDS:
            self.assertEqual(self.admin.post("/api/admin/awards", {"awardId": award["id"], "teamId": ids[0]})[0], 200)
        self.assertTrue(all(a["winner"] == ids[0] and a["winnerConfirmed"] for a in self.public.get("/api/board")[1]["awards"]))
        # Revocation ends access, preserving already accepted submitted score evidence.
        self.assertEqual(self.admin.post("/api/admin/revoke", {"role": "judge", "id": invitation2["id"]})[0], 200)
        self.assertEqual(final2.get("/api/judge/final")[0], 401)
        self.assertEqual(self.public.get("/api/board")[1]["finalists"][0]["finalJudgeCount"], 2)
        self.settings(finalResultsPublished=False)
        hidden = self.public.get("/api/board")[1]
        self.assertTrue(all(t["finalScores"] == [None] * 4 for t in hidden["finalists"]))
        self.assertTrue(all(t["finalTotals"] == [None] * 4 and t["finalTotal"] is None for t in hidden["finalists"]))
        self.assertTrue(all(a["leaders"] == [] and a["winner"] is None and a["score"] is None for a in hidden["awards"]))
        self.assertIsNone(hidden["mvp"]["score"])
        self.assertEqual(hidden["mvp"]["leaders"], [])
        self.assertTrue(self.admin.get("/api/admin")[1]["awards"][0]["winnerConfirmed"])
        self.settings(resultsPublished=False)
        hidden = self.public.get("/api/board")[1]
        self.assertEqual(hidden["finalists"], [])
        self.assertEqual(hidden["qualification"]["teamIds"], [])
        self.assertIsNone(hidden["qualification"]["cutoff"])
        self.assertFalse(hidden["qualification"]["confirmed"])
        self.assertTrue(all(a["leaders"] == [] and a["winner"] is None for a in hidden["awards"]))
        self.assertNotIn("PRIVATE", json.dumps(hidden))
        self.settings(finalScoringOpen=True, resultsPublished=True, finalResultsPublished=True)
        self.assertTrue(all(not a["winnerConfirmed"] for a in self.admin.get("/api/admin")[1]["awards"]))
        self.assertEqual(self.admin.post("/api/admin/unqualify", {})[0], 409)
        self.assertEqual(self.score(final1, ids[0], [25, 25, 25, 25], "final")[0], 200)
        for invalid in [[25.1, 0, 0, 0], [100, 0, 0, 0], [-0.1, 0, 0, 0], [0] * 6, [True, 0, 0, 0], [0.01, 0, 0, 0]]:
            self.assertEqual(self.score(final1, ids[0], invalid, "final")[0], 400)
        status, content, _ = self.admin.get("/api/admin/export")
        self.assertEqual(status, 200)
        rows = list(csv.DictReader(io.StringIO(content.decode("utf-8-sig"))))
        self.assertEqual({r["阶段"] for r in rows}, {"路演", "决赛"})
        self.assertTrue(all(r["路演总分"] == "" for r in rows if r["阶段"] == "决赛"))
        self.assertTrue(all(a["name"] in rows[0] for a in AWARDS))
        self.assertIn("团队MVP累计", rows[0])

    def test_zero_scores_recusal_and_half_up_averages(self):
        self.assertEqual(EventService.average_score(1, 4), 0.03)
        self.assertEqual(EventService.average_score(345, 4), 8.63)
        ids, road, _ = self.roadshow(6, [0] * 6)
        for team in ids:
            self.assertEqual(self.score(road, team, [0] * 6)[0], 200)
        self.assertTrue(all(t["score"] == 0 for t in self.public.get("/api/board")[1]["teams"]))
        self.qualify()
        final1, _ = self.invitation("final", "Zero judge 1")
        final2, _ = self.invitation("final", "Zero judge 2")
        self.settings(activeStage="final", finalScoringOpen=True, finalMinJudges=2)
        for team in ids:
            self.assertEqual(self.score(final1, team, [0] * 4, "final")[0], 200)
            self.assertEqual(self.score(final2, team, [0] * 4, "final")[0], 200)
        board = self.public.get("/api/board")[1]
        self.assertTrue(all(t["finalScores"] == [0, 0, 0, 0] for t in board["finalists"]))
        self.assertTrue(all(a["score"] == 0 and len(a["leaders"]) == 6 and a["tied"] for a in board["awards"]))
        self.assertEqual(self.score(final1, ids[0], [], "final", "recused")[0], 200)
        row = self.public.get("/api/board")[1]["finalists"][0]
        self.assertEqual(row["finalJudgeCount"], 1)
        self.assertEqual(row["finalScores"], [None] * 4)
        self.assertEqual(self.score(final1, ids[0], [0] * 4, "final", "draft")[0], 200)
        self.assertEqual(self.score(final1, ids[0], [0] * 4, "final", ["submitted"])[0], 400)
        self.assertEqual(self.score(final1, ids[0], [0] * 4, "final")[0], 200)
        self.assertEqual(self.public.get("/api/board")[1]["finalists"][0]["finalScores"], [0, 0, 0, 0])

    def test_settings_are_atomic_and_restart_retains_qualification(self):
        ids, _, _ = self.roadshow()
        self.qualify()
        self.assertEqual(self.admin.post("/api/admin/settings", {"resultsPublished": False, "finalistCount": 8})[0], 409)
        self.assertTrue(self.admin.get("/api/admin")[1]["config"]["resultsPublished"])
        previous = self.service
        self.service = EventService(data_dir=previous.data_dir, base_path=previous.base_path, origin=previous.origin, static_root=previous.root)
        self.server.service = self.service
        self.assertEqual(self.public.get("/api/board")[1]["qualification"]["teamIds"], ids[:6])
        self.assertEqual(len(self.admin.get("/api/admin")[1]["judges"]), 1)
        with self.service.db() as db:
            actions = [row[0] for row in db.execute("SELECT action FROM audit")]
        self.assertIn("qualification.confirm", actions)


if __name__ == "__main__":
    unittest.main(verbosity=2)
