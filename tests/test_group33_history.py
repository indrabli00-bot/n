import asyncio
import inspect

import main


def test_history_renderer_uses_screen_content_and_context_separator():
    src = inspect.getsource(main.render_history)
    assert "[ OPERATOR HUB ]" in src
    assert "recent_orders_for" in src
    assert "t(lang, 'history')} // {t(lang, 'account')}" in src
    assert "t(lang, 'history')}\"," not in src


def test_history_renderer_has_inactive_premium_cta_and_persistent_nav():
    src = inspect.getsource(main.render_history)
    assert "screen:activate" in src
    assert "_keyboard(update, keyboard_rows)" in src


def test_history_renderer_is_async():
    assert asyncio.iscoroutinefunction(main.render_history)
