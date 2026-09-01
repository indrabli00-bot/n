from pathlib import Path

main = Path('main.py').read_text()
premium = Path('premium_visuals.py').read_text()
app = Path('app.py').read_text()
assert 'def _nav_keyboard' not in main
assert 'nav:back' not in main
assert "InlineKeyboardButton(t(lang, 'back')" not in main
assert 'main.render_' not in premium
assert 'premium_visuals' not in app
assert 'def _persistent_nav' in main
assert "callback_data='nav:home'" in main
assert "callback_data='screen:account'" in main
print('GROUP 3.3 ownership guard: PASS')
