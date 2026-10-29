"""Persist check diagnostics; scheduling belongs to HA's coordinator."""
import json
import time
from pathlib import Path


class DailyGate:
    def __init__(self, path, payment_code):
        self.path = Path(path)
        self.payment_code = payment_code
        self.last_attempt = None
        self.next_check = 0
        self.status = 'starting'
        try:
            saved = json.loads(self.path.read_text())
            if saved['payment_code'] == payment_code:
                self.last_attempt = saved['last_attempt']
                self.next_check = saved['next_check']
                self.status = saved['status']
        except (OSError, ValueError, KeyError):
            pass

    def reserve(self, now=None):
        now = time.time() if now is None else now
        self.last_attempt = now
        self.next_check = now + 86400
        self.set_status('collection_failed')
        return True

    def set_status(self, status):
        self.status = status
        temp = self.path.with_suffix('.tmp')
        temp.write_text(json.dumps(dict(payment_code=self.payment_code,
            status=status, last_attempt=self.last_attempt, next_check=self.next_check)))
        temp.replace(self.path)
