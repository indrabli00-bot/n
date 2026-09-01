from pathlib import Path

root = Path('.')

main = root / 'main.py'
s = main.read_text(encoding='utf-8')
s = s.replace('InlineKeyboardButton("🔄 Tambah masa aktif", callback_data="screen:renew")', 'InlineKeyboardButton(f"🔄 {t(lang, \'renew\')}", callback_data="screen:renew")')
main.write_text(s, encoding='utf-8')

i18n = root / 'i18n.py'
s = i18n.read_text(encoding='utf-8')
if '"renew":"Renew"' not in s:
    s = s.replace('"history":"Transaction History",', '"history":"Transaction History","renew":"Renew",', 1)
if '"renew":"Perpanjang"' not in s:
    s = s.replace('"history":"Riwayat Transaksi",', '"history":"Riwayat Transaksi","renew":"Perpanjang",', 1)
i18n.write_text(s, encoding='utf-8')

term = root / 'terminal_style.py'
s = term.read_text(encoding='utf-8')
s = s.replace('line("SYSTEM", "INITIALIZING...")', 'line("SYSTEM", f"INITIALIZING NEURAL GOLD {NEURAL_VERSION}...")')
term.write_text(s, encoding='utf-8')
print('GROUP 3.3 COMPATIBILITY FIX APPLIED')
