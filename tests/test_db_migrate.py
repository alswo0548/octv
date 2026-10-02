"""Protect backup-before-mutation and already-current behavior without Docker."""
import importlib.util
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('db_cli', Path(__file__).resolve().parents[1] / 'scripts/db.py')
db = importlib.util.module_from_spec(spec)
spec.loader.exec_module(db)

class MigrationSafetyTests(unittest.TestCase):
    def test_current_schema_needs_no_backup_or_mutation(self):
        with patch('sys.argv', ['db.py', 'migrate']), patch.object(db, 'run_inside') as run, patch.object(db, 'backup') as backup:
            self.assertEqual(db.main(), 0)
            backup.assert_not_called()
            self.assertEqual(run.call_count, 1)
            self.assertNotIn('migrations/', run.call_args.args[0])

    def test_backup_failure_prevents_migration(self):
        with patch('sys.argv', ['db.py', 'migrate']), patch.object(db, 'run_inside', side_effect=subprocess.CalledProcessError(1, 'psql')) as run, patch.object(db, 'backup', side_effect=RuntimeError('backup failed')):
            self.assertEqual(db.main(), 1)
            self.assertEqual(run.call_count, 1)

    def test_backup_precedes_migration(self):
        events = []
        def run(command, **kwargs):
            if 'migrations/' not in command:
                raise subprocess.CalledProcessError(1, 'psql')
            events.append('migrate')
            self.assertIn('003_final_erd_uniques.sql', command)
            self.assertIn('backup_confirmed=1', command)
        with patch('sys.argv', ['db.py', 'migrate']), patch.object(db, 'run_inside', side_effect=run), patch.object(db, 'backup', side_effect=lambda: events.append('backup')):
            self.assertEqual(db.main(), 0)
            self.assertEqual(events, ['backup', 'migrate'])
