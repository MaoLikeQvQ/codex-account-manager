import unittest
from manager_parts.config_import import parse_provider_config


class ConfigImportTests(unittest.TestCase):
    config = '''model_provider = "krill"
model = "gpt-6-sol"
model_reasoning_effort = "high"
web_search = "live"
[model_providers.other]
base_url = "https://other.example/v1"
[model_providers.krill]
base_url = "https://api.example.com/codex/v1"
wire_api = "responses"
'''

    def test_selects_named_provider_and_only_imports_account_fields(self):
        result = parse_provider_config('```toml\n' + self.config + '```')
        self.assertEqual(result['provider_id'], 'krill')
        self.assertEqual(result['base_url'], 'https://api.example.com/codex/v1')
        self.assertEqual(result['default_model'], 'gpt-6-sol')
        self.assertEqual(result['ignored_fields'], ['web_search'])
        self.assertNotIn('web_search', result)

    def test_rejects_bad_configuration_without_echoing_input(self):
        for text in ['', 'secret-invalid', 'model_provider = "missing"',
                     self.config.replace('https://api.example.com/codex/v1', 'https://user:secret@example.com'),
                     self.config.replace('"responses"', '"chat"'),
                     self.config.replace('"high"', '"invalid"')]:
            with self.subTest(text=text):
                with self.assertRaises(ValueError) as error:
                    parse_provider_config(text)
                self.assertNotIn('secret', str(error.exception))

    def test_invalid_catalog_flags_and_secret_headers_are_rejected_without_echo(self):
        for addition in [
            'model_catalog_url = "https://user:secret@api.example.com/catalog"',
            'requires_openai_auth = "secret"',
            'http_headers = { "x-test" = 12 }',
            'request_max_retries = true',
        ]:
            with self.subTest(addition=addition), self.assertRaises(ValueError) as error:
                parse_provider_config(self.config + addition + "\n")
            self.assertNotIn('secret', str(error.exception))
        with self.assertRaises(ValueError):
            parse_provider_config(self.config + '[features]\napi_key_model_discovery = "true"\n')

    def test_unknown_fields_are_explicitly_reported_and_not_passed_through(self):
        result = parse_provider_config(self.config + 'experimental_bearer_token = "secret"\n[features]\nother = true\n')
        self.assertIn('model_providers.krill.experimental_bearer_token', result['ignored_fields'])
        self.assertIn('features.other', result['ignored_fields'])
        self.assertNotIn('secret', str(result))
