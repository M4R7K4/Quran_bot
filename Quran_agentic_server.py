import os
import json
import time
import requests
import random


from telegram import Bot
from datetime import datetime, date, timedelta
from apscheduler.schedulers.background import BackgroundScheduler

TELEGRAM_BOT_TOKEN = "8500929808:AAFqLnkHberhmRwhHhOk_7xp5iFca3JfD0I"
TELEGRAM_CHAT_ID = "5229631495"
bot = Bot(token=TELEGRAM_BOT_TOKEN)
LATITUDE = "24.0046"
LONGITUDE = "47.1225"

TOPICS = {
    "alrizq": True,
    "alduea_aldhikr": False,
    "almaghfirah_altawba": True,
    "aljanah_alnaar_alakhira": True,
    "alwaeid": True,
    "aleibadah": True,
    "aleaqidah": False
}

TOPICS_MAP = {
    "Fajr": "alrizq",
    "Dhuhr": "aljanah_alnaar_alakhira",
    "Asr": "almaghfirah_altawba",
    "Maghrib": "alwaeid",
    "Isha": "aleibadah"
}

SENT_LOG_FILE = os.getenv("SENT_LOG_FILE", "sent_log.json")
AYAT_LOG_FILE = os.getenv("AYAT_LOG_FILE", "ayat_log.json")
path_vereses = "approved_verses.json"


########################################################################################

def load_verse(path_vereses):

    if not os.path.exists(path_vereses):
        raise FileNotFoundError(f"File not found: {path_vereses}")

    with open(path_vereses, "r", encoding="utf-8") as f:
        data = json.load(f)

    return data

def get_today_prayer_times(lat, lon):
    today = date.today().strftime("%d-%m-%Y")
    url = f"http://api.aladhan.com/v1/timings/{today}"
    params = {"latitude": lat, "longitude": lon, "method": 2}
    try:
        r = requests.get(url, params=params, timeout=10)
        j = r.json()
        timings = j["data"]["timings"]
        return {
            "Fajr": timings["Fajr"],
            "Dhuhr": timings["Dhuhr"],
            "Asr": timings["Asr"],
            "Maghrib": timings["Maghrib"],
            "Isha": timings["Isha"]
        }
    except Exception as e:
        print("Error fetching prayer times:", e)
        return None

def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text}  # لاحظ: حذفت parse_mode
    try:
        r = requests.post(url, json=payload, timeout=10)
        if not r.ok:
            print("Telegram send failed:", r.text)
    except Exception as e:
        print("Telegram send error:", e)

def format_message(verse_item):
    surah = verse_item.get("surah", "")
    ayah_num = verse_item.get("num_the_verse", "")
    ayah = verse_item.get("ayah_text", "")
    tafser = verse_item.get("tafser", "")
    # ارجع نص عادي (بدون علامات Markdown) لأننا نرسل بدون parse_mode
    return f"📿 {ayah}\n\n📖 سورة {surah} - آية {ayah_num}\n\n🪶 {tafser}"

def load_sent_log(path):
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except:
            return {}

def save_sent_log(log, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)

def job_for_prayer(prayer_name, verses_data, TOPICS_MAP):
    try:
        print(f"[{datetime.now()}] تشغيل مهمة الصلاة: {prayer_name}")
        sent_log = load_sent_log(SENT_LOG_FILE)
        today_str = date.today().isoformat()
        sent_today = sent_log.get(today_str, {})

        topic_for_prayer = TOPICS_MAP[prayer_name]



        if prayer_name in sent_today:
            print(f"Already sent for {prayer_name} today -> skipping.")
            return

        ayah = search_verses(verses_data, topic_for_prayer)


        msg = format_message(ayah)
        send_telegram_message(msg)

        sent_today[prayer_name] = {"surah": ayah.get("surah"), "ayah": ayah.get("num_the_verse")}
        sent_log[today_str] = sent_today
        save_sent_log(sent_log, SENT_LOG_FILE)

        print(f"[SENT] {prayer_name} -> {ayah.get('surah')}:{ayah.get('num_the_verse')}")
    except Exception as e:
        print("Error in job_for_prayer:", e)

