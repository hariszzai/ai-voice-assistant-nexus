# shared.py
from database import init_db, load_profile, load_voice_settings

# initialize database and create tables on first run
init_db()

# load saved profile and voice settings from database
_profile = load_profile()
_voice = load_voice_settings()

notifications_queue = []
custom_system_prompt = {"value": ""}
voice_mode_active = {"value": False}

# now populated from database instead of hardcoded defaults
voice_settings = {"voice": _voice["voice"], "speed": _voice["speed"]}
user_profile = {"name": _profile["name"], "city": _profile["city"]}