# Group 3.3 validation alignment helper.
# Final trigger for canonical ownership validation.
from pathlib import Path

p = Path('main.py')
s = p.read_text()
start = s.index('def _persistent_nav(')
end = s.index('async def render_home(', start)
block = s[start:end]
for old, new in {
    "InlineKeyboardButton(t(lang, 'price'),": "InlineKeyboardButton(f\"📈 {t(lang, 'price')}\",",
    "InlineKeyboardButton(t(lang, 'signal'),": "InlineKeyboardButton(f\"🧠 {t(lang, 'signal')}\",",
    "InlineKeyboardButton(t(lang, 'analysis'),": "InlineKeyboardButton(f\"📊 {t(lang, 'analysis')}\",",
    "InlineKeyboardButton(t(lang, 'account'),": "InlineKeyboardButton(f\"👑 {t(lang, 'account')}\",",
    "InlineKeyboardButton(t(lang, 'settings'),": "InlineKeyboardButton(f\"⚙️ {t(lang, 'settings')}\",",
    "InlineKeyboardButton(t(lang, 'access'),": "InlineKeyboardButton(f\"💎 {t(lang, 'access')}\",",
}.items():
    block = block.replace(old, new)
p.write_text(s[:start] + block + s[end:])

p = Path('tests/test_ui_language_consistency.py')
s = p.read_text()
old = '''                f"📈 {i18n.t(lang, 'price')}",
                f"🧠 {i18n.t(lang, 'signal')}",
                f"📊 {i18n.t(lang, 'analysis')}",
                f"👑 {i18n.t(lang, 'account')}",
                f"⚙️ {i18n.t(lang, 'settings')}",
                f"🌐 {i18n.t(lang, 'language')}",
                f"💎 {i18n.t(lang, 'access')}",
                i18n.t(lang, "menu"),'''
new = '''                f"📈 {i18n.t(lang, 'price')}",
                f"🧠 {i18n.t(lang, 'signal')}",
                f"📊 {i18n.t(lang, 'analysis')}",
                f"👑 {i18n.t(lang, 'account')}",
                f"⚙️ {i18n.t(lang, 'settings')}",
                f"🌐 {i18n.t(lang, 'language')}",
                f"💎 {i18n.t(lang, 'access')}",
                f"🏠 {i18n.t(lang, 'menu')}",
                f"👨‍💼 {i18n.t(lang, 'account')}",'''
assert old in s
p.write_text(s.replace(old, new, 1))
