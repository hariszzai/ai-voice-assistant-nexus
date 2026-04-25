import os
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
import logging
logging.disable(logging.CRITICAL)
import warnings
warnings.filterwarnings("ignore")

import threading
import re
import speech_recognition as sr
import webbrowser
import requests
import musicLibrary as ml
import edge_tts
import asyncio
import pygame
import subprocess
import datetime
import pyautogui
import time
from shared import notifications_queue
import json
from shared import notifications_queue, custom_system_prompt, voice_mode_active, voice_settings, user_profile
from dotenv import load_dotenv
load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
NEWS_API_KEY = os.getenv("NEWS_API_KEY")
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")
HF_API_KEY = os.getenv("HF_API_KEY")
WAKE_WORD = "nexus"
conversation_history = []
reminders = []

def check_reminders():
    while True:
        now = datetime.datetime.now().strftime("%I:%M %p").lower()
        for reminder in reminders[:]:
            if reminder["time"] == now:
                speak(f"Reminder: {reminder['message']}")
                notifications_queue.append(f"Reminder: {reminder['message']}")
                # push to UI queue so chat shows it too
                reminders.remove(reminder)
        time.sleep(30)
            # check every 30 sec
# start reminder checker in background thread when program starts
reminder_thread = threading.Thread(target=check_reminders, daemon=True)
# daemon=True means thread dies when main program exits
reminder_thread.start()

r = sr.Recognizer()
r.dynamic_energy_threshold = False

def clean_for_speech(text):
    # remove emojis and markdown before speaking
    text = re.sub(r'[^\x00-\x7F]+', '', text)
    # removes all non-ASCII characters including emojis
    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
    # **bold** → just the word
    text = re.sub(r'\*(.*?)\*', r'\1', text)
    # *italic* → just the word
    text = re.sub(r'^##+ ', '', text, flags=re.MULTILINE)
    # remove heading symbols
    text = re.sub(r'^- ', '', text, flags=re.MULTILINE)
    # remove bullet dashes
    return text.strip()


def speak(text):
    text = clean_for_speech(text)
    # Generate a unique filename using timestamp
    filename = f"temp_{int(time.time() * 1000)}.mp3"
    
    async def _speak():
        v = voice_settings.get("voice", "en-US-BrianNeural")
        s = voice_settings.get("speed", "20")
        rate = f"+{s}%" if int(s) >= 0 else f"{s}%"
        communicate = edge_tts.Communicate(text, voice=v, rate=rate)
        await communicate.save(filename)
        pygame.mixer.init()
        pygame.mixer.music.load(filename)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            pygame.time.Clock().tick(10)
        pygame.mixer.music.unload()
        if os.path.exists(filename):
            os.remove(filename)

    thread = threading.Thread(target=lambda: asyncio.run(_speak()))
    thread.start()


def listen(timeout=2, phrase_limit=5):
    with sr.Microphone() as source:
        try:
            audio = r.listen(source, timeout=timeout, phrase_time_limit=phrase_limit)
            return r.recognize_google(audio).lower()
        except:
            return ""

def calibrate_microphone():
    print("Calibrating microphone...")
    with sr.Microphone() as source:
        r.adjust_for_ambient_noise(source, duration=1)
    print("Microphone ready.")


def fetch_news():
    res = requests.get(
        f"https://newsapi.org/v2/top-headlines?country=us&apiKey={NEWS_API_KEY}"
    )
    if res.status_code == 200:
        articles = res.json().get("articles", [])
        headlines = [a["title"] for a in articles[:3]]
        # combine into one speak call so no conflict
        full_text = "Here are the top headlines. " + ". Next, ".join(headlines)
        speak(full_text)
    else:
        speak("Sorry, couldn't fetch news right now.")

def fetch_weather(city="Delhi"):
    try:
        res = requests.get(
            f"https://api.openweathermap.org/data/2.5/weather?q={city}&appid={WEATHER_API_KEY}&units=metric"
        )
        data = res.json()   

        if data.get("cod") != 200:
            return f"Sorry, I couldn't find weather for {city}."

        city_name = data["name"]
        temp = data["main"]["temp"]
        feels_like = data["main"]["feels_like"]
        description = data["weather"][0]["description"]
        humidity = data["main"]["humidity"]

        return f"Weather in {city_name}: {description}, {temp} degrees celsius, feels like {feels_like} degrees celsius, humidity {humidity}%."

    except Exception as e:
        return "Sorry, couldn't fetch weather right now."
    
