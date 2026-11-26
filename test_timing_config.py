import tomllib
import unittest

from manager_parts.timing_config import configure_timing


class TimingConfigTests(unittest.TestCase):
    endpoint = "http://127.0.0.1:8787/api/timing/otlp"

    def test_adds_local_json_export_without_changing_provider(self):
        original = 'model = "example"\n\n[model_providers.local]\nbase_url = "https://example.com/v1"\n'
        result, status = configure_timing(original, self.endpoint)
        parsed = tomllib.loads(result)
        self.assertEqual(status, "configured")
        self.assertEqual(parsed["otel"]["exporter"], {
            "otlp-http": {"endpoint": self.endpoint, "protocol": "json"},
        })
        self.assertFalse(parsed["otel"]["log_user_prompt"])
        self.assertEqual(parsed["model_providers"], tomllib.loads(original)["model_providers"])
        self.assertTrue(result.startswith(original))
        self.assertEqual(configure_timing(result, self.endpoint), (result, "configured"))

    def test_updates_disabled_exporter_and_preserves_other_otel_settings(self):
        original = '''model = "example"
[otel]
exporter = "none"
log_user_prompt = true
environment = "development"
[otel.trace_exporter.otlp-http]
endpoint = "https://traces.example.com"
protocol = "binary"
[otel.metrics_exporter.otlp-http]
endpoint = "https://metrics.example.com"
protocol = "json"
[features]
test = true
'''
        result, status = configure_timing(original, self.endpoint)
        before, after = tomllib.loads(original), tomllib.loads(result)
        self.assertEqual(status, "configured")
        for key in ("trace_exporter", "metrics_exporter", "environment"):
            self.assertEqual(after["otel"][key], before["otel"][key])
        self.assertEqual(after["features"], {"test": True})
        self.assertFalse(after["otel"]["log_user_prompt"])

    def test_preserves_external_and_unrelated_loopback_exporters_verbatim(self):
        for exporter in [
            '"statsig"',
            '{ otlp-http = { endpoint = "https://otel.example.com/v1/logs", protocol = "json" } }',
            '{ otlp-http = { endpoint = "http://127.0.0.1:4318/v1/logs", protocol = "json" } }',
            '{ otlp-grpc = { endpoint = "http://127.0.0.1:4317" } }',
        ]:
            with self.subTest(exporter=exporter):
                original = f'# Keep exactly\n[otel]\nexporter = {exporter}\nlog_user_prompt = true\n'
                self.assertEqual(configure_timing(original, self.endpoint), (original, "external_exporter"))

    def test_updates_previous_manager_endpoint(self):
        original = '''[otel.exporter.otlp-http]
endpoint = "http://127.0.0.1:8799/api/timing/otlp"
protocol = "json"
'''
        result, status = configure_timing(original, self.endpoint)
        self.assertEqual(status, "configured")
        self.assertEqual(tomllib.loads(result)["otel"]["exporter"]["otlp-http"]["endpoint"], self.endpoint)

    def test_inline_otel_table_keeps_other_top_level_fields(self):
        original = 'otel = { exporter = "none", environment = "local" }\nmodel = "example"\n'
        result, status = configure_timing(original, self.endpoint)
        self.assertEqual(status, "configured")
        self.assertEqual(tomllib.loads(result)["model"], "example")
        self.assertEqual(tomllib.loads(result)["otel"]["environment"], "local")

    def test_multiline_strings_and_dotted_otel_keys_do_not_damage_unrelated_content(self):
        original = '''instructions = """Keep this example:
[otel]
exporter = "none"
"""
otel.exporter = "none"
otel.environment = "local"
[features]
test = true
'''
        result, status = configure_timing(original, self.endpoint)
        before, after = tomllib.loads(original), tomllib.loads(result)
        self.assertEqual(status, "configured")
        self.assertEqual(after["instructions"], before["instructions"])
        self.assertEqual(after["features"], before["features"])
        self.assertEqual(after["otel"]["environment"], "local")

    def test_quoted_otel_headers_and_multiline_exporter_are_supported(self):
        original = '''["otel"] # disabled locally
exporter = {
}
'''
        # Inline tables cannot span lines in TOML; the parser must reject it
        # before returning a configuration that would fail Codex startup.
        with self.assertRaises(ValueError):
            configure_timing(original, self.endpoint)
        original = '["otel"] # disabled locally\nexporter = "none"\nenvironment = "local"\n'
        result, status = configure_timing(original, self.endpoint)
        self.assertEqual(status, "configured")
        self.assertEqual(tomllib.loads(result)["otel"]["environment"], "local")

    def test_rejects_invalid_toml_and_non_loopback_endpoints(self):
        with self.assertRaises(ValueError):
            configure_timing('[otel\n', self.endpoint)
        for endpoint in ["https://remote.example.com/v1/logs", "http://0.0.0.0:8787/api/timing/otlp", "http://user:secret@127.0.0.1:8787/api/timing/otlp"]:
            with self.subTest(endpoint=endpoint), self.assertRaises(ValueError):
                configure_timing('', endpoint)
