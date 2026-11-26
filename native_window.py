"""Native window interaction adjustments, loaded only for desktop startup."""
import sys


def _accepts_first_mouse(_view, _event):
    return True


def enable_first_mouse() -> None:
    """Allow a macOS click to activate the window and its control together."""
    if sys.platform != 'darwin':
        return
    from AppKit import NSView
    from objc import classAddMethods, selector
    from webview.platforms.cocoa import BrowserView

    # WKWebView otherwise consumes the first click solely to activate its window.
    # Match the system BOOL signature rather than assuming an Objective-C ABI.
    classAddMethods(BrowserView.WebKitHost, [selector(
        _accepts_first_mouse,
        selector=b'acceptsFirstMouse:',
        signature=NSView.acceptsFirstMouse_.signature,
    )])
