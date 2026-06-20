import uuid
from django.conf import settings
from django.db import models
from django.utils import timezone


class Friendship(models.Model):
    PENDING, ACCEPTED = "pending", "accepted"
    STATUS = ((PENDING, "pending"), (ACCEPTED, "accepted"))

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user_low = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    user_high = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    status = models.CharField(max_length=10, choices=STATUS, default=PENDING)
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user_low", "user_high"], name="uniq_friendship_pair")]

    @staticmethod
    def ordered(a, b):
        return (a, b) if str(a.id) < str(b.id) else (b, a)

    @classmethod
    def between(cls, a, b):
        low, high = cls.ordered(a, b)
        return cls.objects.filter(user_low=low, user_high=high).first()

    @classmethod
    def are_friends(cls, a, b):
        f = cls.between(a, b)
        return bool(f and f.status == cls.ACCEPTED)

    def other(self, user):
        return self.user_high if self.user_low_id == user.id else self.user_low


class Group(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=120)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="owned_groups")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class GroupMembership(models.Model):
    OWNER, ADMIN, MEMBER = "owner", "admin", "member"
    ROLES = ((OWNER, "owner"), (ADMIN, "admin"), (MEMBER, "member"))
    INVITED, ACTIVE, LEFT = "invited", "active", "left"
    STATUS = ((INVITED, "invited"), (ACTIVE, "active"), (LEFT, "left"))

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(max_length=10, choices=ROLES, default=MEMBER)
    status = models.CharField(max_length=10, choices=STATUS, default=INVITED)
    invited_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    joined_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["group", "user"], name="uniq_group_user")]
