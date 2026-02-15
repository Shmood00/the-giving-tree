import urequests
import os
import machine
import gc
import json
import time
import urandom
import mbedtls
import uhashlib

class OTAUpdater:
    PUBLIC_KEY = b'''-----BEGIN PUBLIC KEY-----
MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAE8y87fJqQsbcq4ER/RlSO6vnx07CX
MFKlJFQQVqm5SF38OdPHU3MvWO6DmL+RPFr01jSFOFQ0lsUXBMGa9BzEqA==
-----END PUBLIC KEY-----'''

    def __init__(self, repo_url, filenames):
        self.repo_url = repo_url
        self.filenames = filenames

    def _xor_crypt(self, data):
        if isinstance(data, str):
            data = data.encode()
        key = machine.unique_id()
        return bytes([data[i] ^ key[i % len(key)] for i in range(len(data))])

    def _verify_file(self, filename, signature_bytes):
        """Hash-based verification using PEM-format public key"""
        print(f"[OTA] Verifying hash signature for {filename}...")
        try:
            sha = uhashlib.sha256()
            with open(f"tmp_{filename}", "rb") as f:
                while True:
                    chunk = f.read(256)
                    if not chunk:
                        break
                    sha.update(chunk)

            digest = sha.digest()  # 32-byte SHA-256

            # Verify signature using public key
            valid = mbedtls.ec_key_verify(self.PUBLIC_KEY, digest, signature_bytes)

            if valid:
                print(f"[OTA] Hash signature valid for {filename}")
            else:
                print(f"[OTA] Hash signature INVALID for {filename}")

            return valid

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

                    # 1. Download File and Signature
                    if self._download_file(fname) and self._download_signature(fname):
                        with open(f"tmp_{fname}.sig", "rb") as s:
                            sig_data = s.read()

                        # 2. Verify using SHA-256 hash + PEM key
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
        """Download .sig file"""
        try:
            url = f"{self.repo_url}/signatures/{filename}.sig"
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
