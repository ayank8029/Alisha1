import os
import logging
import tempfile
import requests
import speech_recognition as sr
from pydub import AudioSegment
from telegram import Update, ReplyKeyboardMarkup
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram.ext import (
    Application, CommandHandler,
    MessageHandler, filters, ContextTypes
)

# ══════════════════════════════════════════════
#  ENV VARIABLES  (Railway/Kuberns mein set karna)
# ══════════════════════════════════════════════
BOT_TOKEN      = os.environ.get("8952093616:AAFMzVicjqGnomdEdgFrI9ckyyjpKbAlCns")
ELEVENLABS_KEY = os.environ.get("sk_df526334ab3d3cb029079cf12c8afba2b5e03ff611dc34be")
ADMIN_ID       = int(os.environ.get("8009192285"))

# ══════════════════════════════════════════════
#  ElevenLabs — TOP 3 Indian Girl Voice IDs
#  In teeno mein se ek choose karna hai
#  (neeche explain kiya hai kaise choose karein)
# ══════════════════════════════════════════════

# Option A → Aisha  (warm, natural Indian girl)
VOICE_ID = "mg9npuuaf8WJphS6E0Rt"

# Option B → Simran (young, friendly, Hindi)
# VOICE_ID = "TRnaQb7q41oL7sV0w6Bu"

# Option C → Anushri (natural young Indian)
# VOICE_ID = "n8agU3KLt1Yttvrx1mYA"

PAID_USERS_FILE = "paid_users.txt"

# ══════════════════════════════════════════════
#  LOGGING
# ══════════════════════════════════════════════
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO
)
log = logging.getLogger(__name__)

# ══════════════════════════════════════════════
#  PAID USER SYSTEM
# ══════════════════════════════════════════════
def is_paid(uid: int) -> bool:
    if uid == ADMIN_ID:
        return True
    try:
        with open(PAID_USERS_FILE) as f:
            return str(uid) in [l.strip() for l in f]
    except FileNotFoundError:
        return False

def add_user(uid: int):
    with open(PAID_USERS_FILE, "a") as f:
        f.write(f"{uid}\n")

def remove_user(uid: int):
    try:
        with open(PAID_USERS_FILE) as f:
            lines = f.readlines()
        with open(PAID_USERS_FILE, "w") as f:
            f.writelines(l for l in lines if l.strip() != str(uid))
    except FileNotFoundError:
        pass

def list_users() -> list:
    try:
        with open(PAID_USERS_FILE) as f:
            return [l.strip() for l in f if l.strip()]
    except FileNotFoundError:
        return []

# ══════════════════════════════════════════════
#  ELEVENLABS — INDIAN GIRL VOICE GENERATE
# ══════════════════════════════════════════════
def make_voice(text: str) -> str:
    """
    ElevenLabs se Indian girl voice banao
    Same text, same emotion feel mein
    Returns: mp3 file path
    """
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}/stream"

    headers = {
        "xi-api-key": ELEVENLABS_KEY,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg"
    }

    body = {
        "text": text,
        # eleven_multilingual_v2 = Hindi+English dono + emotions capture karta hai
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {
            # Stability kam = zyada natural variation (human feel)
            "stability": 0.35,
            # Similarity high = voice consistent rahe
            "similarity_boost": 0.85,
            # Style = emotional expressiveness (IMPORTANT for same feeling)
            "style": 0.40,
            # Speaker boost = clarity aur presence
            "use_speaker_boost": True
        }
    }

    resp = requests.post(url, headers=headers, json=body, timeout=30, stream=True)

    if resp.status_code != 200:
        error_detail = resp.text[:200]
        raise Exception(f"ElevenLabs API error {resp.status_code}: {error_detail}")

    # Temp file mein save karo
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
    for chunk in resp.iter_content(chunk_size=4096):
        if chunk:
            tmp.write(chunk)
    tmp.close()
    return tmp.name

# ══════════════════════════════════════════════
#  SPEECH TO TEXT — Voice → Text convert
# ══════════════════════════════════════════════
def voice_to_text(ogg_path: str) -> str:
    """
    OGG voice message → text
    Hindi aur English dono detect karta hai
    """
    wav_path = ogg_path.replace(".ogg", ".wav")

    try:
        audio = AudioSegment.from_ogg(ogg_path)
        audio.export(wav_path, format="wav")

        r = sr.Recognizer()
        r.energy_threshold = 300
        r.dynamic_energy_threshold = True

        with sr.AudioFile(wav_path) as src:
            r.adjust_for_ambient_noise(src, duration=0.3)
            audio_data = r.record(src)

        # Hindi pehle try karo, phir Indian English
        for lang in ["hi-IN", "en-IN"]:
            try:
                text = r.recognize_google(audio_data, language=lang)
                if text and len(text.strip()) > 0:
                    log.info(f"Recognized [{lang}]: {text}")
                    return text.strip()
            except sr.UnknownValueError:
                continue
            except sr.RequestError as e:
                raise Exception(f"Google Speech API unavailable: {e}")

        return ""

    finally:
        for p in [wav_path]:
            if os.path.exists(p):
                try:
                    os.unlink(p)
                except:
                    pass

