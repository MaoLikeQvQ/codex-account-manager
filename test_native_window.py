"""Check click-through behavior without opening or changing account data."""
import importlib.util
import sys
import unittest
from unittest.mock import patch

from native_window import enable_first_mouse


class NativeWindowTests(unittest.TestCase):
    def test_non_macos_does_not_load_the_cocoa_backend(self):
        with patch('native_window.sys.platform', 'linux'):
            with patch('builtins.__import__', side_effect=AssertionError('native import on HTTP-only host')):
                enable_first_mouse()

    @unittest.skipUnless(sys.platform == 'darwin' and importlib.util.find_spec('webview'),
                         'macOS pywebview runtime is not installed')
    def test_native_webview_accepts_the_first_mouse_after_repeated_setup(self):
        import AppKit
        import WebKit
        from webview.platforms.cocoa import BrowserView

        enable_first_mouse()
        enable_first_mouse()
        view = BrowserView.WebKitHost.alloc().initWithFrame_configuration_(
            AppKit.NSMakeRect(0, 0, 100, 100), WebKit.WKWebViewConfiguration.new(),
        )
        self.assertTrue(view.acceptsFirstMouse_(None))
        self.assertEqual(view.acceptsFirstMouse_.signature, AppKit.NSView.acceptsFirstMouse_.signature)


if __name__ == '__main__':
    unittest.main()
