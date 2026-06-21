from collections import defaultdict
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db.models import Sum

from apps.ledger.models import Category, Expense, ExpenseShare
from apps.haazri.models import MealEvent, MealAttendance, ExtraAmount
from .money import quantize, apportion

NON_KITCHEN = ("monthly_expense", "workplace")


def compute_settlement(group, year, month):
    paid = defaultdict(lambda: Decimal("0.00"))
    owed = defaultdict(lambda: Decimal("0.00"))
    bd = defaultdict(lambda: {"non_kitchen": [], "kitchen": [], "extras": [], "paid": []})
    users = {}

    def remember(u):
        users[u.id] = u
        return u.id

    # --- Non-kitchen + kitchen expense PAID side, and non-kitchen OWED side ---
    expenses = (Expense.objects
                .filter(group=group, date__year=year, date__month=month)
                .select_related("paid_by", "category")
                .prefetch_related("shares__user"))
    for e in expenses:
        pid = remember(e.paid_by)
        paid[pid] += e.amount
        bd[pid]["paid"].append({
            "label": e.title or e.category.name, "ledger_type": e.ledger_type, "amount": e.amount,
        })
        if e.ledger_type in NON_KITCHEN:
            for s in e.shares.all():
                uid = remember(s.user)
                owed[uid] += s.amount
                bd[uid]["non_kitchen"].append({
                    "ledger_type": e.ledger_type, "category_name": e.category.name, "amount": s.amount,
                })

    # --- Kitchen pool OWED side (rate x units, remainder-absorbed) ---
    pool_ids = (MealEvent.objects
                .filter(group=group, date__year=year, date__month=month)
                .values_list("category_id", flat=True).distinct())
    for pool_id in pool_ids:
        pool_spend = Expense.objects.filter(
            group=group, ledger_type="kitchen", category_id=pool_id,
            date__year=year, date__month=month,
        ).aggregate(t=Sum("amount"))["t"] or Decimal("0.00")
        units_qs = (MealAttendance.objects.filter(
            meal_event__group=group, meal_event__category_id=pool_id,
            meal_event__date__year=year, meal_event__date__month=month,
        ).values("user").annotate(u=Sum("multiplier")))
        rows = list(units_qs)
        total_units = sum(r["u"] for r in rows)
        if pool_spend == 0 or total_units == 0:
            continue
        member_ids = [r["user"] for r in rows]
        umap = {u.id: u for u in get_user_model().objects.filter(id__in=member_ids)}
        weights = [Decimal(r["u"]) for r in rows]
        amounts = apportion(pool_spend, weights)
        rate = pool_spend / Decimal(total_units)
        pool_name = Category.objects.get(id=pool_id).name
        for r, amt in zip(rows, amounts):
            u = umap.get(r["user"])
            if u is None:
                continue
            uid = remember(u)
            owed[uid] += amt
            bd[uid]["kitchen"].append({
                "pool_name": pool_name, "units": int(r["u"]),
                "rate": str(quantize(rate)), "amount": amt,
            })

    # --- Extras: PAID side to paid_by, OWED side weighted by multiplier per event ---
    events = (MealEvent.objects
              .filter(group=group, date__year=year, date__month=month)
              .select_related("category")
              .prefetch_related("attendance__user", "extras__paid_by"))
    for ev in events:
        att = list(ev.attendance.all())
        for ex in ev.extras.all():
            pid = remember(ex.paid_by)
            paid[pid] += ex.amount
            bd[pid]["paid"].append({
                "label": ex.title, "ledger_type": "kitchen_extra", "amount": ex.amount,
            })
            if not att:
                continue
            weights = [Decimal(a.multiplier) for a in att]
            amounts = apportion(ex.amount, weights)
            for a, amt in zip(att, amounts):
                uid = remember(a.user)
                owed[uid] += amt
                bd[uid]["extras"].append({
                    "pool_name": ev.category.name, "date": ev.date.isoformat(),
                    "title": ex.title, "amount": amt,
                })

    lines = {}
    for uid, u in users.items():
        p = quantize(paid[uid])
        o = quantize(owed[uid])
        lines[uid] = {
            "user": u, "paid_total": p, "owed_total": o, "net": quantize(o - p),
            "breakdown": bd[uid],
        }
    return {"participants": list(users.values()), "lines": lines}
