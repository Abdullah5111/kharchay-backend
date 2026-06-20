from decimal import Decimal, ROUND_HALF_UP

CENT = Decimal("0.01")


def quantize(d):
    return Decimal(d).quantize(CENT, rounding=ROUND_HALF_UP)


def apportion(total, weights):
    """Split `total` across positions proportional to `weights`.

    Each position quantized to 2dp; the LAST position with a nonzero weight
    absorbs the rounding remainder so sum(result) == quantize(total) exactly.
    Zero-weight positions get 0.00.
    """
    total = quantize(total)
    weight_sum = sum(weights)
    n = len(weights)
    result = [Decimal("0.00")] * n
    if weight_sum == 0:
        return result
    last_nonzero = max(i for i, w in enumerate(weights) if w > 0)
    running = Decimal("0.00")
    for i, w in enumerate(weights):
        if w == 0:
            continue
        if i == last_nonzero:
            result[i] = total - running
        else:
            part = quantize(total * Decimal(w) / Decimal(weight_sum))
            result[i] = part
            running += part
    return result