def get_battery():
    try:
        import psutil
        battery = psutil.sensors_battery()
        if battery:
            percent = int(battery.percent)
            charging = "and charging" if battery.power_plugged else "and not charging"
            return f"Battery is at {percent}% {charging}."
        return "Couldn't read battery status."
    except:
        return "Battery info not available."

def control_volume(command):
    try:
        from pycaw.pycaw import AudioUtilities

        device = AudioUtilities.GetSpeakers()
        volume = device.EndpointVolume
        if "unmute" in command:
            volume.SetMute(0, None)
            return "Unmuted."
        elif any(w in command for w in ["mute", "silent", "silence"]):
            volume.SetMute(1, None)
            return "Muted."
        elif any(w in command for w in ["max", "full", "maximum"]):
            volume.SetMasterVolumeLevelScalar(1.0, None)
            return "Volume set to maximum."
        elif any(w in command for w in ["up", "increase", "louder", "raise"]):
            current = volume.GetMasterVolumeLevelScalar()
            new_vol = min(1.0, current + 0.15)
            volume.SetMasterVolumeLevelScalar(new_vol, None)
            return f"Volume increased to {int(new_vol * 100)}%."
        elif any(w in command for w in ["down", "decrease", "lower", "quieter", "reduce"]):
            current = volume.GetMasterVolumeLevelScalar()
            new_vol = max(0.0, current - 0.15)
            volume.SetMasterVolumeLevelScalar(new_vol, None)
            return f"Volume decreased to {int(new_vol * 100)}%."
        else:
            current = volume.GetMasterVolumeLevelScalar()
            return f"Current volume is {int(current * 100)}%."

    except Exception as e:
        print(f"Volume error: {e}")
        return "Volume control failed."
    
def generate_image(prompt):
    try:
        import urllib.parse
        encoded_prompt = urllib.parse.quote(prompt)
        image_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=768&height=768&nologo=true"
        response = requests.get(image_url, timeout=60)
        if response.status_code == 200:
            image_path = os.path.join("static", "generated_image.png")
            with open(image_path, "wb") as f:
                f.write(response.content)
            print(f"Image saved to {image_path}")
            return "IMAGE_GENERATED"
        else:
            return "IMAGE_FAILED"
    except Exception as e:
        print(f"Image gen error: {e}")
        return "IMAGE_FAILED"

def play_music(song_name):
    song_key = song_name.lower().replace(" ", "_")
    link = ml.music.get(song_key)
    if link:
        webbrowser.open(link)
        return f"Playing {song_name}."
    else:
        # this URL format auto-plays the top result
        query = song_name.replace(" ", "+")
        webbrowser.open(f"https://www.youtube.com/results?search_query={query}")
        return f"Here's {song_name} on YouTube."

def set_reminder(command):
    try:
        # expected format: "set reminder at 5pm to drink water"
        # or "remind me at 5:30pm to call mom"
        
        # extract time — find "at X" pattern
        time_part = re.search(r'at (\d{1,2}(?::\d{2})?\s*(?:am|pm))', command, re.IGNORECASE)
        
        # extract message — find "to X" pattern
        message_part = re.search(r'\bto\b (.+)$', command, re.IGNORECASE)
        
        if not time_part or not message_part:
            return "Please say something like: set reminder at 5pm to drink water."
        
        time_str = time_part.group(1).strip().lower().replace(" ", "")
        message = message_part.group(1).strip()
        
        # convert to standard format matching datetime output
        # handles both "5pm" and "5:30pm"
        if ":" in time_str:
            reminder_time = datetime.datetime.strptime(time_str, "%I:%M%p").strftime("%I:%M %p").lower()
        else:
            reminder_time = datetime.datetime.strptime(time_str, "%I%p").strftime("%I:%M %p").lower()
        
        reminders.append({"time": reminder_time, "message": message})
        return f"Reminder set for {reminder_time} — {message}."
    
    except Exception as e:
        print(f"Reminder error: {e}")
        return "Sorry, I couldn't set that reminder. Try saying: set reminder at 5pm to drink water."
    
def analyze_image(question, image_base64, image_type="image/jpeg"):
    try:
        response = requests.post(
            url="https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "meta-llama/llama-4-scout-17b-16e-instruct",
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{image_type};base64,{image_base64}"
                                }
                            },
                            {
                                "type": "text",
                                "text": question
                            }
                        ]
                    }
                ],
                "max_tokens": 1024
            }
        )
        data = response.json()
        reply = data["choices"][0]["message"]["content"]
        # add to conversation history so follow up questions work
        conversation_history.append({"role": "user", "content": f"[Image uploaded] {question}"})
        conversation_history.append({"role": "assistant", "content": reply})
        return reply
    except Exception as e:
        print(f"Vision error: {e}")
        return "Sorry, I couldn't analyze that image."

