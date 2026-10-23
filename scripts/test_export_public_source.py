import unittest
from scripts.export_public_source import allowed, findings


class PublicSourceContract(unittest.TestCase):
    def test_private_evidence_and_history_are_excluded(self):
        for path in ['.env', 'engine/.env.example', 'backend/fixtures/ektp.json',
                     'backend/app/datasets/forex_sample.json', 'engine/samples/source.pdf',
                     'engine/ektp/examples/customer.json', 'frontend/e2e/state.json',
                     'docs/private.xlsx', '.git/config', '../backend/app/main.py']:
            self.assertFalse(allowed(path), path)

    def test_application_source_and_synthetic_tests_are_selected(self):
        for path in ['backend/app/main.py', 'backend/app/configuration/migrations/0001_publications.sql',
                     'frontend/components/field-checks.tsx', 'backend/tests/test_field_checks.py']:
            self.assertTrue(allowed(path), path)
        self.assertFalse(allowed('backend/tests/test_platform.py'))

    def test_sensitive_shapes_are_blocked_without_echoing_values(self):
        for value in ['1' * 16, 'sk-' + 'x' * 25, 'llx-' + 'x' * 25,
                      '-----BEGIN ' + 'PRIVATE KEY-----']:
            result = findings('source.py', value.encode())
            self.assertTrue(result)
            self.assertNotIn(value, str(result))

    def test_normal_configuration_is_not_rejected(self):
        self.assertEqual(findings('source.py', b"digits = 16; model = 'configured-model'"), [])

    def test_invalid_encoding_is_blocked_instead_of_bypassing_inspection(self):
        self.assertEqual(findings('source.tsx', b'unsafe\xb7text'),
                         ['source must use UTF-8 encoding before it can be inspected'])

    def test_private_document_links_are_not_published(self):
        link = 'https://' + 'drive.google.com' + '/file/d/synthetic'
        self.assertIn('private document link requires configuration outside source',
                      findings('policy.json', link.encode()))


if __name__ == '__main__':
    unittest.main()
