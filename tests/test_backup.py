import unittest
from pathlib import Path

from blogger_crawler.backup import build_mysqldump_command


class BackupTest(unittest.TestCase):
    def test_build_mysqldump_command_uses_a_defaults_file_and_utf8(self):
        command = build_mysqldump_command(
            Path("mysqldump.exe"),
            Path("mysql-client.cnf"),
            Path("backups/blogger_data.sql"),
            "blogger_data",
        )

        self.assertEqual(command[0], "mysqldump.exe")
        self.assertIn("--defaults-extra-file=mysql-client.cnf", command)
        self.assertIn("--single-transaction", command)
        self.assertIn("--default-character-set=utf8mb4", command)
        self.assertIn("--result-file=backups\\blogger_data.sql", command)
        self.assertEqual(command[-1], "blogger_data")


if __name__ == "__main__":
    unittest.main()