def ask_ai(question, mode="voice"):
    try:
        conversation_history.append({"role": "user", "content": question})

        if custom_system_prompt["value"]:
            system_prompt = custom_system_prompt["value"]
        elif mode == "voice":
            name = user_profile.get("name", "")
            name_str = f" The user's name is {name}." if name else ""
            system_prompt = f"You are Nexus, a helpful voice assistant.{name_str} Keep answers short, natural and conversational. No bullet points, no markdown, no special characters — plain spoken English only."
        else:
            name = user_profile.get("name", "")
            name_str = f" The user's name is {name}." if name else ""
            system_prompt = f"""You are Nexus, a helpful AI assistant.{name_str} Follow these rules strictly:

1. For casual messages like greetings or small talk — reply casually in 1-2 sentences maximum. No formatting, no bullet points, just natural conversation.
2. For specific questions or requests for information — give a clear, well structured response using markdown formatting. Use **bold** for key terms, - for bullet points, ## for headings only when truly needed.
3. Use emojis sparingly — only in casual conversation, never in technical or informational responses.
4. Never over-explain. Match the length of your response to the complexity of the question."""
        response = requests.post(
            url="https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": [
                    {"role": "system", "content": system_prompt}
                ] + conversation_history
            }
        )
        data = response.json()
        reply = data["choices"][0]["message"]["content"]
        conversation_history.append({"role": "assistant", "content": reply})
        return reply

    except Exception as e:
        print(f"AI error: {e}")
        return "Sorry, I couldn't get an answer right now."
    
def detect_intent(command):
    try:
        response = requests.post(
            url="https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": [
                    {
                        "role": "system",
                        "content": """You are an intent classifier for a voice assistant called Nexus.
Analyze the user's command and return ONLY a JSON object with no extra text.

Possible intents:
- open_website (open google, youtube, netflix)
- open_app (notepad, calculator, camera, any app)
- play_music (play a song)
- get_time
- get_date
- take_screenshot
- lock_pc
- shutdown
- restart
- get_weather (extract city if mentioned)
- get_news
- set_reminder (extract time and message)
- generate_image (user wants to create/generate an image or picture)
- get_battery (user asks about battery level or status)
- volume_control (user wants to change volume, mute, unmute)
- change_voice (user wants to change voice to male or female)
- exit_conversation (user wants to stop, end, goodbye, dismiss assistant)
- general_query (anything else — questions, conversation)

Return this exact JSON format:
{
  "intent": "intent_name",
  "website": null,
  "app": null,
  "song": null,
  "city": null,
  "reminder_time": null,
  "reminder_message": null,
  "image_prompt": null,
  "query": null
}

Fill image_prompt with a detailed description when intent is generate_image.
Fill in the relevant fields based on the command.
For reminder_time use format like "5:00pm" or "3:30am".
For website return the full URL like "https://google.com".
For query copy the original command."""
                    },
                    {
                        "role": "user",
                        "content": command
                    }
                ]
            }
        )
        data = response.json()
        raw = data["choices"][0]["message"]["content"]
        # strip any accidental markdown code fences
        raw = raw.replace("```json", "").replace("```", "").strip()
        return json.loads(raw)
    except Exception as e:
        print(f"Intent error: {e}")
        # fallback — treat as general query if detection fails
        return {"intent": "general_query", "query": command}

