"""Final ballots use four 25-point dimensions, six-judge sums and a 600-point MVP."""
import csv
import io
import json
import unittest

from app import EventService
import test_stages as stage_helpers


class FinalTotalsTests(unittest.TestCase):
    setUp = stage_helpers.TwoStageTests.setUp
    tearDown = stage_helpers.TwoStageTests.tearDown
    team = stage_helpers.TwoStageTests.team
    invitation = stage_helpers.TwoStageTests.invitation
    settings = stage_helpers.TwoStageTests.settings
    score = stage_helpers.TwoStageTests.score
    roadshow = stage_helpers.TwoStageTests.roadshow
    qualify = stage_helpers.TwoStageTests.qualify

    def start_final(self, judges=6):
        ids, _, _ = self.roadshow(6)
        self.qualify()
        clients = [self.invitation("final", f"PRIVATE FINAL {i + 1}")[0] for i in range(judges)]
        self.settings(activeStage="final", finalScoringOpen=True)
        return ids, clients

    def test_five_to_six_sums_partial_leaders_mvp_tie_and_csv(self):
        ids, judges = self.start_final()
        initial = self.public.get("/api/board")[1]
        self.assertEqual(initial["config"]["finalMinJudges"], 6)
        self.assertEqual(initial["config"]["finalJudgeLimit"], 6)
        self.assertEqual(initial["config"]["finalAwardMax"], 150)
        self.assertEqual(initial["config"]["finalMvpMax"], 600)
        self.assertEqual([d["max"] for d in initial["config"]["finalDimensions"]], [25] * 4)
        self.assertTrue(all(t["finalTotal"] is None and t["finalTotals"] == [None] * 4 for t in initial["finalists"]))
        self.assertIsNone(initial["mvp"]["score"])
        values = [[25] * 4, [25] * 4] + [[20] * 4] * 4
        for judge in judges[:5]:
            for team, scores in zip(ids, values):
                self.assertEqual(self.score(judge, team, scores, "final")[0], 200)
        partial = self.public.get("/api/board")[1]
        self.assertTrue(all(t["finalScores"] == [None] * 4 and not t["finalReady"] for t in partial["finalists"]))
        self.assertEqual(partial["finalists"][0]["finalTotals"], [125] * 4)
        self.assertEqual(partial["finalists"][0]["finalTotal"], 500)
        self.assertEqual(partial["mvp"]["score"], 500)
        self.assertEqual(partial["mvp"]["leaders"], ids[:2])
        self.assertTrue(partial["mvp"]["tied"])
        self.assertFalse(partial["mvp"]["ready"])
        self.assertTrue(all(a["score"] == 125 and a["max"] == 150 and not a["ready"] for a in partial["awards"]))
        # A finished leading team cannot authorize awards while any other finalist has only five judges.
        self.assertEqual(self.score(judges[5], ids[0], values[0], "final")[0], 200)
        self.settings(finalScoringOpen=False)
        self.assertEqual(self.admin.post("/api/admin/awards", {"awardId": "mvp", "teamId": ids[0]})[0], 409)
        self.settings(finalScoringOpen=True)
        for team, scores in zip(ids[1:], values[1:]):
            self.assertEqual(self.score(judges[5], team, scores, "final")[0], 200)
        complete = self.public.get("/api/board")[1]
        self.assertTrue(all(t["finalReady"] for t in complete["finalists"]))
        self.assertEqual(complete["finalists"][0]["finalScores"], [25] * 4)
        self.assertEqual(complete["finalists"][0]["finalTotals"], [150] * 4)
        self.assertEqual(complete["finalists"][0]["finalTotal"], 600)
        self.assertEqual(complete["mvp"]["score"], 600)
        self.assertEqual(complete["mvp"]["leaders"], ids[:2])
        self.assertFalse(complete["mvp"]["ready"])
        self.settings(finalScoringOpen=False)
        self.assertEqual(self.admin.post("/api/admin/awards", {"awardId": "mvp", "teamId": ids[2]})[0], 400)
        self.assertEqual(self.admin.post("/api/admin/awards", {"awardId": "mvp", "teamId": ids[1]})[0], 200)
        self.assertEqual(self.admin.post("/api/admin/awards", {"awardId": "creativity", "teamId": ids[0]})[0], 200)
        confirmed = self.public.get("/api/board")[1]
        self.assertEqual(confirmed["mvp"]["winner"], ids[1])
        self.assertTrue(confirmed["mvp"]["winnerConfirmed"])
        self.assertEqual(confirmed["awards"][0]["winner"], ids[0])
        rows = list(csv.DictReader(io.StringIO(self.admin.get("/api/admin/export")[1].decode("utf-8-sig"))))
        final_row = next(r for r in rows if r["阶段"] == "决赛" and r["队号"] == "1")
        self.assertEqual(float(final_row["决赛单评委总分"]), 100)
        self.assertEqual(float(final_row["团队MVP累计"]), 600)
        self.assertEqual(float(final_row["专项累计 · 最佳创意奖"]), 150)
        self.settings(finalScoringOpen=True)
        cleared = self.admin.get("/api/admin")[1]
        self.assertFalse(cleared["mvp"]["winnerConfirmed"])
        self.assertTrue(all(not a["winnerConfirmed"] for a in cleared["awards"]))

    def test_edit_draft_recusal_capacity_and_sum_precision(self):
        ids, judges = self.start_final(7)
        team = ids[0]
        self.assertEqual(self.score(judges[0], team, [20.1, 20.2, 20.3, 20.4], "final")[0], 200)
        row = self.public.get("/api/board")[1]["finalists"][0]
        self.assertEqual(row["finalTotal"], 81)
        self.assertEqual(row["finalTotals"], [20.1, 20.2, 20.3, 20.4])
        self.assertEqual(self.score(judges[1], team, [25] * 4, "final", "draft")[0], 200)
        self.assertEqual(self.public.get("/api/board")[1]["finalists"][0]["finalTotal"], 81)
        self.assertEqual(self.score(judges[0], team, [0] * 4, "final", "draft")[0], 409)
        self.assertEqual(self.score(judges[0], team, [25] * 4, "final")[0], 200)
        self.assertEqual(self.public.get("/api/board")[1]["finalists"][0]["finalTotal"], 100)
        for judge in judges[1:6]:
            self.assertEqual(self.score(judge, team, [25] * 4, "final")[0], 200)
        self.assertEqual(self.public.get("/api/board")[1]["finalists"][0]["finalTotal"], 600)
        self.assertEqual(self.score(judges[6], team, [25] * 4, "final")[0], 409)
        self.assertEqual(self.score(judges[0], team, [24] * 4, "final")[0], 200)
        self.assertEqual(self.public.get("/api/board")[1]["finalists"][0]["finalTotal"], 596)
        self.assertEqual(self.score(judges[0], team, [], "final", "recused")[0], 200)
        recused = self.public.get("/api/board")[1]["finalists"][0]
        self.assertEqual(recused["finalJudgeCount"], 5)
        self.assertEqual(recused["finalTotal"], 500)
        self.assertFalse(recused["finalReady"])
        self.assertEqual(self.score(judges[6], team, [25] * 4, "final")[0], 200)
        self.assertEqual(self.score(judges[0], team, [25] * 4, "final")[0], 409)
        for invalid in [[25.1] * 4, [100] * 4, [-1] * 4, [True] * 4, [float("nan")] * 4]:
            self.assertEqual(self.score(judges[6], team, invalid, "final")[0], 400)
        self.assertEqual(self.public.get("/api/board")[1]["finalists"][0]["finalTotal"], 600)
        self.assertEqual(self.admin.post("/api/admin/settings", {"finalMinJudges": 7})[0], 400)

    def test_partial_totals_mvp_privacy_and_restart(self):
        ids, judges = self.start_final(1)
        self.assertEqual(self.score(judges[0], ids[0], [25, 20, 15, 10], "final")[0], 200)
        self.assertEqual(self.admin.get("/api/admin")[1]["mvp"]["score"], 70)
        self.settings(finalResultsPublished=False)
        hidden = self.public.get("/api/board")[1]
        self.assertTrue(all(t["finalTotals"] == [None] * 4 and t["finalTotal"] is None and not t["finalReady"] for t in hidden["finalists"]))
        self.assertTrue(all(a["score"] is None and a["leaders"] == [] and not a["ready"] for a in [*hidden["awards"], hidden["mvp"]]))
        self.settings(finalResultsPublished=True, resultsPublished=False)
        hidden = self.public.get("/api/board")[1]
        self.assertEqual(hidden["finalists"], [])
        self.assertEqual(hidden["mvp"]["leaders"], [])
        self.assertIsNone(hidden["mvp"]["score"])
        self.assertNotIn("PRIVATE", json.dumps(hidden))
        previous = self.service
        self.service = EventService(data_dir=previous.data_dir, base_path=previous.base_path, origin=previous.origin, static_root=previous.root)
        self.server.service = self.service
        admin = self.admin.get("/api/admin")[1]
        self.assertEqual(admin["mvp"]["score"], 70)
        self.assertEqual(admin["finalists"][0]["finalTotals"], [25, 20, 15, 10])
        self.assertEqual(admin["config"]["finalScoringVersion"], 2)
        with self.service.db() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM audit WHERE action='final.scoring-version'").fetchone()[0], 1)

    def test_unmarked_historical_final_scores_fail_without_reinterpretation(self):
        ids, judges = self.start_final(1)
        self.assertEqual(self.score(judges[0], ids[0], [25] * 4, "final")[0], 200)
        with self.service.db() as db:
            db.execute("DELETE FROM settings WHERE key='finalScoringVersion'")
            db.execute("UPDATE final_scores SET scores_json='[100,80,60,40]',total_tenths=2800")
            original = tuple(db.execute("SELECT * FROM final_scores").fetchone())
        with self.assertRaisesRegex(RuntimeError, "explicit migration is required"):
            EventService(data_dir=self.service.data_dir, base_path=self.service.base_path, origin=self.service.origin, static_root=self.service.root)
        with self.service.db() as db:
            self.assertEqual(tuple(db.execute("SELECT * FROM final_scores").fetchone()), original)
            self.assertIsNone(db.execute("SELECT value FROM settings WHERE key='finalScoringVersion'").fetchone())


if __name__ == "__main__":
    unittest.main(verbosity=2)
