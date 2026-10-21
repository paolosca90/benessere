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
