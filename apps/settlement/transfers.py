from decimal import Decimal


def minimize_transfers(nets):
    debtors = sorted(((k, v) for k, v in nets.items() if v > 0), key=lambda x: x[1], reverse=True)
    creditors = sorted(((k, -v) for k, v in nets.items() if v < 0), key=lambda x: x[1], reverse=True)
    debtors = [[k, v] for k, v in debtors]
    creditors = [[k, v] for k, v in creditors]
    transfers = []
    i = j = 0
    while i < len(debtors) and j < len(creditors):
        dk, dv = debtors[i]
        ck, cv = creditors[j]
        pay = min(dv, cv)
        if pay > 0:
            transfers.append({"from": dk, "to": ck, "amount": pay})
        debtors[i][1] -= pay
        creditors[j][1] -= pay
        if debtors[i][1] == 0:
            i += 1
        if creditors[j][1] == 0:
            j += 1
    return transfers
