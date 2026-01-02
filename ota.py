import urequests
import os
import machine
import gc
import json
import time
import urandom
import uhashlib
try:
    import cryptolib # standard name in many production MPy builds
except ImportError:
    import ucryptolib as cryptolib

class OTAUpdater:
    # HARDCODED PUBLIC KEY (The contents of public.der in hex format)
    # Replace this with your actual key bytes
    PUBLIC_KEY = b'0Y0\x13\x06\x07*\x86H\xce=\x02\x01\x06\x08*\x86H\xce=\x03\x01\x07\x03B\x00\x04\xf3/;|\x9a\x90\xb1\xb7*\xe0D\x7fFT\x8e\xea\xf9\xf1\xd3\xb0\x970R\xa5$T\x10V\xa9\xb9H]\xfc9\xd3\xc7Ss/X\xee\x83\x98\xbf\x91<Z\xf4\xd64\x858T4\x96\xc5\x17\x04\xc1\x9a\xf4\x1c\xc4\xa8' 

    def __init__(self, repo_url, filenames):
        self.repo_url = repo_url
        self.filenames = filenames

    def _xor_crypt(self, data):
        if isinstance(data, str):
            data = data.encode()
        key = machine.unique_id()
        return bytes([data[i] ^ key[i % len(key)] for i in range(len(data))])

    def _verify_file(self, filename, signature_bytes):
        """Streaming SHA-256 hash verification against ECDSA signature."""
        print(f"[OTA] Verifying signature for {filename}...")
        sha = uhashlib.sha256()
        try:
            with open(f"tmp_{filename}", "rb") as f:
                while True:
                    chunk = f.read(256) # Larger chunks for faster hashing
                    if not chunk: break
                    sha.update(chunk)
            
            # Note: The actual verification call depends on your specific 
            # firmware's ECDSA implementation (mbedtls wrapper).
            # This is the conceptual call:
            return cryptolib.ecc_verify(self.PUBLIC_KEY, signature_bytes, sha.digest())
        except Exception as e:
            print(f"[OTA] Verification error: {e}")
            return False

    def check_and_update(self, local_config):
        if "versions" not in local_config:
            local_config["versions"] = {}

        gc.collect()
        updated = False
        cb = urandom.getrandbits(24)

        try:
            url = f"{self.repo_url}/versions.json?cb={cb}"
            print("[OTA] Checking for updates...")
            res = urequests.get(url)
            remote = res.json()
            res.close()

            for fname in self.filenames:
                local = local_config["versions"].get(fname, 0)
                remote_v = remote.get(fname, 0)

                if float(remote_v) > float(local):
                    print(f"[OTA] New version found for {fname}")
                    
                    # 1. Download File and its Signature
                    if self._download_file(fname) and self._download_signature(fname):
                        # 2. Verify Signature
                        with open(f"tmp_{fname}.sig", "rb") as s:
                            sig_data = s.read()
                        
                        if self._verify_file(fname, sig_data):
                            print(f"[OTA] {fname} verified. Applying...")
                            try: os.remove(fname)
                            except: pass
                            os.rename(f"tmp_{fname}", fname)
                            local_config["versions"][fname] = remote_v
                            updated = True
                        else:
                            print(f"[OTA] CRITICAL: {fname} signature invalid! Rejecting.")
                            os.remove(f"tmp_{fname}")
                        
                        try: os.remove(f"tmp_{fname}.sig")
                        except: pass
                else:
                    print(f"[OTA] {fname} OK")

            if updated:
                self._finalize_update(local_config)
                return True

        except Exception as e:
            print("[OTA] Failed:", e)
        return False

    def _download_signature(self, filename):
        """Downloads the .sig file for the target file."""
        try:
            url = f"{self.repo_url}/{filename}.sig"
            res = urequests.get(url)
            if res.status_code == 200:
                with open(f"tmp_{filename}.sig", "wb") as f:
                    f.write(res.content)
                res.close()
                return True
        except: pass
        return False

    def _download_file(self, filename):
        gc.collect()
        try:
            url = f"{self.repo_url}/{filename}"
            res = urequests.get(url, stream=True)
            if res.status_code == 200:
                tmp = f"tmp_{filename}"
                with open(tmp, "wb") as f:
                    while True:
                        chunk = res.raw.read(128)
                        if not chunk: break
                        f.write(chunk)
                res.close()
                return True
        except: pass
        return False

    def _finalize_update(self, config):
        try:
            print("[OTA] Saving config...")
            enc = self._xor_crypt(json.dumps(config))
            with open("config.dat.tmp", "wb") as f:
                f.write(enc)
            try: os.remove("config.dat")
            except: pass
            os.rename("config.dat.tmp", "config.dat")

            with open(".ota_running", "w") as f:
                f.write("1")

            print("[OTA] Rebooting...")
            time.sleep(1)
            machine.reset()
        except Exception as e:
            print("[OTA] Finalize failed:", e)