def process_command(command):
    print(f"Detecting intent for: {command}")
    intent_data = detect_intent(command)
    intent = intent_data.get("intent", "general_query")
    print(f"Intent: {intent}")

    if intent == "open_website":
        url = intent_data.get("website") or "https://google.com"
        webbrowser.open(url)
        speak(f"Opening {url}")

    elif intent == "open_app":
        app = (intent_data.get("app") or "").lower()
        if "notepad" in app:
            subprocess.Popen("notepad.exe")
            speak("Opening Notepad.")
        elif "calculator" in app or "calc" in app:
            subprocess.Popen("calc.exe")
            speak("Opening Calculator.")
        elif "camera" in app:
            subprocess.Popen("start microsoft.windows.camera:", shell=True)
            speak("Opening Camera.")
        elif "whatsapp" in app:
            os.system("start shell:AppsFolder\\5319275A.WhatsAppDesktop_cv1g1gvanyjgm!App")
            speak("Opening WhatsApp.")
        elif "capcut" in app:
            os.system("start shell:AppsFolder\\Bytedance.CapCut")
            speak("Opening CapCut.")
        elif "instagram" in app:
            os.system("start shell:AppsFolder\\Facebook.InstagramBeta_8xx8rvfyw5nnt!App")
            speak("Opening Instagram.")
        elif "reddit" in app:
            os.system("start shell:AppsFolder\\redditTV.Reddit_99kbdge22ed1a!App")
            speak("Opening Reddit.")
        elif "pinterest" in app:
            os.system("start shell:AppsFolder\\1424566A.147190DF3DE79_5byw4zywtsh80!App")
            speak("Opening Pinterest.")
        elif "davinci" in app or "resolve" in app:
            os.system('start "" "{6D809377-6AF0-444B-8957-A3773F02200E}\\Blackmagic Design\\DaVinci Resolve\\Resolve.exe"')
            speak("Opening DaVinci Resolve.")
        elif "netflix" in app:
            os.system("start shell:AppsFolder\\4DF9E0F8.Netflix_mcm4njqhnhss8!Netflix.App")
            speak("Opening netflix.")
        elif "store" in app or "microsoft store" in app:
            os.system("start ms-windows-store:")
            speak("Opening Microsoft Store.")
        else:
            speak(f"Opening {app}.")
            # try direct start first, then PowerShell for Store apps
            result = os.system(f"start {app}")
            if result != 0:
                os.system(f'powershell -command "Start-Process \'{app}\'"')

    elif intent == "play_music":
        song = (intent_data.get("song") or "").lower()
        result = play_music(song)
        speak(result)

    elif intent == "get_time":
        now = datetime.datetime.now().strftime("%I:%M %p")
        speak(f"Current time is {now}")

    elif intent == "get_date":
        today = datetime.datetime.now().strftime("%B %d, %Y")
        speak(f"Today is {today}")

    elif intent == "take_screenshot":
        screenshot = pyautogui.screenshot()
        screenshot_path = os.path.join(os.path.expanduser("~"), "Desktop", "screenshot.png")
        screenshot.save(screenshot_path)
        speak("Screenshot saved to your desktop.")

    elif intent == "lock_pc":
        speak("Locking the screen.")
        os.system("rundll32.exe user32.dll,LockWorkStation")

    elif intent == "shutdown":
        speak("Shutting down. Goodbye.")
        os.system("shutdown /s /t 5")

    elif intent == "restart":
        speak("Restarting now.")
        os.system("shutdown /r /t 5")

    elif intent == "get_weather":
        # city = intent_data.get("city") or "Delhi"
        city = user_profile.get("city") or "Delhi"
        result = fetch_weather(city)
        speak(result)

    elif intent == "get_news":
        fetch_news()

    elif intent == "set_reminder":
        r_time = intent_data.get("reminder_time")
        r_msg = intent_data.get("reminder_message")
        if r_time and r_msg:
            # clean up time string and parse it
            r_time = r_time.strip().lower().replace(" ", "")
            try:
                if ":" in r_time:
                    reminder_time = datetime.datetime.strptime(r_time, "%I:%M%p").strftime("%I:%M %p").lower()
                else:
                    reminder_time = datetime.datetime.strptime(r_time, "%I%p").strftime("%I:%M %p").lower()
                reminders.append({"time": reminder_time, "message": r_msg})
                speak(f"Reminder set for {reminder_time} — {r_msg}.")
            except:
                speak("Sorry, I couldn't parse that time. Try saying 5pm or 5:30pm.")
        else:
            speak("Please tell me when and what to remind you about.")

    elif intent == "generate_image":
        prompt = intent_data.get("image_prompt") or intent_data.get("query") or command
        speak(f"Generating image of {prompt}, please wait.")
        result = generate_image(prompt)
        if result == "IMAGE_GENERATED":
            speak("Your image is ready.")
        elif result == "MODEL_LOADING":
            speak("The model is loading, try again in 20 seconds.")
        else:
            speak("Sorry, I couldn't generate that image.")

    elif intent == "get_battery":
        result = get_battery()
        speak(result)

    elif intent == "volume_control":
        result = control_volume(command)
        speak(result)

    elif intent == "change_voice":
        if "female" in command or "girl" in command or "woman" in command:
            voice_settings["voice"] = "en-US-JennyNeural"
            result = "Switching to female voice."
        else:
            voice_settings["voice"] = "en-US-GuyNeural"
            result = "Switching back to male voice."
        speak(result) 

    # elif any(phrase in command for phrase in ["describe yourself", "who are you", "what are you", "introduce yourself", "about yourself"]):
    #     description = "I am Nexus — an advanced AI assistant that controls your PC, answers anything, analyzes and generate images, and holds natural conversations and much more. Built from scratch, combining automation with artificial intelligence."
    #     speak(description)

    elif intent == "general_query":
        query = intent_data.get("query") or command
        answer = ask_ai(query)
        print(f"Nexus: {answer}")
        speak(answer)

