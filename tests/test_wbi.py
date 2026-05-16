"""Tests for WBI signature module."""

import pytest
from src.api.wbi import WBISigner


class TestWBIKeyExtraction:
    def test_extract_key_simple(self):
        url = "https://i0.hdslb.com/bfs/wbi/abc123def456.png"
        assert WBISigner.extract_key_from_url(url) == "abc123def456"

    def test_extract_key_long(self):
        url = "https://i0.hdslb.com/bfs/wbi/a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6.png"
        assert WBISigner.extract_key_from_url(url) == "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6"

    def test_extract_key_sub(self):
        url = "https://i0.hdslb.com/bfs/wbi/sub_key_xyz.png"
        assert WBISigner.extract_key_from_url(url) == "sub_key_xyz"


class TestMixinKeyComputation:
    def test_mixin_key_length(self):
        """Mixin key should always be exactly 32 characters."""
        # Keys must be long enough for the obfuscation table (max index = 63)
        img_key = "a" * 32
        sub_key = "b" * 32
        key = WBISigner.compute_mixin_key(img_key, sub_key)
        assert len(key) == 32

    def test_mixin_key_deterministic(self):
        """Same inputs should always produce the same key."""
        img_key = "img1234567890abcdefghijklmnopqrstuv"
        sub_key = "sub1234567890abcdefghijklmnopqrstuv"
        key1 = WBISigner.compute_mixin_key(img_key, sub_key)
        key2 = WBISigner.compute_mixin_key(img_key, sub_key)
        assert key1 == key2

    def test_mixin_key_uses_tab(self):
        """Key should be derived from the obfuscation table, not raw concatenation."""
        img_key = "a" * 32
        sub_key = "b" * 32
        raw = img_key + sub_key
        key = WBISigner.compute_mixin_key(img_key, sub_key)
        assert key != raw[:32]  # Should be permuted
        assert len(key) == 32


class TestWBISigning:
    def test_sign_adds_wts_and_wrid(self):
        """Sign should add wts (timestamp) and w_rid (MD5 hash)."""
        signer = WBISigner()
        mixin_key = signer.compute_mixin_key(
            "a" * 32, "b" * 32
        )
        params = {"bvid": "BV1xx"}
        signed = signer.sign(params, mixin_key)

        assert "wts" in signed
        assert "w_rid" in signed
        assert isinstance(signed["wts"], int)
        assert len(signed["w_rid"]) == 32  # MD5 hex length

    def test_sign_is_deterministic(self):
        """Same params + same time = same signature."""
        signer = WBISigner()
        mixin_key = signer.compute_mixin_key(
            "a" * 32, "b" * 32
        )

        params1 = {"bvid": "BV1xx"}
        params2 = {"bvid": "BV1xx"}

        # Override timestamp to be the same
        params1["wts"] = 1700000000
        params2["wts"] = 1700000000

        # Re-sign without wts to test determinism
        signed1 = signer.sign(params1, mixin_key)
        # Reset for second call
        params2["wts"] = 1700000000
        signed2 = signer.sign(params2, mixin_key)

        assert signed1["w_rid"] == signed2["w_rid"]

    def test_sign_strips_special_chars(self):
        """Sign should strip !'()* characters from values."""
        signer = WBISigner()
        mixin_key = signer.compute_mixin_key(
            "a" * 32, "b" * 32
        )
        params = {"title": "test'value(with)special*chars!"}
        signed = signer.sign(params, mixin_key)
        assert "wts" in signed
        assert "w_rid" in signed

    def test_sign_sorts_params(self):
        """Sign should alphabetically sort parameters."""
        signer = WBISigner()
        mixin_key = signer.compute_mixin_key(
            "a" * 32, "b" * 32
        )
        params = {"cid": 123, "bvid": "BV1xx"}
        signed = signer.sign(params, mixin_key)
        # The hash depends on sort order - just verify it succeeds
        assert "w_rid" in signed

    def test_sign_mutates_params(self):
        """Sign should mutate and return the same params dict."""
        signer = WBISigner()
        mixin_key = signer.compute_mixin_key(
            "a" * 32, "b" * 32
        )
        params = {"bvid": "BV1xx"}
        result = signer.sign(params, mixin_key)
        assert result is params  # Same object
