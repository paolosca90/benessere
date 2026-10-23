"""Test isolati del ponte Google Sheets, senza rete e senza dati reali."""
import sqlite3
import tempfile
import unittest
from pathlib import Path

from benessere import db
from sheets_bridge import apply_event


class SheetsBridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.conn = db.connect(Path(self.temp.name) / "test.db")

    def tearDown(self):
        self.conn.close()
        self.temp.cleanup()

    def test_crossfit_and_idempotency(self):
        payload = {
            "date": "2026-10-21",
            "type": "other",
            "duration_min": 60,
            "notes": "Allenamento artificiale di test.",
            "wod": {
                "name": "Fixture Test Barbell WOD",
                "score_type": "time",
                "score": "17:00",
                "scaling": "unspecified",
                "description": "Esercizio artificiale di test"
            }
        }
        saved = apply_event(self.conn, "workout_20261021_0800_crossfit", "workout", payload)
        self.assertEqual(saved["status"], "saved")
        self.assertEqual(apply_event(self.conn, "workout_20261021_0800_crossfit", "workout", payload)["status"], "duplicate")
        self.assertEqual(self.conn.execute("SELECT count(*) FROM workouts").fetchone()[0], 1)
        self.assertEqual(self.conn.execute("SELECT count(*) FROM wod_results").fetchone()[0], 1)
        self.assertEqual(self.conn.execute("SELECT score_value FROM wod_results").fetchone()[0], 1020)
        self.assertEqual(self.conn.execute("SELECT wod_result_id FROM workouts").fetchone()[0], saved["result"]["wod_result_id"])
        self.assertIsNone(self.conn.execute("SELECT rpe FROM workouts").fetchone()[0])

    def test_revision_updates_rpe_load_and_full_wod_without_duplication(self):
        original = {
            "date": "2026-10-23", "type": "other", "duration_min": 25.6667,
            "notes": "Team di 4, ripetizioni condivise.",
            "wod": {
                "name": "CrossFit team 4", "category": "custom", "score_type": "time",
                "score": "25:40", "description": "Descrizione provvisoria."
            },
        }
        a = apply_event(self.conn, "workout_team_original", "workout", original)
        wid = a["result"]["workout_id"]
        rid = a["result"]["wod_result_id"]
        b = apply_event(self.conn, "workout_team_blocks", "workout", {
            "update_of": "workout_team_original", "date": "2026-10-23",
            "start_time": "09:00", "duration_min": 25.6667,
            "notes": "Final 4 Way; 200 TTB, 200 DB Press, 200 Snatch, 400 DU, team 4",
            "blocks": [
                {"phase": "wod", "label": "1", "exercise": "Toes to Bar", "repetitions": 200},
                {"phase": "wod", "label": "2", "exercise": "Dumbbell Bench Press",
                 "repetitions": 200, "weight_kg": 22.5},
                {"phase": "wod", "label": "3", "exercise": "Hang Dumbbell Snatch",
                 "repetitions": 200, "weight_kg": 22.5},
                {"phase": "wod", "label": "4", "exercise": "Double Unders", "repetitions": 400},
            ],
        })
        self.assertEqual(b["result"]["blocks_updated"], 4)
        c = apply_event(self.conn, "workout_team_rpe4", "workout", {
            "update_of": "workout_team_original", "date": "2026-10-23", "rpe": 4,
            "wod": {
                "name": "Final 4 Way — Team of 4", "score_type": "time",
                "score": "25:40",
                "description": "200 TTB, 200 DB Bench Press, 200 Hang DB Snatch, 400 DU. Totali squadra di quattro.",
                "notes": "Risultato di squadra 25:40; ripetizioni individuali sconosciute."
            },
        })
        self.assertEqual(c["status"], "saved")
        self.assertEqual(c["result"]["rpe"], 4.0)
        self.assertEqual(c["result"]["load"], 61.6)
        self.assertEqual(c["result"]["blocks_updated"], 4)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM workouts").fetchone()[0], 1)
        workout = self.conn.execute("SELECT * FROM workouts WHERE id=?", (wid,)).fetchone()
        self.assertEqual(workout["rpe"], 4.0)
        self.assertEqual(workout["load"], 61.6)
        self.assertEqual(workout["start_time"], "09:00")
        self.assertEqual(workout["wod_result_id"], rid)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM workout_blocks WHERE workout_id=?", (wid,)).fetchone()[0], 4)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM wod_results").fetchone()[0], 1)
        self.assertEqual(self.conn.execute("SELECT name FROM wods").fetchone()[0], "Final 4 Way — Team of 4")
        self.assertEqual(self.conn.execute("SELECT score_display FROM wod_results WHERE id=?", (rid,)).fetchone()[0], "25:40")
        self.assertEqual(apply_event(self.conn, "workout_team_rpe4", "workout", {
            "update_of": "workout_team_original", "date": "2026-10-23", "rpe": 4
        })["status"], "duplicate")

    def test_rejects_invalid_rpe_on_revision(self):
        payload = {
            "date": "2026-10-23", "type": "other", "duration_min": 25,
            "notes": "Test only"
        }
        apply_event(self.conn, "workout_initial", "workout", payload)
        with self.assertRaisesRegex(ValueError, "RPE fuori intervallo"):
            apply_event(self.conn, "workout_bad_rpe", "workout", {
                "update_of": "workout_initial", "date": "2026-10-23", "rpe": 12
            })
        self.assertIsNone(self.conn.execute("SELECT rpe FROM workouts").fetchone()[0])

    def test_meal_and_idempotency(self):
        data = {
            "date": "2026-10-21", "time": "13:15", "meal": "lunch",
            "description": "Piatto di prova", "kcal": 510,
            "protein_g": 32, "carbs_g": 48, "fat_g": 18
        }
        self.assertEqual(apply_event(self.conn, "meal_01", "meal", data)["status"], "saved")
        self.assertEqual(apply_event(self.conn, "meal_01", "meal", data)["status"], "duplicate")
        self.assertEqual(self.conn.execute("SELECT count(*) FROM meals").fetchone()[0], 1)
        with self.assertRaisesRegex(ValueError, "Pasto gia presente"):
            apply_event(self.conn, "meal_02", "meal", data)

    def test_bad_data_does_not_insert(self):
        with self.assertRaises((ValueError, KeyError)):
            apply_event(self.conn, "bad_event", "workout",
                        {"date": "2026-10-21", "duration_min": -5, "type": "other"})
        self.assertEqual(self.conn.execute("SELECT count(*) FROM workouts").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