def process_command_text(command):
    print(f"Detecting intent for: {command}")
    intent_data = detect_intent(command)
    intent = intent_data.get("intent", "general_query")
    print(f"Intent: {intent}")

    if intent == "open_website":
        url = intent_data.get("website") or "https://google.com"
        webbrowser.open(url)
        return f"Opening {url}."

    elif intent == "open_app":
        app = (intent_data.get("app") or "").lower()
        if "notepad" in app:
            subprocess.Popen("notepad.exe")
            return "Opening Notepad."
        elif "calculator" in app or "calc" in app:
            subprocess.Popen("calc.exe")
            return "Opening Calculator."
        elif "camera" in app:
            subprocess.Popen("start microsoft.windows.camera:", shell=True)
            return "Opening Camera."
        elif "whatsapp" in app:
            os.system("start shell:AppsFolder\\5319275A.WhatsAppDesktop_cv1g1gvanyjgm!App")
            return "Opening WhatsApp."
        elif "capcut" in app:
            os.system("start shell:AppsFolder\\Bytedance.CapCut")
            return "Opening CapCut."
        elif "instagram" in app:
            os.system("start shell:AppsFolder\\Facebook.InstagramBeta_8xx8rvfyw5nnt!App")
            return "Opening Instagram."
        elif "reddit" in app:
            os.system("start shell:AppsFolder\\redditTV.Reddit_99kbdge22ed1a!App")
            return "Opening Reddit."
        elif "pinterest" in app:
            os.system("start shell:AppsFolder\\1424566A.147190DF3DE79_5byw4zywtsh80!App")
            return "Opening Pinterest."
        elif "davinci" in app or "resolve" in app:
            os.system('start "" "{6D809377-6AF0-444B-8957-A3773F02200E}\\Blackmagic Design\\DaVinci Resolve\\Resolve.exe"')
            return "Opening DaVinci Resolve."
        elif "netflix" in app:
            os.system("start shell:AppsFolder\\4DF9E0F8.Netflix_mcm4njqhnhss8!Netflix.App")
            return "Opening netflix."
        elif "store" in app or "microsoft store" in app:
            os.system("start ms-windows-store:")
            return f"Opening Microsoft Store."
        else:
            os.system(f"start {app}")
            return f"Opening {app}."

    elif intent == "play_music":
        song = (intent_data.get("song") or "").lower()
        return play_music(song)

    elif intent == "get_time":
        now = datetime.datetime.now().strftime("%I:%M %p")
        return f"Current time is {now}."

    elif intent == "get_date":
        today = datetime.datetime.now().strftime("%B %d, %Y")
        return f"Today is {today}."

    elif intent == "take_screenshot":
        screenshot = pyautogui.screenshot()
        screenshot_path = os.path.join(os.path.expanduser("~"), "Desktop", "screenshot.png")
        screenshot.save(screenshot_path)
        return "Screenshot saved to your desktop."

    elif intent == "lock_pc":
        os.system("rundll32.exe user32.dll,LockWorkStation")
        return "Locking the screen."

    elif intent == "shutdown":
        os.system("shutdown /s /t 5")
        return "Shutting down in 5 seconds."

    elif intent == "restart":
        os.system("shutdown /r /t 5")
        return "Restarting in 5 seconds."

    elif intent == "get_weather":
        # city = intent_data.get("city") or "Delhi"
        city = user_profile.get("city") or "Delhi"
        return fetch_weather(city)

    elif intent == "get_news":
        res = requests.get(
            f"https://newsapi.org/v2/top-headlines?country=us&apiKey={NEWS_API_KEY}"
        )
        if res.status_code == 200:
            articles = res.json().get("articles", [])
            headlines = [a["title"] for a in articles[:3]]
            return "Here are the top headlines: " + " | ".join(headlines)
        else:
            return "Sorry, couldn't fetch news right now."

    elif intent == "set_reminder":
        r_time = intent_data.get("reminder_time")
        r_msg = intent_data.get("reminder_message")
        if r_time and r_msg:
            r_time = r_time.strip().lower().replace(" ", "")
            try:
                if ":" in r_time:
                    reminder_time = datetime.datetime.strptime(r_time, "%I:%M%p").strftime("%I:%M %p").lower()
                else:
                    reminder_time = datetime.datetime.strptime(r_time, "%I%p").strftime("%I:%M %p").lower()
                reminders.append({"time": reminder_time, "message": r_msg})
                return f"Reminder set for {reminder_time} — {r_msg}."
            except:
                return "Sorry, I couldn't parse that time. Try saying 5pm or 5:30pm."
        else:
            return "Please tell me when and what to remind you about."
        
    elif intent == "generate_image":
        prompt = intent_data.get("image_prompt") or intent_data.get("query") or command
        result = generate_image(prompt)
        if result == "IMAGE_GENERATED":
            return "IMAGE_GENERATED"
        elif result == "MODEL_LOADING":
            return "The model is loading, please wait about 20 seconds and try again."
        else:
            return "Sorry, couldn't generate that image right now."
        
    elif intent == "get_battery":
        return get_battery()

    elif intent == "volume_control":
        return control_volume(command)
    
    elif intent == "change_voice":
        if "female" in command or "girl" in command or "woman" in command:
            voice_settings["voice"] = "en-US-JennyNeural"
            result = "Switching to female voice."
        else:
            voice_settings["voice"] = "en-US-GuyNeural"
            result = "Switching back to male voice."
        return result

    # elif any(phrase in command for phrase in ["describe yourself", "who are you", "what are you", "introduce yourself", "about yourself"]):
    #     description = "I am Nexus — an advanced AI assistant that controls your PC, answers anything, analyzes and generate images, and holds natural conversations and much more. Built from scratch, combining automation with artificial intelligence."
    #     return description

    elif intent == "general_query":
        query = intent_data.get("query") or command
        return ask_ai(query, mode="text")

