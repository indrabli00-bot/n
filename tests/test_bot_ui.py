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
    assert 'Premium Channel is the primary' in text
    assert 'a bonus utility for channel members.' in text
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
