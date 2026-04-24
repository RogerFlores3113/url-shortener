ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"


def base62_encode(n: int) -> str:
    if n == 0:
        return "0"
    result = []
    while n:
        result.append(ALPHABET[n % 62])
        n //= 62
    return "".join(reversed(result))


def to_short_code(id: int) -> str:
    encoded = base62_encode(id)
    return encoded.lstrip("0").rjust(7, "0")
