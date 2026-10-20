"""The training website: sign-in, downloading lessons and tests, and uploading results (queued offline)."""
import datetime
import json
import os
import threading
import time
import urllib.error
import urllib.request
import uuid

from coach.config import ACCOUNT_FILE, CATALOG_FILE, OUTBOX_DIR, RESULTS_DIR, SITE_KEY, SITE_URL
from coach.log import dlog


class Offline(Exception):
    """The training site can't be reached (no internet, or the site is down)."""


class SiteError(Exception):
    """The site answered with an error, e.g. a wrong password or a rule that refused the request."""


class Cloud:
    """Talks to the training site. Everything here is safe to call from a background thread."""

    def __init__(self):
        self.lock = threading.Lock()
        self.access, self.expires = None, 0
        try:
            with open(ACCOUNT_FILE, encoding="utf-8") as fh:
                self.account = json.load(fh)
        except Exception:
            self.account = {}

    # --- plumbing
    def _http(self, method, path, body=None, token=None, headers=None, timeout=20):
        req = urllib.request.Request(SITE_URL + path, method=method,
                                     data=None if body is None else json.dumps(body).encode("utf-8"))
        req.add_header("apikey", SITE_KEY)
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", f"Bearer {token or SITE_KEY}")
        for k, v in (headers or {}).items():
            req.add_header(k, v)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as e:
            try:
                info = json.loads(e.read() or b"{}")
            except Exception:
                info = {}
            msg = info.get("msg") or info.get("message") or info.get("error_description") or info.get("error") or str(e)
            raise SiteError(f"{msg}") from None
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise Offline(str(e)) from None

    def _save(self):
        os.makedirs(RESULTS_DIR, exist_ok=True)
        with open(ACCOUNT_FILE, "w", encoding="utf-8") as fh:
            json.dump(self.account, fh)

    def _store_tokens(self, tok):
        self.access = tok["access_token"]
        self.expires = time.time() + int(tok.get("expires_in", 3600))
        self.account["refresh_token"] = tok["refresh_token"]
        self.account["user_id"] = tok.get("user", {}).get("id", self.account.get("user_id"))
        self._save()

    def token(self):
        with self.lock:
            if self.access and time.time() < self.expires - 60:
                return self.access
            if not self.account.get("refresh_token"):
                raise SiteError("Not signed in.")
            try:
                tok = self._http("POST", "/auth/v1/token?grant_type=refresh_token",
                                 {"refresh_token": self.account["refresh_token"]})
            except SiteError as e:
                dlog(f"sign-in expired: {e}")
                self.account.pop("refresh_token", None)
                self._save()
                raise SiteError("Your sign-in has expired. Please sign in again.") from None
            self._store_tokens(tok)
            return self.access

    def api(self, method, path, body=None, headers=None):
        return self._http(method, path, body, token=self.token(), headers=headers)

    def rpc(self, name, **args):
        return self.api("POST", f"/rest/v1/rpc/{name}", args)

    # --- account
    @property
    def signed_in(self):
        return bool(self.account.get("refresh_token"))

    def sign_in(self, email, password):
        tok = self._http("POST", "/auth/v1/token?grant_type=password", {"email": email.strip(), "password": password})
        with self.lock:
            self.account = {"email": email.strip()}
            self._store_tokens(tok)
        self.refresh_profile()

    def refresh_profile(self):
        rows = self.api("GET", f"/rest/v1/profiles?id=eq.{self.account['user_id']}"
                               "&select=full_name,role,companies(name)")
        if rows:
            p = rows[0]
            self.account.update(name=p.get("full_name") or self.account.get("email", ""), role=p.get("role"),
                                company=(p.get("companies") or {}).get("name", ""))
            self._save()

    def sign_out(self):
        with self.lock:
            self.account, self.access = {}, None
            try:
                os.remove(ACCOUNT_FILE)
            except OSError:
                pass

    # --- content
    def download_catalog(self):
        cat = {
            "lessons": self.api("GET", "/rest/v1/lessons?published=eq.true"
                                       "&select=id,title,tier,sort,block_ids,version&order=sort"),
            "tests": self.api("GET", "/rest/v1/tests?published=eq.true"
                                     "&select=id,title,tier,description,draw_count,pass_score,inactivity_minutes,sort"
                                     "&order=sort"),
            "blocks": self.api("GET", "/rest/v1/blocks?coach_ready=eq.true"
                                      "&select=id,title,tier,topic,steps,answer_key,version"),
            "downloaded": datetime.datetime.now().isoformat(timespec="seconds"),
        }
        with open(CATALOG_FILE, "w", encoding="utf-8") as fh:
            json.dump(cat, fh)
        return cat

    # --- results: queued on disk first, so nothing is lost if the PC is offline or the coach is closed
    def queue(self, item):
        os.makedirs(OUTBOX_DIR, exist_ok=True)
        path = os.path.join(OUTBOX_DIR, f"{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(item, fh, default=str)
        return path

    def pending(self):
        try:
            return sorted(f for f in os.listdir(OUTBOX_DIR) if f.endswith(".json"))
        except OSError:
            return []

    def flush(self):
        """Upload everything waiting. Returns (sent, still_waiting). Stops quietly when offline."""
        sent = 0
        if not self.signed_in:
            return 0, len(self.pending())
        for name in self.pending():
            path = os.path.join(OUTBOX_DIR, name)
            try:
                with open(path, encoding="utf-8") as fh:
                    item = json.load(fh)
                kind = item.pop("kind", "practice")
                if kind == "finish_test":
                    self.rpc("finish_test", p_session=item["session_id"], p_status=item["status"],
                             p_score=item.get("score"), p_summary=item.get("summary", {}))
                else:
                    self.api("POST", "/rest/v1/sessions?on_conflict=client_id", item,
                             headers={"Prefer": "resolution=ignore-duplicates,return=minimal"})
                os.remove(path)
                sent += 1
            except Offline:
                break
            except SiteError as e:
                if "sign" in str(e).lower():
                    break
                dlog(f"upload of {name} refused: {e}")
                os.makedirs(os.path.join(OUTBOX_DIR, "refused"), exist_ok=True)
                os.replace(path, os.path.join(OUTBOX_DIR, "refused", name))
            except Exception as e:
                dlog(f"upload of {name} failed: {e!r}")
                break
        return sent, len(self.pending())
