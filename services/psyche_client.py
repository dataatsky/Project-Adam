import requests
import time
import logging


class PsycheClient:
    def __init__(self, base_url: str, *, timeout: float = 30.0, retries: int = 2, backoff: float = 0.5):
        self.base_url = base_url.rstrip("/")
        self.timeout = float(timeout)
        self.retries = int(retries)
        self.backoff = float(backoff)
        self.log = logging.getLogger(__name__ + ".PsycheClient")

    def generate_impulse(self, payload: dict) -> dict | None:
        url = f"{self.base_url}/generate_impulse"
        delay = self.backoff
        for attempt in range(self.retries + 1):
            try:
                r = requests.post(url, json=payload, timeout=self.timeout)
                r.raise_for_status()
                return r.json()
            except Exception as e:
                self.log.warning(f"{url} attempt {attempt+1} failed: {e}")
                if attempt < self.retries:
                    time.sleep(delay)
                    delay *= 2
                else:
                    return None

    def imagine(self, action: dict) -> str:
        url = f"{self.base_url}/imagine"
        delay = self.backoff
        for attempt in range(self.retries + 1):
            try:
                resp = requests.post(url, json={"action": action}, timeout=self.timeout)
                data = resp.json() or {}
                return data.get("outcome", "I imagine nothing happens.")
            except Exception as e:
                self.log.warning(f"{url} attempt {attempt+1} failed: {e}")
                if attempt < self.retries:
                    time.sleep(delay)
                    delay *= 2
                else:
                    return "My imagination is fuzzy."

    def reflect(self, payload: dict) -> dict:
        url = f"{self.base_url}/reflect"
        delay = self.backoff
        for attempt in range(self.retries + 1):
            try:
                r = requests.post(url, json=payload, timeout=self.timeout)
                r.raise_for_status()
                return r.json() or {}
            except Exception as e:
                self.log.warning(f"{url} attempt {attempt+1} failed: {e}")
                if attempt < self.retries:
                    time.sleep(delay)
                    delay *= 2
                else:
                    return {"final_action": {"verb": "wait", "target": "null"}, "reasoning": "Mind is blank."}
