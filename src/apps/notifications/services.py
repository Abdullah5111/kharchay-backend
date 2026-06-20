from apps.accounts.models import DeviceToken
from .models import Notification
from .tasks import send_push


def notify(users, type, title, body, data=None):
    data = data or {}
    Notification.objects.bulk_create([
        Notification(user=u, type=type, title=title, body=body, data=data) for u in users
    ])
    tokens = list(DeviceToken.objects.filter(user__in=users).values_list("expo_push_token", flat=True))
    if tokens:
        try:
            send_push.delay(tokens, title, body, data)
        except Exception:
            pass  # broker unavailable; in-app feed already recorded
