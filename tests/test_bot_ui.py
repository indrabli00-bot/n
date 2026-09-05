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


def test_terminal_layout_uses_fixed_width():
    lines = _visible_lines(bot._main_menu_text())
    assert lines
    assert all(len(line) <= bot.TERMINAL_WIDTH for line in lines)


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


def test_message_not_modified_error_is_treated_as_idempotent_noop():
    from telegram.error import BadRequest

    assert bot._is_message_not_modified(BadRequest('Message is not modified'))
    assert bot._is_message_not_modified(
        BadRequest('Bad Request: message is not modified')
    )
    assert not bot._is_message_not_modified(BadRequest('Bad Request: message not found'))


def test_help_layout_uses_fixed_width():
    lines = _visible_lines(bot.HELP_TEXT)
    assert lines
    assert all(len(line) <= bot.TERMINAL_WIDTH for line in lines)


def test_signal_layout_uses_terminal_labels_and_fixed_width():
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
    assert lines[0] == '[ NEURAL STRIKES ]'
    assert any(line.startswith('SIGNAL : HOLD') for line in lines)
    assert any(line.startswith('ENTRY  :') for line in lines)
    assert any(line.startswith('TP1') for line in lines)
    assert any(line.startswith('STOP   :') for line in lines)
    assert all(len(line) <= bot.TERMINAL_WIDTH for line in lines)
