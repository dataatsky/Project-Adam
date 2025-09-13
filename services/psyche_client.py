import requests


class PsycheClient:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    def generate_impulse(self, payload: dict) -> dict | None:
        try:
            r = requests.post(f"{self.base_url}/generate_impulse", json=payload, timeout=30)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            print(f"/generate_impulse error: {e}")
            return None

    def imagine(self, action: dict) -> str:
        try:
            resp = requests.post(f"{self.base_url}/imagine", json={"action": action}, timeout=30)
            data = resp.json() or {}
            return data.get("outcome", "I imagine nothing happens.")
        except Exception as e:
            print(f"/imagine error: {e}")
            return "My imagination is fuzzy."

    def reflect(self, payload: dict) -> dict:
        try:
            r = requests.post(f"{self.base_url}/reflect", json=payload, timeout=60)
            r.raise_for_status()
            return r.json() or {}
        except Exception as e:
            print(f"/reflect error: {e}")
            return {"final_action": {"verb": "wait", "target": "null"}, "reasoning": "Mind is blank."}

