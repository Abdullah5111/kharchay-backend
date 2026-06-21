import pytest
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import RefreshToken
from apps.social.models import Group, GroupMembership
from apps.ledger.models import Category
from apps.haazri.models import MealEvent, MealAttendance, AttendanceDispute
from apps.notifications.models import Notification

User = get_user_model()


def auth(c, u):
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(u).access_token}")


def make_group(owner, *members):
    g = Group.objects.create(name="TestGroup", owner=owner)
    GroupMembership.objects.create(group=g, user=owner, role="owner", status="active")
    for m in members:
        GroupMembership.objects.create(group=g, user=m, role="member", status="active")
    return g


def make_admin(g, user):
    GroupMembership.objects.filter(group=g, user=user).update(role="admin")


def pool(g, name):
    return Category.objects.create(group=g, ledger_type="kitchen_pool", name=name)


def event(c, g, cat, date="2026-06-05"):
    return c.post(f"/api/groups/{g.id}/haazri/", {"category": str(cat.id), "date": date}, format="json").json()


@pytest.mark.django_db
def test_member_disputes_own_attendance(api_client):
    """A member disputes their own attendance → 201 + group admins/owner get attendance_disputed notification."""
    owner = User.objects.create_user(email="owner@e.com", name="Owner")
    admin = User.objects.create_user(email="admin@e.com", name="Admin")
    member = User.objects.create_user(email="member@e.com", name="Member")
    g = make_group(owner, admin, member)
    make_admin(g, admin)
    lunch = pool(g, "Lunch")

    ev = MealEvent.objects.create(group=g, category=lunch, date="2026-06-01", created_by=owner)
    att = MealAttendance.objects.create(meal_event=ev, user=member, multiplier=1)

    auth(api_client, member)
    r = api_client.post(
        f"/api/haazri/attendance/{att.id}/dispute/",
        {"reason": "I was not present"},
        format="json",
    )
    assert r.status_code == 201

    # owner and admin should be notified
    admin_notif = Notification.objects.filter(user=admin, type="attendance_disputed").first()
    owner_notif = Notification.objects.filter(user=owner, type="attendance_disputed").first()
    assert admin_notif is not None
    assert owner_notif is not None


@pytest.mark.django_db
def test_other_member_cannot_dispute_someone_elses_attendance(api_client):
    """A different member cannot dispute someone else's attendance → 404."""
    owner = User.objects.create_user(email="owner@e.com", name="Owner")
    a = User.objects.create_user(email="a@e.com", name="A")
    b = User.objects.create_user(email="b@e.com", name="B")
    g = make_group(owner, a, b)
    lunch = pool(g, "Lunch")

    ev = MealEvent.objects.create(group=g, category=lunch, date="2026-06-01", created_by=owner)
    att = MealAttendance.objects.create(meal_event=ev, user=a, multiplier=1)

    # b tries to dispute a's attendance
    auth(api_client, b)
    r = api_client.post(
        f"/api/haazri/attendance/{att.id}/dispute/",
        {"reason": "Trying to dispute someone else"},
        format="json",
    )
    assert r.status_code == 404


@pytest.mark.django_db
def test_member_cannot_list_disputes(api_client):
    """A regular member cannot list disputes → 403."""
    owner = User.objects.create_user(email="owner@e.com", name="Owner")
    member = User.objects.create_user(email="member@e.com", name="Member")
    g = make_group(owner, member)

    auth(api_client, member)
    r = api_client.get(f"/api/groups/{g.id}/haazri/disputes/")
    assert r.status_code == 403


@pytest.mark.django_db
def test_admin_can_list_open_disputes(api_client):
    """Admin can list open disputes (sees dispute data)."""
    owner = User.objects.create_user(email="owner@e.com", name="Owner")
    member = User.objects.create_user(email="member@e.com", name="Member")
    g = make_group(owner, member)
    lunch = pool(g, "Lunch")

    ev = MealEvent.objects.create(group=g, category=lunch, date="2026-06-01", created_by=owner)
    att = MealAttendance.objects.create(meal_event=ev, user=member, multiplier=1)

    # Create a dispute
    auth(api_client, member)
    api_client.post(
        f"/api/haazri/attendance/{att.id}/dispute/",
        {"reason": "I was not present"},
        format="json",
    )

    # Admin lists disputes
    auth(api_client, owner)
    r = api_client.get(f"/api/groups/{g.id}/haazri/disputes/")
    assert r.status_code == 200
    disputes = r.json()
    assert len(disputes) == 1
    assert disputes[0]["status"] == "open"
    assert disputes[0]["reason"] == "I was not present"


