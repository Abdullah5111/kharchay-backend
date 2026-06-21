from decimal import Decimal, ROUND_HALF_UP
from rest_framework import serializers


def build_shares(amount, split_type, involved_users, custom):
    """Return list of (user, Decimal amount). Validates and raises serializers.ValidationError."""
    if split_type == "custom":
        if not custom:
            raise serializers.ValidationError("Custom split requires per-member amounts.")
        seen = set()
        for c in custom:
            u = c["user"]
            uid = str(getattr(u, "id", u))
            if uid in seen:
                raise serializers.ValidationError("A member appears more than once in the custom split.")
            seen.add(uid)
            if Decimal(str(c["amount"])) <= 0:
                raise serializers.ValidationError("Each custom share must be greater than zero.")
        total = sum((Decimal(str(c["amount"])) for c in custom), Decimal("0"))
        if total != Decimal(str(amount)):
            raise serializers.ValidationError("Custom shares must sum to the total amount.")
        return [(c["user"], Decimal(str(c["amount"]))) for c in custom]
    # equal
    users = list(involved_users)
    if not users:
        raise serializers.ValidationError("Select at least one member to split between.")
    amount = Decimal(str(amount))
    n = len(users)
    base = (amount / n).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    shares = [base] * n
    # last member absorbs the rounding remainder so shares sum exactly to amount
    shares[-1] = amount - base * (n - 1)
    return list(zip(users, shares))
