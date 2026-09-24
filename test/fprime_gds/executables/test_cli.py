import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fprime_gds.executables.cli import ConfigDrivenParser


class TestConfigDrivenParserDefaultConfiguration(unittest.TestCase):
    """Tests for ConfigDrivenParser's (global) default configuration resolution

    Covers get_default_configuration()/set_default_configuration() precedence (-c/--config >
    FPRIME_GDS_CONFIG_PATH > built-in default) and the fact that set_default_configuration() no
    longer mutates os.environ (so it does not affect child processes that inherit the
    environment).
    """

    def setUp(self):
        # ConfigDrivenParser's default-configuration state is class (global) state; snapshot and
        # restore it so tests do not leak into each other or into other test modules.
        self._orig_default_path = ConfigDrivenParser.DEFAULT_CONFIGURATION_PATH
        self._orig_explicit = ConfigDrivenParser._DEFAULT_CONFIGURATION_EXPLICIT

    def tearDown(self):
        ConfigDrivenParser.DEFAULT_CONFIGURATION_PATH = self._orig_default_path
        ConfigDrivenParser._DEFAULT_CONFIGURATION_EXPLICIT = self._orig_explicit

    def test_default_configuration_without_env_var(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(ConfigDrivenParser.DEFAULT_CONFIGURATION_PATH_ENV, None)
            self.assertEqual(
                ConfigDrivenParser.get_default_configuration(),
                Path("fprime-gds.yml"),
            )

    def test_env_var_overrides_built_in_default(self):
        with mock.patch.dict(
            os.environ,
            {ConfigDrivenParser.DEFAULT_CONFIGURATION_PATH_ENV: "/tmp/custom.yml"},
        ):
            self.assertEqual(
                ConfigDrivenParser.get_default_configuration(), Path("/tmp/custom.yml")
            )

    def test_empty_env_var_is_treated_as_unset(self):
        # An empty FPRIME_GDS_CONFIG_PATH (e.g. from `export FPRIME_GDS_CONFIG_PATH=`) must not
        # resolve to Path(""), i.e. the current working directory.
        with mock.patch.dict(
            os.environ, {ConfigDrivenParser.DEFAULT_CONFIGURATION_PATH_ENV: ""}
        ):
            self.assertEqual(
                ConfigDrivenParser.get_default_configuration(),
                ConfigDrivenParser.DEFAULT_CONFIGURATION_PATH,
            )

    def test_set_default_configuration_wins_over_env_var(self):
        with mock.patch.dict(
            os.environ,
            {ConfigDrivenParser.DEFAULT_CONFIGURATION_PATH_ENV: "/tmp/from-env.yml"},
        ):
            ConfigDrivenParser.set_default_configuration(Path("/tmp/explicit.yml"))
            self.assertEqual(
                ConfigDrivenParser.get_default_configuration(),
                Path("/tmp/explicit.yml"),
            )
            # set_default_configuration() must not mutate the environment: the variable should
            # remain visible (e.g. to child processes that inherit os.environ).
            self.assertEqual(
                os.environ[ConfigDrivenParser.DEFAULT_CONFIGURATION_PATH_ENV],
                "/tmp/from-env.yml",
            )


class TestConfigDrivenParserHandleArguments(unittest.TestCase):
    """Tests for ConfigDrivenParser.handle_arguments()'s explicit-configuration detection

    handle_arguments() must decide whether a configuration file was explicitly requested using
    the `arguments` actually supplied to the parser (or the environment variable), not sys.argv,
    since a caller such as the pytest fixture in pytest_integration.py drives this parser with an
    argument list that differs from sys.argv (which holds pytest's own command line).
    """

    def setUp(self):
        self._orig_default_path = ConfigDrivenParser.DEFAULT_CONFIGURATION_PATH
        self._orig_explicit = ConfigDrivenParser._DEFAULT_CONFIGURATION_EXPLICIT

    def tearDown(self):
        ConfigDrivenParser.DEFAULT_CONFIGURATION_PATH = self._orig_default_path
        ConfigDrivenParser._DEFAULT_CONFIGURATION_EXPLICIT = self._orig_explicit

    def _make_args(self, config_path):
        import argparse

        return argparse.Namespace(config=Path(config_path))

    def test_missing_config_not_explicit_is_ignored(self):
        # No -c/--config in the parsed `arguments`, and no environment override: a missing
        # default configuration file is not an error.
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(ConfigDrivenParser.DEFAULT_CONFIGURATION_PATH_ENV, None)
            args = self._make_args("does-not-exist.yml")
            result = ConfigDrivenParser().handle_arguments(
                args, arguments=["--foo", "bar"]
            )
            self.assertEqual(result.config_values, {})

    def test_missing_config_explicit_via_arguments_raises(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(ConfigDrivenParser.DEFAULT_CONFIGURATION_PATH_ENV, None)
            args = self._make_args("does-not-exist.yml")
            with self.assertRaises(ValueError):
                ConfigDrivenParser().handle_arguments(
                    args, arguments=["--config", "does-not-exist.yml"]
                )

    def test_missing_config_explicit_via_env_var_raises(self):
        # A mistyped/missing FPRIME_GDS_CONFIG_PATH must fail loudly rather than silently falling
        # back to built-in defaults.
        with mock.patch.dict(
            os.environ,
            {ConfigDrivenParser.DEFAULT_CONFIGURATION_PATH_ENV: "does-not-exist.yml"},
        ):
            args = self._make_args("does-not-exist.yml")
            with self.assertRaises(ValueError):
                ConfigDrivenParser().handle_arguments(args, arguments=["--foo", "bar"])

    def test_sys_argv_is_not_consulted(self):
        # Regression test: a driving tool's own sys.argv (e.g. pytest's `-c pytest.ini`) must not
        # be mistaken for an explicit --config to this parser.
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(ConfigDrivenParser.DEFAULT_CONFIGURATION_PATH_ENV, None)
            args = self._make_args("does-not-exist.yml")
            with mock.patch("sys.argv", ["pytest", "-c", "pytest.ini"]):
                result = ConfigDrivenParser().handle_arguments(
                    args, arguments=["--foo", "bar"]
                )
            self.assertEqual(result.config_values, {})

    def test_existing_config_file_is_loaded(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "config.yml"
            config_path.write_text("command-line-options:\n  logs: /tmp/logs\n")
            args = self._make_args(str(config_path))
            result = ConfigDrivenParser().handle_arguments(
                args, arguments=["--config", str(config_path)]
            )
            self.assertEqual(
                result.config_values, {"command-line-options": {"logs": "/tmp/logs"}}
            )


if __name__ == "__main__":
    unittest.main()
