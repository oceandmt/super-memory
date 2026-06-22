"""Tests for safety.encryption module."""
from __future__ import annotations
from super_memory.safety.encryption import MemoryEncryptor

def test_roundtrip():
    key = MemoryEncryptor.generate_key()
    enc = MemoryEncryptor(key)
    assert enc.available
    ct = enc.encrypt("secret_data")
    pt = enc.decrypt(ct)
    assert pt == "secret_data"

def test_no_key_noop():
    enc = MemoryEncryptor()
    assert not enc.available
    assert enc.decrypt("test") == "test"
    assert enc.encrypt("test") == "test"

def test_dict_roundtrip():
    key = MemoryEncryptor.generate_key()
    enc = MemoryEncryptor(key)
    data = {"foo": "bar", "num": 42}
    encrypted = enc.encrypt_dict(data)
    assert "__encrypted__" in encrypted
    decrypted = enc.decrypt_dict(encrypted)
    assert decrypted == data

def test_dict_noop():
    enc = MemoryEncryptor()
    data = {"foo": "bar"}
    assert enc.encrypt_dict(data) == data
    assert enc.decrypt_dict(data) == data
