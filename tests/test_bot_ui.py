import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///./test_bot_ui.sqlite')
os.environ.setdefault('TELEGRAM_BOT_TOKEN', 'test:token')
os.environ.setdefault('TELEGRAM_PREMIUM_CHAT_ID', '-1001234567890')
os.environ.setdefault('TELEGRAM_WEBHOOK_SECRET', 'telegram_secret')
os.environ.setdefault('BELMO_PUBLIC_URL', 'https://example.com')
os.environ.setdefault('WHOP_COMPANY_ID', 'biz_test')
os.environ.setdefault('WHOP_PRODUCT_ID', 'prod_test')
os.environ.setdefault('WHOP_WEBHOOK_SECRET', 'whop_secret')
os.environ.setdefault('WHOP_OAUTH_CLIENT_ID', 'client_test')
os.environ.setdefault('WHOP_OAUTH_CLIENT_SECRET', 'client_secret')
os.environ.setdefault('WHOP_OAUTH_REDIRECT_URI', 'https://example.com/auth/whop/callback')
os.environ.setdefault('WHOP_OAUTH_STATE_SECRET', 'state_secret')

import bot


def _visible_lines(rendered: str) -> list[str]:
    assert rendered.startswith('<pre>')
    assert rendered.endswith('</pre>')
    return rendered[5:-6].splitlines()


def _assert_fixed_terminal(rendered: str) -> None:
    lines = _visible_lines(rendered)
    assert lines
    assert all(len(line) == bot.TERMINAL_WIDTH for line in lines)
    assert lines[0] == '+' + '-' * (bot.TERMINAL_WIDTH - 2) + '+'
    assert lines[-1] == lines[0]
    assert all(line.startswith('|') and line.endswith('|') for line in lines[1:-1])


def test_terminal_layout_uses_mobile_optimized_width():
    assert bot.TERMINAL_WIDTH == 52
    _assert_fixed_terminal(bot._main_menu_text())


def test_all_bot_panels_share_exact_same_terminal_width():
    panels = [
        bot._main_menu_text(),
        bot.HELP_TEXT,
        bot.BONUS_TEXT,
        bot.ACCESS_INACTIVE_TEXT,
        bot.ACCESS_ACTIVE_TEXT,
        bot.UNKNOWN_INPUT_TEXT,
        bot.ERROR_TEXT,
        bot._format_signal({'signal': 'HOLD', 'reason': 'test'}),
    ]
    for panel in panels:
        _assert_fixed_terminal(panel)


def test_main_menu_uses_full_two_column_action_layout():
    markup = bot.main_menu()
    assert len(markup.inline_keyboard) == 2
    assert all(len(row) == 2 for row in markup.inline_keyboard)
    assert [button.text for button in markup.inline_keyboard[0]] == [
        '📡 LATEST SIGNAL',
        '📊 ACCESS STATUS',
    ]
    assert [button.text for button in markup.inline_keyboard[1]] == [
        '🎁 BOT BONUS',
        'ℹ️ HOW IT WORKS',
    ]


def test_main_menu_describes_bot_as_bonus_not_purchase_gate():
    text = bot._main_menu_text()
    assert 'MEMBER BONUS' in text
    assert 'Premium Channel' in text
    assert 'bonus' in text
    assert 'HUBUNGKAN WHOP' not in text


def test_help_describes_channel_as_primary_product():
    assert 'PAYMENT : Neural Gold on Whop' in bot.HELP_TEXT
    assert 'ACCESS  : Premium Channel' in bot.HELP_TEXT
    assert 'BONUS   : Telegram bot' in bot.HELP_TEXT
    assert 'Connect your Whop account' not in bot.HELP_TEXT


def test_bonus_panel_does_not_offer_oauth():
    assert 'BOT     : BONUS' in bot.BONUS_TEXT
    assert 'OAuth' not in bot.BONUS_TEXT
    assert 'HUBUNGKAN WHOP' not in bot.BONUS_TEXT


def test_unknown_input_panel_is_english_and_actionable():
    assert "I didn't recognize that input." in bot.UNKNOWN_INPUT_TEXT
    assert 'Use the menu below to continue.' in bot.UNKNOWN_INPUT_TEXT
    assert 'Available:' in bot.UNKNOWN_INPUT_TEXT


def test_error_panel_is_safe_and_actionable():
    assert 'A temporary error occurred.' in bot.ERROR_TEXT
    assert 'Your request was not completed.' in bot.ERROR_TEXT
    assert 'try again.' in bot.ERROR_TEXT


def test_all_user_facing_bot_panels_are_english():
    panels = [
        bot._main_menu_text(),
        bot.HELP_TEXT,
        bot.BONUS_TEXT,
        bot.ACCESS_INACTIVE_TEXT,
        bot.ACCESS_ACTIVE_TEXT,
        bot.UNKNOWN_INPUT_TEXT,
        bot.ERROR_TEXT,
    ]
    forbidden_legacy_terms = (
        'AKSES',
        'GAGAL',
        'BELUM',
        'SILAKAN',
        'HUBUNGKAN',
        'PEMBAYARAN',
        'CARA KERJA',
    )
    for panel in panels:
        upper = panel.upper()
        assert not any(term in upper for term in forbidden_legacy_terms)


def test_message_not_modified_error_is_treated_as_idempotent_noop():
    from telegram.error import BadRequest

    assert bot._is_message_not_modified(BadRequest('Message is not modified'))
    assert bot._is_message_not_modified(
        BadRequest('Bad Request: message is not modified')
    )
    assert not bot._is_message_not_modified(BadRequest('Bad Request: message not found'))


def test_signal_layout_uses_terminal_labels_and_exact_fixed_width():
    rendered = bot._format_signal(
        {
            'signal': 'HOLD',
            'setup_strength': 42,
            'trend': 'NEUTRAL',
            'rsi': 50.12,
            'entry': 4491.23,
            'tp': [4495.0, 4500.0, 4505.0],
            'stop': 4486.0,
            'risk_reward': '1:2',
            'samples': 300,
            'reason': 'insufficient_confirmation',
        }
    )
    lines = _visible_lines(rendered)
    inner = [line[1:-1].rstrip() for line in lines[1:-1]]
    assert inner[0] == '[ NEURAL STRIKES ]'
    assert any(line == 'SIGNAL : HOLD' for line in inner)
    assert any(line.startswith('ENTRY  :') for line in inner)
    assert any(line.startswith('TP1') for line in inner)
    assert any(line.startswith('STOP   :') for line in inner)
    _assert_fixed_terminal(rendered)
