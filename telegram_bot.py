# telegram_bot.py - Msaidizi Mkononi Telegram Bot with Voice Support
import asyncio
import logging
import os
import tempfile
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, Message
import aiohttp
from pydub import AudioSegment
import speech_recognition as sr
from pydub.utils import which

# ------------------ CONFIG ------------------
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "8449082083:AAEa-SQ7YvyAtFqVe9KzdNTALbhdFrwHxs0")
# Internal URL for reliability inside Docker
RASA_URL = "http://127.0.0.1:5005/webhooks/rest/webhook"

# Ensure ffmpeg is available in the PATH (standard in Linux/Docker)
# We don't need a hardcoded path if it's in the environment PATH

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher(bot)

# In-memory language store
user_language = {}

# Main menu keyboard
def get_menu_keyboard(lang="sw"):
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=False)
    if lang == "sw":
        keyboard.add(KeyboardButton("1. Hospitali"))
        keyboard.add(KeyboardButton("2. KRA"))
        keyboard.add(KeyboardButton("3. SHIF"))
        keyboard.add(KeyboardButton("4. Huduma Centre"))
        keyboard.add(KeyboardButton("0. Toka"))
    else:
        keyboard.add(KeyboardButton("1. Hospitals"))
        keyboard.add(KeyboardButton("2. KRA"))
        keyboard.add(KeyboardButton("3. SHIF"))
        keyboard.add(KeyboardButton("4. Huduma Centre"))
        keyboard.add(KeyboardButton("0. Exit"))
    return keyboard

@dp.message_handler(commands=['start'])
async def start_handler(message: Message):
    user_id = message.from_user.id

    if user_id in user_language:
        lang = user_language[user_id]
        await message.reply(
            "Karibu tena Msaidizi Mkononi!" if lang == "sw" else
            "Welcome back to Msaidizi Mkononi!",
            reply_markup=get_menu_keyboard(lang)
        )
        return

    await message.reply(
        "Karibu Msaidizi Mkononi!\nChagua lugha:\n1. Kiswahili\n2. English",
        reply_markup=ReplyKeyboardMarkup(
            resize_keyboard=True,
            keyboard=[
                [KeyboardButton("1. Kiswahili")],
                [KeyboardButton("2. English")]
            ]
        )
    )

@dp.message_handler(lambda m: m.text in ["1. Kiswahili", "2. English"])
async def language_handler(message: Message):
    user_id = message.from_user.id
    text = message.text

    if "Kiswahili" in text:
        lang = "sw"
        reply = "Asante! Tutazungumza kwa Kiswahili sasa."
    else:
        lang = "en"
        reply = "Thank you! We'll continue in English now."

    user_language[user_id] = lang
    await message.reply(reply, reply_markup=get_menu_keyboard(lang))

@dp.message_handler(content_types=['voice'])
async def handle_voice(message: types.Message):
    user_id = message.from_user.id

    if user_id not in user_language:
        await start_handler(message)
        return

    lang = user_language[user_id]

    # Show typing indicator (fixed)
    await bot.send_chat_action(message.chat.id, "typing")

    # Download voice file
    file = await bot.get_file(message.voice.file_id)
    file_path = file.file_path
    downloaded_file = await bot.download_file(file_path)

    # Save as temporary OGG
    with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as tmp_ogg:
        tmp_ogg.write(downloaded_file)
        ogg_path = tmp_ogg.name

    try:
        # Convert OGG to WAV
        audio = AudioSegment.from_ogg(ogg_path)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp_wav:
            wav_path = tmp_wav.name
            audio.export(wav_path, format="wav")

        # Transcribe
        r = sr.Recognizer()
        with sr.AudioFile(wav_path) as source:
            audio_data = r.record(source)
            try:
                text = r.recognize_google(audio_data, language="sw-KE")
                print(f"Voice transcribed (Swahili): {text}")
            except sr.UnknownValueError:
                try:
                    text = r.recognize_google(audio_data, language="en-KE")
                    print(f"Voice transcribed (English fallback): {text}")
                except sr.UnknownValueError:
                    text = None
                    await message.reply("Samahani, sielewi sauti yako." if lang == "sw" else "Sorry, I couldn't understand your voice.")
                except sr.RequestError:
                    text = None
                    await message.reply("Tatizo la mtandao wakati wa kusikiliza sauti." if lang == "sw" else "Network error while processing voice.")
            except Exception as e:
                text = None
                await message.reply("Tatizo la kiufundi wakati wa kusikiliza sauti." if lang == "sw" else "Technical issue processing voice.")

        # Clean up temp files
        os.unlink(ogg_path)
        os.unlink(wav_path)

        if text:
            # Send transcribed text to Rasa
            payload = {
                "sender": str(user_id),
                "message": text
            }

            async with aiohttp.ClientSession() as session:
                try:
                    async with session.post(RASA_URL, json=payload) as resp:
                        if resp.status == 200:
                            rasa_response = await resp.json()
                            if rasa_response and rasa_response[0].get("text"):
                                reply_text = rasa_response[0]["text"]
                                await message.reply(reply_text, reply_markup=get_menu_keyboard(lang))
                            else:
                                await message.reply("Samahani, sielewi." if lang == "sw" else "Sorry, I don't understand.")
                        else:
                            await message.reply("Tatizo la kiufundi." if lang == "sw" else "Technical issue.")
                except Exception as e:
                    logging.error(f"Rasa error: {e}")
                    await message.reply("Tatizo la kiufundi. Jaribu tena." if lang == "sw" else "Technical issue. Try again.")

    except Exception as e:
        logging.error(f"Voice processing error: {e}")
        await message.reply("Tatizo wakati wa kusikiliza sauti yako." if lang == "sw" else "Error processing your voice message.")

@dp.message_handler()
async def handle_text(message: Message):
    user_id = message.from_user.id
    text = message.text.strip()

    if user_id not in user_language:
        await start_handler(message)
        return

    lang = user_language[user_id]

    if len(text) < 2:
        await message.reply("Andika swali lako vizuri tafadhali." if lang == "sw" else "Please type a proper question.")
        return

    if text == "0" or text.lower() in ["toka", "exit"]:
        del user_language[user_id]
        await message.reply(
            "Asante kwa kutumia Msaidizi Mkononi! Karibu tena." if lang == "sw" else
            "Thank you for using Msaidizi Mkononi! Come back soon."
        )
        return

    # Show typing indicator (fixed)
    await bot.send_chat_action(message.chat.id, "typing")

    payload = {
        "sender": str(user_id),
        "message": text
    }

    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(RASA_URL, json=payload) as resp:
                if resp.status == 200:
                    rasa_response = await resp.json()
                    if rasa_response and rasa_response[0].get("text"):
                        reply_text = rasa_response[0]["text"]
                        await message.reply(reply_text, reply_markup=get_menu_keyboard(lang))
                    else:
                        await message.reply("Samahani, sielewi." if lang == "sw" else "Sorry, I don't understand.")
                else:
                    await message.reply("Tatizo la kiufundi." if lang == "sw" else "Technical issue.")
        except Exception as e:
            logging.error(f"Rasa error: {e}")
            await message.reply("Tatizo la kiufundi. Jaribu tena." if lang == "sw" else "Technical issue. Try again.")

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)