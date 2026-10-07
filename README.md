# UZSE Portfolio Agent

Toshkent Respublika Fond Birjasi (UZSE)'dagi aksiyalaringizni kuzatuvchi,
yangiliklarni tahlil qiluvchi va narx belgilangan chegaradan pasaysa Telegram
orqali ogohlantiruvchi agent.

## Nima qiladi

1. **Narx monitoring** — `uzse.uz`dagi ochiq sahifalarni (rasmiy API yo'q, shu
   sababli scraping) o'qib, portfelingizdagi va watchlist'ingizdagi
   aksiyalarning joriy narxini oladi va tarixini SQLite bazasida saqlaydi.
2. **Threshold-alert** — har bir aksiya uchun siz belgilagan ikkita chegara:
   - sotib olgan narxdan necha foiz pasayganda ogohlantirish (`drop_alert_pct`)
   - so'nggi 30 kunlik eng yuqori narxdan necha foiz pasayganda ogohlantirish
     (`trailing_drop_pct`, "cho'qqidan qaytish"ni ushlaydi)
3. **Yangiliklar tahlili** — O'zbekiston iqtisodiy yangiliklari RSS manbalarini
   (gazeta.uz, uzreport.news, nuz.uz, daryo.uz, uza.uz) kuzatib, kompaniya
   nomi/tikeriga mos maqolalarni topadi va oddiy kalit-so'z asosida
   ijobiy/salbiy ohangini baholaydi.
4. **Kunlik hisobot** — har bir aksiya uchun narx trendi + yangiliklar ohangini
   birlashtirib, oddiy "signal" (Ijobiy trend / Neytral / Salbiy trend)
   chiqaradi va Telegram'ga yuboradi.

## MUHIM cheklovlar (iltimos o'qing)

- **UZSE'ning rasmiy ochiq API'si yo'q.** Narxlar `uzse.uz` saytining HTML
  sahifalarini o'qish (scraping) orqali olinadi. Sayt dizayni o'zgarsa,
  `uzse_agent/scraper.py` faylidagi parsing mantig'ini yangilash kerak
  bo'lishi mumkin.
- **Yangiliklar tahlili sodda** — hozirgi versiyada kalit so'zlarni sanash
  orqali sentiment baholanadi. Bu chin ma'noda "tushunish" emas, faqat qo'pol
  yo'nalish ko'rsatkichi. Sifatni oshirish uchun `uzse_agent/news.py` ichidagi
  `score_sentiment()` funksiyasini kattaroq til modeli (masalan Claude API)
  chaqiruviga almashtirish mumkin — funksiya imzosi bir xil qoladi.
- **Bu moliyaviy maslahat bermaydi.** "Signal" faqat tarixiy narx harakati va
  yangiliklar ohangiga asoslangan statistik xulosa. Hech qanday agent
  (bu yoki boshqasi) bozor harakatini 100% aniqlikda bashorat qila olmaydi.
  Yakuniy qarorni har doim o'zingiz qabul qiling.
- Agent hech qanday **savdo buyrug'i bermaydi / avtomatik xarid-sotuv
  qilmaydi** — faqat kuzatuv, tahlil va ogohlantirish uchun.

## O'rnatish

```bash
cd uzse-agent
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
cp config/portfolio.example.yaml config/portfolio.yaml
```

### Telegram bot sozlash

1. Telegram'da [@BotFather](https://t.me/BotFather)ga yozib `/newbot` buyrug'i
   bilan yangi bot yarating — sizga token beriladi.
2. Shu tokenni `.env` faylidagi `TELEGRAM_BOT_TOKEN` ga qo'ying.
3. Yaratilgan botga Telegram'da biror xabar yuboring (masalan "salom").
4. Brauzerda oching: `https://api.telegram.org/bot<TOKEN>/getUpdates` va
   javobdagi `"chat":{"id": ...}` raqamini `.env`dagi `TELEGRAM_CHAT_ID`ga
   qo'ying.
5. Tekshirish: `python main.py test-telegram` — botdan sinov xabari kelishi
   kerak.

### Portfolio sozlash

`config/portfolio.yaml` faylini o'zingizning aksiyalaringiz bilan to'ldiring
(namuna va har bir maydon izohi `config/portfolio.example.yaml`da). `ticker`
maydoniga aksiyaning ISIN kodini (masalan `UZ7036271003`) yoki birja tikerini
(masalan `UZNGP`) yozing. ISIN'ni https://uzse.uz/isu_infos/STK sahifasidagi
qidiruv orqali topasiz — u havolada `isu_cd=` dan keyin ko'rinadi.

## Ishga tushirish

```bash
# Bir martalik tekshiruv (narx + threshold-alert)
python main.py check

# Yangiliklarni yig'ish
python main.py news

# Darhol kunlik hisobot yuborish
python main.py report

# Doimiy ishlaydigan rejim (savdo kunlari 09:00-18:00 har 30 daqiqada
# narx tekshiradi, har 2 soatda yangilik yig'adi, 18:30da hisobot yuboradi)
python main.py daemon
```

### Productionda ishlatish

`daemon` rejimini terminalda ochiq qoldirish shart emas — uni systemd
service yoki `tmux`/`screen` ichida, yoxud oddiygina cron orqali ishlatish
mumkin:

```cron
# Ish kunlari 9:00-18:00 orasida har 30 daqiqada narx tekshiruvi
*/30 9-18 * * 1-5 cd /path/to/uzse-agent && .venv/bin/python main.py check >> logs/cron.log 2>&1

# Har 2 soatda yangiliklar
0 */2 * * * cd /path/to/uzse-agent && .venv/bin/python main.py news >> logs/cron.log 2>&1

# Kuniga bir marta hisobot
30 18 * * 1-5 cd /path/to/uzse-agent && .venv/bin/python main.py report >> logs/cron.log 2>&1
```

## Loyihaning tuzilishi

```
uzse-agent/
  main.py                  # CLI kirish nuqtasi
  uzse_agent/
    config.py              # .env va portfolio.yaml ni yuklash
    scraper.py              # uzse.uz'dan narx olish (HTML parsing)
    news.py                 # RSS yangiliklar + sentiment baholash
    analyzer.py              # narx trendi + sentiment -> signal
    notifier.py              # Telegram xabar yuborish
    storage.py                # SQLite: narx tarixi, yuborilgan alertlar, yangiliklar
    runner.py                  # yuqoridagilarni birlashtiruvchi asosiy mantiq
  config/portfolio.example.yaml
  .env.example
  requirements.txt
```

## Keyingi qadamlar (ixtiyoriy kengaytirishlar)

- `score_sentiment()`ni LLM-asoslangan tahlilga almashtirish — ancha aniqroq
  yangilik tushunish va qisqacha xulosalash beradi.
- `analyzer.py`ga texnik ko'rsatkichlar (SMA/EMA, RSI) qo'shish.
- Bir nechta broker/ma'lumot manbasidan (masalan qo'lda kiritilgan narxlar
  yoki boshqa platforma) narxlarni o'zaro solishtirib xatolarni kamaytirish.
- Telegram bot'ga `/portfolio`, `/report` kabi buyruqlar qo'shib, so'rov
  bo'yicha hisobot olish (hozircha faqat bir tomonlama xabar yuboriladi).
# stock_agent
