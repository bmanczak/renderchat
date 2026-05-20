import pathlib
import unittest

from renderchat import derive_output_path, detect_platform, normalize_conversation_url


class UrlHandlingTests(unittest.TestCase):
    def test_normalizes_chatgpt_c_url_to_share_url(self):
        self.assertEqual(
            normalize_conversation_url("https://chatgpt.com/c/6a0c6c4e-6f98-838e-ae5d-befdb2ce2ef2"),
            "https://chatgpt.com/share/6a0c6c4e-6f98-838e-ae5d-befdb2ce2ef2",
        )

    def test_adds_scheme_before_platform_detection(self):
        url = "chatgpt.com/c/6a0c6c4e-6f98-838e-ae5d-befdb2ce2ef2"

        self.assertEqual(
            normalize_conversation_url(url),
            "https://chatgpt.com/share/6a0c6c4e-6f98-838e-ae5d-befdb2ce2ef2",
        )
        self.assertEqual(detect_platform(url), "chatgpt")

    def test_detects_supported_share_urls(self):
        self.assertEqual(detect_platform("https://chatgpt.com/share/abc"), "chatgpt")
        self.assertEqual(detect_platform("https://claude.ai/share/abc"), "claude")
        self.assertEqual(detect_platform("https://grok.com/share/abc"), "grok")
        self.assertEqual(detect_platform("https://x.ai/share/abc"), "grok")

    def test_derive_output_path_uses_normalized_conversation_id(self):
        self.assertEqual(
            derive_output_path("chatgpt.com/c/6a0c6c4e-6f98-838e-ae5d-befdb2ce2ef2"),
            pathlib.Path("chatgpt_6a0c6c4e-6f9.html"),
        )

    def test_rejects_unsupported_urls(self):
        with self.assertRaisesRegex(ValueError, "chatgpt.com/c"):
            detect_platform("https://example.com/share/abc")


if __name__ == "__main__":
    unittest.main()