@pytest.mark.django_db
def test_admin_resolves_dispute(api_client):
    """Admin resolves dispute with action=resolve → status becomes resolved."""
    owner = User.objects.create_user(email="owner@e.com", name="Owner")
    member = User.objects.create_user(email="member@e.com", name="Member")
    g = make_group(owner, member)
    lunch = pool(g, "Lunch")

    ev = MealEvent.objects.create(group=g, category=lunch, date="2026-06-01", created_by=owner)
    att = MealAttendance.objects.create(meal_event=ev, user=member, multiplier=1)

    # Create a dispute as member
    auth(api_client, member)
    api_client.post(
        f"/api/haazri/attendance/{att.id}/dispute/",
        {"reason": "Not present"},
        format="json",
    )

    # Get the dispute
    from apps.haazri.models import AttendanceDispute
    dispute = AttendanceDispute.objects.first()

    # Owner resolves it
    auth(api_client, owner)
    r = api_client.post(
        f"/api/haazri/disputes/{dispute.id}/resolve/",
        {"action": "resolve"},
        format="json",
    )
    assert r.status_code == 200
    dispute.refresh_from_db()
    assert dispute.status == "resolved"


@pytest.mark.django_db
def test_admin_rejects_dispute(api_client):
    """Admin rejects dispute with action=reject → status becomes rejected."""
    owner = User.objects.create_user(email="owner@e.com", name="Owner")
    member = User.objects.create_user(email="member@e.com", name="Member")
    g = make_group(owner, member)
    lunch = pool(g, "Lunch")

    ev = MealEvent.objects.create(group=g, category=lunch, date="2026-06-01", created_by=owner)
    att = MealAttendance.objects.create(meal_event=ev, user=member, multiplier=1)

    # Create a dispute as member
    auth(api_client, member)
    api_client.post(
        f"/api/haazri/attendance/{att.id}/dispute/",
        {"reason": "I disagree"},
        format="json",
    )

    # Get the dispute
    from apps.haazri.models import AttendanceDispute
    dispute = AttendanceDispute.objects.first()

    # Owner rejects it
    auth(api_client, owner)
    r = api_client.post(
        f"/api/haazri/disputes/{dispute.id}/resolve/",
        {"action": "reject"},
        format="json",
    )
    assert r.status_code == 200
    dispute.refresh_from_db()
    assert dispute.status == "rejected"


@pytest.mark.django_db
def test_non_member_cannot_resolve_dispute(api_client):
    a = User.objects.create_user(email="a@e.com", name="A")
    b = User.objects.create_user(email="b@e.com", name="B")
    outsider = User.objects.create_user(email="o@e.com", name="O")
    g = make_group(a, b)
    lunch = pool(g, "Lunch")
    auth(api_client, a)
    eid = event(api_client, g, lunch)["id"]
    api_client.put(f"/api/haazri/{eid}/attendance/", {"entries": [{"user": str(b.id), "multiplier": 1}]}, format="json")
    auth(api_client, b)
    att_id = api_client.get(f"/api/me/haazri/?group={g.id}&year=2026&month=6").json()[0]["attendance_id"]
    api_client.post(f"/api/haazri/attendance/{att_id}/dispute/", {"reason": "not me"}, format="json")
    did = AttendanceDispute.objects.first().id
    auth(api_client, outsider)
    assert api_client.post(f"/api/haazri/disputes/{did}/resolve/", {"action": "resolve"}, format="json").status_code == 404


@pytest.mark.django_db
def test_duplicate_dispute_rejected(api_client):
    a = User.objects.create_user(email="a@e.com", name="A")
    b = User.objects.create_user(email="b@e.com", name="B")
    g = make_group(a, b)
    lunch = pool(g, "Lunch")
    auth(api_client, a)
    eid = event(api_client, g, lunch)["id"]
    api_client.put(f"/api/haazri/{eid}/attendance/", {"entries": [{"user": str(b.id), "multiplier": 1}]}, format="json")
    auth(api_client, b)
    att_id = api_client.get(f"/api/me/haazri/?group={g.id}&year=2026&month=6").json()[0]["attendance_id"]
    assert api_client.post(f"/api/haazri/attendance/{att_id}/dispute/", {"reason": "x"}, format="json").status_code == 201
    assert api_client.post(f"/api/haazri/attendance/{att_id}/dispute/", {"reason": "x again"}, format="json").status_code == 400
