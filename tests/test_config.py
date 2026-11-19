import unittest
from pathlib import Path

from blogger_crawler.config import ConfigError, load_simple_yaml, resolve_config_secrets
from helpers import workspace_tempdir


class ConfigTest(unittest.TestCase):
    def test_loads_simple_nested_yaml(self):
        with workspace_tempdir() as tmp:
            path = Path(tmp) / "config.yaml"
            path.write_text(
                "mysql:\n"
                "  host: localhost\n"
                "  port: 3306\n"
                "input:\n"
                "  blogger_list: data/blogger_list.xlsx\n",
                encoding="utf-8",
            )

            config = load_simple_yaml(path)

        self.assertEqual(config["mysql"]["host"], "localhost")
        self.assertEqual(config["mysql"]["port"], "3306")
        self.assertEqual(config["input"]["blogger_list"], "data/blogger_list.xlsx")

    def test_resolves_mysql_password_from_named_environment_variable(self):
        config = {"mysql": {"password_env": "MYSQL_PASSWORD"}}

        resolved = resolve_config_secrets(
            config,
            {"MYSQL_PASSWORD": "secret-value"},
        )

        self.assertEqual(resolved["mysql"]["password"], "secret-value")

    def test_resolves_optional_real_credentials_without_mutating_input(self):
        config = {
            "mysql": {"password_env": "MYSQL_PASSWORD"},
            "source": {
                "username_env": "SOURCE_USERNAME",
                "password_env": "SOURCE_PASSWORD",
            },
        }

        resolved = resolve_config_secrets(
            config,
            {
                "MYSQL_PASSWORD": "mysql-secret",
                "SOURCE_USERNAME": "source-user",
                "SOURCE_PASSWORD": "source-secret",
            },
        )

        self.assertEqual(resolved["mysql"]["password"], "mysql-secret")
        self.assertEqual(resolved["source"]["username"], "source-user")
        self.assertEqual(resolved["source"]["password"], "source-secret")
        self.assertNotIn("password", config["mysql"])
        self.assertNotIn("username", config["source"])
        self.assertNotIn("password", config["source"])

    def test_missing_named_environment_variable_fails_without_revealing_a_secret(self):
        config = {"mysql": {"password_env": "MYSQL_PASSWORD"}}

        with self.assertRaisesRegex(ConfigError, "MYSQL_PASSWORD") as raised:
            resolve_config_secrets(config, {})

        self.assertNotIn("secret-value", str(raised.exception))

    def test_literal_mysql_password_remains_supported_without_environment_reference(self):
        config = {"mysql": {"password": "legacy-value"}}

        resolved = resolve_config_secrets(config, {})

        self.assertEqual(resolved["mysql"]["password"], "legacy-value")


if __name__ == "__main__":
    unittest.main()
