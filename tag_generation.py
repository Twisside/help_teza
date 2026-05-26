import json
import os

import requests
import subprocess
import time
from datetime import datetime

SETTINGS_FILE = "./settings.json"

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {"stay_loaded": True, "target_model": None}

settings = load_settings()
def _ts():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def generate_tags_with_llm(text_content, stay_loaded=False):
    url = "http://127.0.0.1:1234/v1/chat/completions"
    prompt = f"Extract 2-3 highly specific categories or tags for this text. Return ONLY the tags separated by commas. No intro.\nText: {text_content[:500]}"

    needs_unload = False
    if not stay_loaded:
        print(f"[{_ts()}] TAG: Loading model for tag generation...")
        result = subprocess.run(["lms", "load", settings.get("target_model")], check=False)
        if result.returncode != 0:
            print(f"[{_ts()}] TAG: Failed to load model for tag generation. Using default tags.")
            return ["auto-categorized"]
        time.sleep(2)
        needs_unload = True

    try:
        print(f"[{_ts()}] TAG: Calling LLM for tag generation...")
        response = requests.post(url, json={
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1
        }, timeout=30)
        raw_tags = response.json()['choices'][0]['message']['content']
        print(f"[{_ts()}] TAG: Received tag response: {raw_tags}")
        tags = [t.strip().lower() for t in raw_tags.split(',') if t.strip()]
    except Exception as e:
        print(f"Tag generation failed: {e}")
        tags = ["auto-categorized"]
    finally:
        if needs_unload:
            print(f"[{_ts()}] TAG: Unloading model after tag generation...")
            subprocess.run(["lms", "unload", settings.get("target_model")], check=False)

    return tags