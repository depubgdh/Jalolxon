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
- Pul birligi — **$**, eng kichigi **0.0001 $** (bazada butun son: 10 000 birlik = 1 $). Ko'rsatish doim 4 xonali: `100.0001 $`.
- O'yindan daromad (Admin → O'yinlar → «O'yin to'lovlari»): Paper.io — egallangan hudud har 1% uchun $ + o'ldirilgan raqib uchun $; Slither — har 1.00 ochko uchun $ + o'ldirilgan ilon uchun $. Natija mijozdan keladi, shuning uchun server uni vaqt bo'yicha (daqiqasiga eng ko'p $) va kunlik chegara bilan cheklaydi.
- Do'st qo'shilsa va faol bo'lsa: admin belgilagan $ bonus. Vazifalar: bajargan va taklif qilgan odamga alohida bonus.
- Yechib olish: so'rov adminga keladi; to'lovni admin o'zi amalga oshiradi. Rad etilsa balansga qaytadi.

## YouTube video tizimi (alohida modul)
Fayllar: `video.js` (mijoz moduli, YouTube IFrame API), `videos.py` (baza va tartib qoidasi), `api.py` oxiridagi `videos/next` va `admin/video/*` yo'llari. O'yin kodiga faqat `pause`/`resume` xabarlari qo'shilgan.
- O'yin ekranining tepasida, pastida esa doim ko'rinadigan ovozsiz YouTube pleyer. **O'ynash** bosilganda 1-video ishga tushadi; pleyer haqiqatan PLAYING bo'lgach o'yin boshlanadi.
- Videolar admin belgilagan tartibda ketadi, oxirgisidan keyin yana 1-video (LOOP). Yangi video har doim ro'yxat oxiriga qo'shiladi.
- Yutqazish, «Yana o'ynash» va raund almashishi videoni tegmaydi. Video faqat o'yindan chiqib, qaytadan kirilganda 1-videodan boshlanadi.
- Internet uzilsa, video BUFFERING (10 soniyadan ko'p), to'xtab qolsa, xatolik bersa yoki avtomatik ijro bloklansa — o'yin pauzaga tushadi va «Davom ettirish» tugmasi chiqadi. Tugma internetni tekshiradi, joriy videoni boshidan ishga tushiradi va PLAYING bo'lgach o'yin davom etadi.
- Admin → **Videolar**: havolani tekshirish va qo'shish, o'chirish, ⬆⬇ tartib, nomini tahrirlash, o'chirib qo'yish (faolsiz), jami soni va oxirgi qo'shilgani. O'chirilgan video hozir ijro etilayotgan foydalanuvchida oxirigacha davom etadi, keyingi aylanishda esa yo'q.
- Har bir foydalanuvchining navbati o'z qurilmasida saqlanadi — bir-biriga xalaqit bermaydi. Jadval `videos` birinchi ishga tushirishda o'zi yaratiladi.
