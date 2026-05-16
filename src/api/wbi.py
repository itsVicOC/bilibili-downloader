"""WBI (Web Interface) signature module for Bilibili API anti-scraping."""

import hashlib
import time
import urllib.parse

# Obfuscation table from Bilibili's WBI algorithm
MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
    27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
    37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4,
    22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 34, 44, 52,
]


class WBISigner:
    """Stateless WBI signing utility.

    Usage:
        1. Get img_key and sub_key from /x/web-interface/nav response
        2. Compute mixin_key once, cache it
        3. Call sign() on every API request's query params
    """

    @staticmethod
    def extract_key_from_url(url: str) -> str:
        """Extract filename stem from Bilibili WBI image URL.

        e.g. 'https://i0.hdslb.com/bfs/wbi/abc123def456.png' -> 'abc123def456'
        """
        filename = url.rsplit("/", 1)[-1]
        return filename.split(".")[0]

    @staticmethod
    def compute_mixin_key(img_key: str, sub_key: str) -> str:
        """Compute the 32-character mixin key from WBI image keys.

        The mixin key is derived from img_key + sub_key using the
        obfuscation table. Bilibili rotates these keys periodically.
        """
        raw = img_key + sub_key
        return "".join(raw[i] for i in MIXIN_KEY_ENC_TAB)[:32]

    @staticmethod
    def sign(params: dict, mixin_key: str) -> dict:
        """Add WBI signature (wts + w_rid) to query parameters.

        Mutates and returns the params dict.

        Args:
            params: Query parameters to sign.
            mixin_key: 32-char key from compute_mixin_key().

        Returns:
            params dict with 'wts' and 'w_rid' added.
        """
        params["wts"] = int(time.time())

        # Strip characters Bilibili rejects in query values
        sanitized = {
            k: "".join(c for c in str(v) if c not in "!'()*")
            for k, v in params.items()
        }

        # Alphabetically sort, URL-encode, append mixin_key, MD5 hash
        sorted_params = dict(sorted(sanitized.items()))
        query = _urlencode(sorted_params)
        params["w_rid"] = hashlib.md5((query + mixin_key).encode()).hexdigest()

        return params


def _urlencode(params: dict) -> str:
    """URL-encode params without using urllib (avoids + for spaces)."""
    return urllib.parse.urlencode(params, safe="")
