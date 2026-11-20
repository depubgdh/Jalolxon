# UZB cash bot — Telegram bot + Mini App (Paper.io va Slither, tekin)

## Ishga tushirish
1. @BotFather'da bot yarating, tokenni oling.
2. `.env.example` dagi qiymatlarni muhit o'zgaruvchisi qilib kiriting (`BOT_TOKEN`, `ADMIN_IDS`, `WEBAPP_URL`).
3. `pip install -r requirements.txt`, so'ng `python main.py` (bot va Mini App bitta jarayonda; `WEBAPP_URL` — shu serverning https manzili).
4. Telegramda botga `/start` yuboring. Admin: `/admin` yoki Mini App → yuqoridagi ⚙ tugmasi.
5. Telegram vazifalari uchun botni kanal/guruhga **admin** qiling.

## Sinab ko'rish (Telegramsiz)
`python dev_server.py` → `http://localhost:8770/?dev=1` (faqat sinov, `main.py` da ishlamaydi).

## Admin panel (Mini App → ⚙)
- **O'yinlar**: o'yin kartalaridagi rasmlarni almashtirish (JPG/PNG/WEBP/GIF), Paper.io ochko hisobi (hudud foizi va o'ldirishlar uchun coin), coin kursi, kunlik chegara.
- **Start**: `/start` bosganda yuboriladigan matn (`{name}` — ism) va unga rasm yoki GIF.
- **Sozlamalar**, **Vazifalar**, **Yechishlar**, **Foydalanuvchi**, **Xabar** — avvalgidek.

## Qoidalar
- O'yindan daromad: o'yinda yig'ilgan **coin**ga qarab (daqiqaga emas). Paper.io: egallangan hudud foizi × (1% uchun coin) + o'ldirilganlar × (har biri uchun coin). Slither: yig'ilgan ochko × (1.00 ochko uchun coin). So'm = coin × kurs (100 coin = N so'm). Natija mijozdan keladi, shuning uchun server uni vaqt bo'yicha (daqiqasiga eng ko'p coin) va kunlik chegara bilan cheklaydi.
- Do'st qo'shilsa: 300 so'm; faol bo'lsa (10 daqiqa o'ynasa): +700 so'm. Vazifalar: bajargan va taklif qilgan odamga alohida bonus.
- Yechib olish: so'rov adminga keladi (bot tugmalari yoki panel); to'lovni admin o'zi amalga oshiradi. Rad etilsa balansga qaytadi.
