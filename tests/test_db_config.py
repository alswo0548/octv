"""로컬 개발 설정 우선순위와 비밀번호 보존 검사. 실제 DB는 check-db.py로 검사합니다."""

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backend.app import config


class DatabaseConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'backend').mkdir()
        (self.root / '.env').write_text(
            "POSTGRES_DB=test_db\nPOSTGRES_USER=test_user\n"
            "POSTGRES_PASSWORD='literal$HOME#test'\nPOSTGRES_PORT=5433\n",
            encoding='utf-8',
        )
        self.addCleanup(patch.stopall)
        patch.object(config, 'ROOT', self.root).start()
        patch.dict(os.environ, {}, clear=True).start()

    def test_root_settings_and_special_password_are_preserved(self):
        result = config.database_connect_kwargs()
        self.assertEqual(result['password'], 'literal$HOME#test')
        self.assertEqual(result['port'], 5433)
        self.assertEqual(result['dbname'], 'test_db')
        self.assertEqual(result['host'], '127.0.0.1')

    def test_explicit_backend_url_overrides_root(self):
        (self.root / 'backend/.env').write_text('DATABASE_URL=postgresql://example/test\n', encoding='utf-8')
        self.assertEqual(config.database_connect_kwargs()['conninfo'], 'postgresql://example/test')
        os.environ['DATABASE_URL'] = 'postgresql://environment/test'
        self.assertEqual(config.database_connect_kwargs()['conninfo'], 'postgresql://environment/test')

    def test_empty_url_falls_back_and_invalid_port_fails(self):
        (self.root / 'backend/.env').write_text('DATABASE_URL=\n', encoding='utf-8')
        self.assertEqual(config.database_connect_kwargs()['user'], 'test_user')
        os.environ['POSTGRES_PORT'] = '70000'
        with self.assertRaises(ValueError):
            config.database_connect_kwargs()


if __name__ == '__main__':
    unittest.main()
