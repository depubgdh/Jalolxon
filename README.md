# Bull Play — Telegram bot + Mini App (Paper.io va Slither, tekin)

## Ishga tushirish
1. @BotFather'da bot yarating, tokenni oling.
2. `.env.example` dagi qiymatlarni muhit o'zgaruvchisi qilib kiriting (`BOT_TOKEN`, `ADMIN_IDS`, `WEBAPP_URL`).
3. `pip install -r requirements.txt`, so'ng `python main.py` (bot va Mini App bitta jarayonda; `WEBAPP_URL` — shu serverning https manzili).
4. Telegramda botga `/start` yuboring. Admin: `/admin` yoki Mini App → yuqoridagi ⚙ tugmasi.
5. Telegram vazifalari uchun botni kanal/guruhga **admin** qiling.

## Sinab ko'rish (Telegramsiz)
`python dev_server.py` → `http://localhost:8770/?dev=1` (faqat sinov, `main.py` da ishlamaydi).

## Qoidalar (hammasi Mini App → Admin → Sozlamalar)
- O'yindan daromad: serverda o'lchangan vaqt × daqiqasiga so'm, kunlik chegara bilan (natija mijozdan olinmaydi — soxtalashtirib bo'lmaydi).
- Do'st qo'shilsa: 300 so'm; faol bo'lsa (10 daqiqa o'ynasa): +700 so'm. Vazifalar: bajargan va taklif qilgan odamga alohida bonus.
- Yechib olish: so'rov adminga keladi (bot tugmalari yoki panel); to'lovni admin o'zi amalga oshiradi. Rad etilsa balansga qaytadi.
