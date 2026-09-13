import json
import os
import sys
import winreg

CONFIG_FILE = "config.json"
APP_NAME = "WindowsMultiAudioRouter"


def load_config():
    if not os.path.exists(CONFIG_FILE):
        return {
            "devices": {},
            "auto_mute_speakers": False,
            "start_on_boot": False,
            "github_repo": "User/Audio_router",  # Replace with your GitHub user/repo
        }
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if "devices" not in data:
                data = {"devices": data, "auto_mute_speakers": False, "start_on_boot": False}
            return data
    except Exception:
        return {"devices": {}, "auto_mute_speakers": False, "start_on_boot": False}


def save_config(data):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print(f"[Config Error] Failed to save config: {e}")


def set_windows_autostart(enable=True):
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_ALL_ACCESS)
        if enable:
            exe_path = f'"{sys.executable}"' if getattr(sys, "frozen", False) else f'"{sys.executable}" "{os.path.abspath("main.py")}"'
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, f"{exe_path} --minimized")
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
        return True
    except Exception as e:
        print(f"[Autostart Error]: {e}")
        return False