def search_verses(verses_data, topic_for_prayer):
    topics_used = []
    for _, topic_name in TOPICS_MAP.items():
        topics_used.append(topic_name)

    ayat_log = load_sent_log(AYAT_LOG_FILE)
    ayat_topic_sended = ayat_log.get(topic_for_prayer, [])

    # احسب المتبقي من الآيات غير المُرسلة من المصدر الأصلي للموضوع
    num_ayat_not_sent = 0
    for ayah in verses_data[topic_for_prayer]:
        if ayah["use_it"] == False:
            num_ayat_not_sent += 1

    if num_ayat_not_sent == 0:
        TOPICS[topic_for_prayer] = True
        new_topic = ""

        # ابحث عن موضوع غير مستخدم
        for topic_name, used in TOPICS.items():
            if not used:
                new_topic = topic_name
                break

        # إن لم يوجد، أعد تقييم حسب المواضيع المستخدمة في الصلوات
        if new_topic == "":
            for topic_used in topics_used:
                is_used = False
                for topic_name in TOPICS.keys():
                    if topic_name == topic_used:
                        is_used = True
                        break
                if not is_used:
                    new_topic = topic_name
                    TOPICS[topic_name] = False
                    break

        # طوارئ: لو لم نجد أي موضوع
        if new_topic == "":
            print("♻️ لم يتم العثور على موضوع جديد غير مستخدم. جاري التحقق من المواضيع التي يمكن إعادة تفعيلها...")

            # المواضيع المستخدمة حالياً في الصلوات (محجوزة)
            reserved_topics = set(TOPICS_MAP.values())

            # أعد تفعيل فقط المواضيع المنتهية والتي ليست محجوزة
            for topic_name, used in TOPICS.items():
                if used and (topic_name not in reserved_topics):
                    print(f"🔁 إعادة تفعيل الموضوع: {topic_name}")
                    TOPICS[topic_name] = False

                    # إعادة تعيين حالة use_it للآيات الخاصة بهذا الموضوع فقط
                    for ayah in verses_data[topic_name]:
                        ayah["use_it"] = False

                    # وأفرغ سجل هذا الموضوع في ayat_log
                    ayat_log[topic_name] = []

            save_sent_log(ayat_log, AYAT_LOG_FILE)

            # بعد إعادة التفعيل الجزئية، اختر أول موضوع أصبح جاهز
            for topic_name, used in TOPICS.items():
                if not used:
                    new_topic = topic_name
                    break

            if new_topic == "":
                print("⚠️ جميع المواضيع محجوزة حاليًا في الصلوات، سيتم استخدام نفس الموضوع مؤقتًا.")
                new_topic = topic_for_prayer

        TOPICS[new_topic] = True
        topic_for_prayer = new_topic

        # IMPORTANT: حمّل سجل الموضوع الجديد
        ayat_topic_sended = ayat_log.get(topic_for_prayer, [])

    # اختر آية مناسبة (غير مكررة ولم تُستخدم بعد)
    turn = True
    while turn:
        ayah = random.choice(verses_data[topic_for_prayer])

        # تكرار = نفس ayah_text موجود في السجل
        is_duplicate = False
        for ayah_sent in ayat_topic_sended:
            if ayah_sent.get("ayah_text") == ayah.get("ayah_text"):
                is_duplicate = True
                break

        if (not is_duplicate) and (ayah.get("use_it", False) == False):
            turn = False

    ayah["use_it"] = True
    ayat_topic_sended.append(ayah)
    ayat_log[topic_for_prayer] = ayat_topic_sended
    save_sent_log(ayat_log, AYAT_LOG_FILE)

    return ayah

def schedule_daily_jobs(lat, lon, verses_data, debug=False):
    scheduler = BackgroundScheduler()
    scheduler.start()

    def schedule_for_today():
        print(f"\n🔁 تحديث جدول الصلوات ({date.today()})\n")
        times = get_today_prayer_times(lat, lon)
        if not times:
            print("❌ فشل في جلب مواقيت الصلاة.")
            return

        now = datetime.now()
        for prayer, time_str in times.items():
            hh_mm = time_str.strip()[:5]
            try:
                hour, minute = map(int, hh_mm.split(":"))
            except Exception as e:
                print("Error parsing time for", prayer, time_str, e)
                continue

            run_dt = datetime(now.year, now.month, now.day, hour, minute, 0)
            run_dt = run_dt + timedelta(hours=3)
            if run_dt < now:
                run_dt += timedelta(days=1)


            scheduler.add_job(
                job_for_prayer,
                trigger='date',
                run_date=run_dt,
                args=[prayer, verses_data, TOPICS_MAP],
            )

            print(f"✅ تم جدولة {prayer} عند {run_dt.strftime('%H:%M')} لموضوع {TOPICS_MAP[prayer]}")

    # أول تشغيل لليوم الحالي
    schedule_for_today()

    # إعادة الجدولة كل يوم عند 00:05 صباحًا
    scheduler.add_job(schedule_for_today, 'cron', hour=0, minute=5)
    print("\n🕒 تم تفعيل النظام لتحديث الجداول يوميًا 00:05\n")

    try:
        while True:
            time.sleep(30)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()

def main():
    verses = load_verse(path_vereses)
    print("Loaded", len(verses), "verses.")

    print("Computed topic embeddings for topics:", TOPICS_MAP)

    # اختبار فوري لتشغيل وظيفة صلاة الفجر الآن
    print("\n[🔹 TEST RUN] Running Fajr test job immediately...\n")
    job_for_prayer("Isha", verses, TOPICS_MAP)

    schedule_daily_jobs(LATITUDE, LONGITUDE, verses, debug=False)



if __name__ == "__main__":
    main()