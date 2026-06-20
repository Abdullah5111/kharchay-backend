import pytest
from django.contrib.auth import get_user_model
from apps.social.models import Group, GroupMembership
from apps.settlement.models import Settlement

User = get_user_model()


def make_group(owner, *members):
    g = Group.objects.create(name="House 8", owner=owner)
    GroupMembership.objects.create(group=g, user=owner, role="owner", status="active")
    for m in members:
        GroupMembership.objects.create(group=g, user=m, role="member", status="active")
    return g


@pytest.mark.django_db
def test_settlement_period_unique():
    a = User.objects.create_user(email="a@e.com", name="A")
    g = make_group(a)
    Settlement.objects.create(group=g, year=2026, month=6)
    with pytest.raises(Exception):
        Settlement.objects.create(group=g, year=2026, month=6)
