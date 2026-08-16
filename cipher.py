import string

ALPHABET_SIZE = 26


def caesar_encrypt_letters(text, key):
    result = []
    for ch in text:
        if ch.isalpha():
            base = ord('A') if ch.isupper() else ord('a')
            shifted = (ord(ch) - base + key) % ALPHABET_SIZE
            result.append(chr(base + shifted))
        else:
            result.append(ch)
    return "".join(result)


def caesar_decrypt_letters(text, key):
    return caesar_encrypt_letters(text, -key)


def caesar_encrypt_number(value, key):
    """
    value: float or int edge weight, e.g. 4.2
    key:   integer shift 0-25 (kept in same range as the UI slider for consistency)
    """
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
    result = []
    for ch in value_str:
        if ch.isdigit():
            shifted = (int(ch) - key) % 10
            result.append(str(shifted))
        else:
            result.append(ch)
    return "".join(result)
