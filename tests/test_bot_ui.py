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
    prefix = f'{bot.TERMINAL_HEADER}\n\n<pre>'
    suffix = f'</pre>\n\n{bot.TERMINAL_FOOTER}'
    assert rendered.startswith(prefix)
    assert rendered.endswith(suffix)
    return rendered[len(prefix):-len(suffix)].splitlines()


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


def test_terminal_has_unified_header_and_footer():
    rendered = bot._main_menu_text()
    assert rendered.startswith('NEURAL GOLD [SIGNALS]\n\n<pre>')
    assert rendered.endswith('</pre>\n\nXAU/USD • MEMBER BONUS')


def test_all_bot_panels_share_exact_same_terminal_width():
    panels = [
        bot._main_menu_text(),
        bot.HELP_TEXT,
        bot.BONUS_TEXT,
        bot.ACCESS_INACTIVE_TEXT,
        bot.ACCESS_ACTIVE_TEXT,
        bot.UNKNOWN_INPUT_TEXT,
        bot.ERROR_TEXT,
        bot._system_info_text(False),
        bot._system_info_text(True),
        bot._format_signal({'signal': 'HOLD', 'reason': 'test'}),
    ]
    for panel in panels:
        _assert_fixed_terminal(panel)


def test_all_bot_panels_share_the_same_header_and_footer():
    panels = [
        bot._main_menu_text(),
        bot.HELP_TEXT,
        bot.BONUS_TEXT,
        bot.ACCESS_INACTIVE_TEXT,
        bot.ACCESS_ACTIVE_TEXT,
        bot.UNKNOWN_INPUT_TEXT,
        bot.ERROR_TEXT,
        bot._system_info_text(False),
        bot._system_info_text(True),
        bot._format_signal({'signal': 'HOLD', 'reason': 'test'}),
    ]
    for panel in panels:
        assert panel.startswith(f'{bot.TERMINAL_HEADER}\n\n<pre>')
        assert panel.endswith(f'</pre>\n\n{bot.TERMINAL_FOOTER}')


def test_main_menu_is_exactly_four_actions_in_two_columns():
    markup = bot.main_menu()
    assert len(markup.inline_keyboard) == 2
    assert all(len(row) == 2 for row in markup.inline_keyboard)
    assert [button.text for button in markup.inline_keyboard[0]] == [
        '📡 LIVE MARKET FEED',
        '⚡ NEURAL SIGNAL',
    ]
    assert [button.text for button in markup.inline_keyboard[1]] == [
        '📊 MARKET ANALYSIS',
        '⚙️ SYSTEM SETTING',
    ]
    assert [button.callback_data for row in markup.inline_keyboard for button in row] == [
        'market',
        'signal',
        'analysis',
        'system',
    ]


def test_main_menu_has_no_legacy_primary_actions():
    markup = bot.main_menu()
    labels = [button.text for row in markup.inline_keyboard for button in row]
    assert not any('LATEST SIGNAL' in label for label in labels)
    assert not any('ACCESS STATUS' in label for label in labels)
    assert not any('BOT BONUS' in label for label in labels)
    assert not any('HOW IT WORKS' in label for label in labels)


def test_main_menu_describes_the_four_terminal_views():
    text = bot._main_menu_text()
    assert 'LIVE MARKET FEED' in text
    assert 'NEURAL SIGNAL' in text
    assert 'MARKET ANALYSIS' in text
    assert 'SYSTEM SETTING' in text
    assert 'MEMBER BONUS' in text
    assert 'Premium Channel' in text
    assert 'HUBUNGKAN WHOP' not in text


def test_system_setting_is_single_information_panel():
    inactive = bot._system_info_text(False)
    active = bot._system_info_text(True)
    for panel, access_status, channel_status in (
        (inactive, 'ACCESS STATUS  : INACTIVE', 'PREMIUM CHANNEL: MEMBER ACCESS REQUIRED'),
        (active, 'ACCESS STATUS  : ACTIVE', 'PREMIUM CHANNEL: VERIFIED'),
    ):
        assert access_status in panel
        assert channel_status in panel
        assert '[ HOW IT WORKS ]' in panel
        assert '01 PAYMENT : Neural Gold on Whop' in panel
        assert '02 ACCESS  : Premium Channel' in panel
        assert '03 CONTENT : Neural Strikes' in panel
        assert '04 BONUS   : Telegram bot' in panel
        _assert_fixed_terminal(panel)


def test_system_setting_contains_no_submenu_actions():
    panel = bot._system_info_text(True)
    assert 'ACCESS STATUS' in panel
    assert 'HOW IT WORKS' in panel
    assert 'BOT BONUS' in panel
    assert 'PREMIUM CHANNEL' in panel
    assert 'Select a terminal view below.' not in panel


def test_help_and_bonus_commands_are_compatible_without_restoring_primary_menu_items():
    assert bot.HELP_TEXT == bot._system_info_text(False)
    assert bot.BONUS_TEXT == bot._system_info_text(False)
    markup = bot.main_menu()
    labels = [button.text for row in markup.inline_keyboard for button in row]
    assert labels == [
        '📡 LIVE MARKET FEED',
        '⚡ NEURAL SIGNAL',
        '📊 MARKET ANALYSIS',
        '⚙️ SYSTEM SETTING',
    ]


def test_bonus_panel_does_not_offer_oauth():
    assert 'OAuth' not in bot.BONUS_TEXT
    assert 'HUBUNGKAN WHOP' not in bot.BONUS_TEXT


def test_unknown_input_panel_is_english_and_actionable():
    assert "I didn't recognize that input." in bot.UNKNOWN_INPUT_TEXT
    assert 'Use the four terminal views below.' in bot.UNKNOWN_INPUT_TEXT
    assert 'LIVE MARKET FEED' in bot.UNKNOWN_INPUT_TEXT
    assert 'NEURAL SIGNAL' in bot.UNKNOWN_INPUT_TEXT
    assert 'MARKET ANALYSIS' in bot.UNKNOWN_INPUT_TEXT
    assert 'SYSTEM SETTING' in bot.UNKNOWN_INPUT_TEXT


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
