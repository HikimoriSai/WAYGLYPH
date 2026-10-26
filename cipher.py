import string

ALPHABET_SIZE = 26


def caesar_encrypt_letters(text, key):
    """Return text with shifted ASCII letters for the Caesar cipher helpers."""
    result = []
    for ch in text:
        if ch in string.ascii_letters:
            base = ord('A') if ch.isupper() else ord('a')
            shifted = (ord(ch) - base + key) % ALPHABET_SIZE
            result.append(chr(base + shifted))
        else:
            result.append(ch)
    return "".join(result)


def caesar_decrypt_letters(text, key):
    """Reverse the letter shift and return the restored text to the caller."""
    return caesar_encrypt_letters(text, -key)


def caesar_encrypt_message(text, key):
    """Shift letters and digits for the path string returned and exported by app.py."""
    text = caesar_encrypt_letters(text, key)
    return ''.join(str((int(ch) + key) % 10) if ch in string.digits else ch for ch in text)


def caesar_encrypt_number(value, key):
    """Return a digit-shifted edge weight for the path JSON and text export."""
    text = str(value)
    result = []
    for ch in text:
        if ch.isdigit():
            shifted = (int(ch) + key) % 10
            result.append(str(shifted))
        else:
            # '.', '-', etc. pass through unchanged
            result.append(ch)
    return "".join(result)


def caesar_decrypt_number(value_str, key):
    """Reverse digit shifts and return the original weight as text."""
    result = []
    for ch in value_str:
        if ch.isdigit():
            shifted = (int(ch) - key) % 10
            result.append(str(shifted))
        else:
            result.append(ch)
    return "".join(result)