def wake_sequence():
    now = datetime.datetime.now()
    hour = now.hour
    if hour < 12:
        period = "in the morning"
    elif hour < 17:
        period = "in the afternoon"
    elif hour < 20:
        period = "in the evening"
    else:
        period = "at night"
    time_str = now.strftime("%I:%M").lstrip("0")
    
    weather_msg = ""
    try:
        city = user_profile.get("city") or "Delhi"
        res = requests.get(
            f"https://api.openweathermap.org/data/2.5/weather?q={city}&appid={WEATHER_API_KEY}&units=metric"
        )
        data = res.json()
        if data.get("cod") == 200:
            temp = round(data["main"]["temp"])
            desc = data["weather"][0]["description"]
            weather_msg = f"Weather today in {city} is {desc}, {temp} degrees Celsius."
    except:
        pass

    speak(f"Greetings, Sir. It's {time_str} {period}. {weather_msg} What can I do for you today?")
    time.sleep(2)
    webbrowser.open("http://localhost:5000/")
    # time.sleep(2)
    # webbrowser.open("spotify:track:1XrSjpNe49IiygZfzb74pk")    
    # time.sleep(2)
    # subprocess.Popen([r"C:\Users\hp\AppData\Local\Programs\Microsoft VS Code\Code.exe", "--reuse-window"])

def voice_assistant_loop():
    calibrate_microphone()
    speak("Hello sir, just say the name for the move.")
    print("Listening for wake word...")
    activated = False

    while True:
        if not activated:
            word = listen(timeout=2, phrase_limit=3)
            if word and any(w in word for w in [WAKE_WORD, "wake up nexus", "wakeup nexus", "hey nexus"]):
                print(f"Wake word detected: {word}")
                activated = True
                wake_sequence()
        else:
            voice_mode_active["value"] = True
            while True:
                command = listen(timeout=8, phrase_limit=None)
                if not command:
                    continue
                exit_intent = detect_intent(command)
                if exit_intent.get("intent") == "exit_conversation" or any(phrase in command for phrase in ["stop", "goodbye", "bye", "exit", "that's all", "thatsall", "tata"]):
                    voice_mode_active["value"] = False
                    speak("Alright, goodbye sir. Going back to standby.")
                    activated = False
                    break
                print(f"VOICE LOOP PROCESSING: {command}")
                process_command(command)
                time.sleep(0.5)

if __name__ == "__main__":
    # run standalone voice only mode without UI
    voice_assistant_loop()
# Updated