# ══════════════════════════════════════════════
#  CLEANUP HELPER
# ══════════════════════════════════════════════
def cleanup(*paths):
    for p in paths:
        if p and os.path.exists(p):
            try:
                os.unlink(p)
            except:
                pass

# ══════════════════════════════════════════════
#  TELEGRAM COMMANDS
# ══════════════════════════════════════════════
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid  = update.effective_user.id
    name = update.effective_user.first_name
    paid = is_paid(uid)

    keyboard = [["🎤 Voice Bhejo", "📝 Text Bhejo"]]
    markup   = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    status = "✅ Tera access active hai!" if paid else f"🔒 Access nahi hai\nAdmin se contact karo: apna ID share karo → `{uid}`"

    await update.message.reply_text(
        f"🎙️ *Indian Girl Voice Bot*\n\n"
        f"Namaste *{name}*! 🙏🇮🇳\n\n"
        f"Koi bhi *voice ya text* bhejo — main wohi\n"
        f"*real Indian girl ki awaaz* mein repeat karungi!\n\n"
        f"Same text · Same feeling · Indian accent 💫\n\n"
        f"{status}",
        parse_mode="Markdown",
        reply_markup=markup
    )

async def cmd_myid(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    await update.message.reply_text(
        f"🆔 Tera Telegram ID:\n`{uid}`\n\n"
        f"Is ID ko admin ko bhejo access lene ke liye.",
        parse_mode="Markdown"
    )

async def cmd_adduser(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Sirf admin kar sakta hai!")
        return
    if not ctx.args:
        await update.message.reply_text("Usage: `/adduser 123456789`", parse_mode="Markdown")
        return
    try:
        uid = int(ctx.args[0])
        add_user(uid)
        await update.message.reply_text(f"✅ User `{uid}` ko access de diya!", parse_mode="Markdown")
    except ValueError:
        await update.message.reply_text("❌ Valid numeric ID daalo!")

async def cmd_removeuser(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Sirf admin kar sakta hai!")
        return
    if not ctx.args:
        await update.message.reply_text("Usage: `/removeuser 123456789`", parse_mode="Markdown")
        return
    try:
        uid = int(ctx.args[0])
        remove_user(uid)
        await update.message.reply_text(f"✅ User `{uid}` ka access hata diya!", parse_mode="Markdown")
    except ValueError:
        await update.message.reply_text("❌ Valid numeric ID daalo!")

async def cmd_listusers(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Sirf admin kar sakta hai!")
        return
    users = list_users()
    if not users:
        await update.message.reply_text("📋 Koi paid user nahi hai abhi.")
        return
    user_list = "\n".join([f"• `{u}`" for u in users])
    await update.message.reply_text(
        f"📋 *Paid Users ({len(users)}):*\n\n{user_list}",
        parse_mode="Markdown"
    )

async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid  = update.effective_user.id
    paid = is_paid(uid)
    await update.message.reply_text(
        f"🆔 Tera ID: `{uid}`\n"
        f"Status: {'✅ Active' if paid else '🔒 Access nahi hai'}",
        parse_mode="Markdown"
    )

# ══════════════════════════════════════════════
#  VOICE MESSAGE HANDLER
# ══════════════════════════════════════════════
async def handle_voice(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id

    # Access check
    if not is_paid(uid):
        await update.message.reply_text(
            f"🔒 *Access Required!*\n\n"
            f"Bot use karne ke liye admin se contact karo.\n"
            f"Apna ID share karo: `{uid}`\n\n"
            f"Pehle /myid command try karo.",
            parse_mode="Markdown"
        )
        return

    status_msg = await update.message.reply_text("🎧 Awaaz sun rahi hoon...")
    ogg_path   = None
    voice_path = None

    try:
        # Step 1: Voice download
        vfile = await ctx.bot.get_file(update.message.voice.file_id)
        tmp   = tempfile.NamedTemporaryFile(delete=False, suffix=".ogg")
        await vfile.download_to_drive(tmp.name)
        ogg_path = tmp.name
        tmp.close()

        # Step 2: Speech → Text
        await status_msg.edit_text("🔤 Samajh rahi hoon...")
        text = voice_to_text(ogg_path)

        if not text:
            await status_msg.edit_text(
                "❌ Awaaz samajh nahi aayi!\n\n"
                "• Thoda zyada clear bolo\n"
                "• Background noise kam karo\n"
                "• Dobara try karo"
            )
            return

        # Step 3: Indian Girl Voice generate
        await status_msg.edit_text("🎤 Indian girl voice bana rahi hoon...")
        voice_path = make_voice(text)

        # Step 4: Send voice back
        await status_msg.delete()
        with open(voice_path, "rb") as vf:
            await update.message.reply_voice(
                voice=vf,
                caption=f"🗣️ _{text}_",
                parse_mode="Markdown"
            )
        log.info(f"Voice sent to user {uid}: {text[:50]}")

    except Exception as e:
        log.error(f"Voice handler error for {uid}: {e}")
        try:
            await status_msg.edit_text(
                f"❌ Kuch problem ho gayi:\n`{str(e)[:150]}`\n\nDobara try karo!",
                parse_mode="Markdown"
            )
        except:
            pass
    finally:
        cleanup(ogg_path, voice_path)

# ══════════════════════════════════════════════
#  TEXT MESSAGE HANDLER
# ══════════════════════════════════════════════
async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid  = update.effective_user.id
    text = update.message.text.strip()

    # Button text ignore karo
    if text in ["🎤 Voice Bhejo", "📝 Text Bhejo"]:
        await update.message.reply_text(
            "Seedha *voice ya text message bhejo* — main wohi Indian girl voice mein repeat karungi! 😊",
            parse_mode="Markdown"
        )
        return

    # Access check
    if not is_paid(uid):
        await update.message.reply_text(
            f"🔒 *Access Required!*\n\n"
            f"Admin se contact karo, apna ID share karo: `{uid}`",
            parse_mode="Markdown"
        )
        return

    if not text:
        return

    # Character limit check
    if len(text) > 400:
        await update.message.reply_text(
            f"❌ Bahut lamba text!\n"
            f"Maximum 400 characters bhejo.\n"
            f"Abhi {len(text)} characters hain."
        )
        return

    status_msg = await update.message.reply_text("🎤 Indian girl voice bana rahi hoon...")
    voice_path = None

    try:
        voice_path = make_voice(text)
        await status_msg.delete()
        with open(voice_path, "rb") as vf:
            await update.message.reply_voice(voice=vf)
        log.info(f"Text→Voice sent to {uid}")

    except Exception as e:
        log.error(f"Text handler error for {uid}: {e}")
        try:
            await status_msg.edit_text(
                f"❌ Error: `{str(e)[:150]}`\n\nDobara try karo!",
                parse_mode="Markdown"
            )
        except:
            pass
    finally:
        cleanup(voice_path)


# ══════════════════════════════════════════════
#  HEALTH CHECK SERVER (platform probe)
# ══════════════════════════════════════════════
class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'OK')
    def log_message(self, *args):
        pass  # silent

def start_health_server(port: int = 8000):
    srv = HTTPServer(('0.0.0.0', port), _HealthHandler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    log.info(f'Health server running on port {port}')


# ══════════════════════════════════════════════
#  MAIN — BOT START
# ══════════════════════════════════════════════
def main():
    if not BOT_TOKEN:
        raise RuntimeError("❌ BOT_TOKEN env variable nahi mila!")
    if not ELEVENLABS_KEY:
        raise RuntimeError("❌ ELEVENLABS_KEY env variable nahi mila!")
    if ADMIN_ID == 0:
        log.warning("⚠️  ADMIN_ID set nahi hai! Admin commands kaam nahi karenge.")

    app = Application.builder().token(BOT_TOKEN).build()

    # Commands register
    app.add_handler(CommandHandler("start",       cmd_start))
    app.add_handler(CommandHandler("myid",        cmd_myid))
    app.add_handler(CommandHandler("status",      cmd_status))
    app.add_handler(CommandHandler("adduser",     cmd_adduser))
    app.add_handler(CommandHandler("removeuser",  cmd_removeuser))
    app.add_handler(CommandHandler("listusers",   cmd_listusers))

    # Message handlers
    app.add_handler(MessageHandler(filters.VOICE,                    handle_voice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,  handle_text))

    start_health_server(int(os.environ.get("PORT", "8000")))
    log.info("🚀 Bot chal raha hai — 24/7!")
    app.run_polling(
        drop_pending_updates=True,
        poll_interval=1.0,
        timeout=30
    )

if __name__ == "__main__":
    main()
