# config_loader.py
import os, gc, json, machine

_settings = None

def get_config():
    global _settings
    if _settings is not None:
        return _settings

    # --- Decryption Logic ---
    try:
        filename = "config.dat"
        os.stat(filename)
    except OSError:
        filename = "config.json"

    try:
        with open(filename, "rb") as f:
            data = bytearray(f.read())
        
        if filename.endswith(".dat"):
            key = machine.unique_id()
            kl = len(key)
            for i in range(len(data)):
                data[i] ^= key[i % kl]
        
        _settings = json.loads(data)
        del data
        gc.collect()
        return _settings
    except Exception as e:
        print("[Config] Error:", e)
        return {} # Fallback
