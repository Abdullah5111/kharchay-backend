import pytest
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import RefreshToken
from apps.social.models import Group, GroupMembership
from apps.ledger.models import Category
from apps.notifications.models import Notification

User=get_user_model()
def auth(c,u): c.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(u).access_token}")
def make_group(owner,*m):
    g=Group.objects.create(name="H",owner=owner); GroupMembership.objects.create(group=g,user=owner,role="owner",status="active")
    for x in m: GroupMembership.objects.create(group=g,user=x,role="member",status="active")
    return g
def pool(g,name): return Category.objects.create(group=g,ledger_type="kitchen_pool",name=name)
def event(c,g,cat,date="2026-06-05"):
    return c.post(f"/api/groups/{g.id}/haazri/",{"category":str(cat.id),"date":date},format="json").json()

@pytest.mark.django_db
def test_set_roster_with_multiplier_and_notifies(api_client):
    a=User.objects.create_user(email="a@e.com",name="A"); b=User.objects.create_user(email="b@e.com",name="B")
    g=make_group(a,b); lunch=pool(g,"Lunch"); auth(api_client,a)
    eid=event(api_client,g,lunch)["id"]
    r=api_client.put(f"/api/haazri/{eid}/attendance/",{"entries":[
        {"user":str(a.id),"multiplier":1},{"user":str(b.id),"multiplier":2,"guest_label":"cousin"}]},format="json")
    assert r.status_code==200
    # a and b both got notified (newly added)
    assert Notification.objects.filter(user=a,type="meal_marked").count()==1
    assert Notification.objects.filter(user=b,type="meal_marked").count()==1
    day=api_client.get(f"/api/groups/{g.id}/haazri/?date=2026-06-05").json()
    att={x["user"]["id"]:x for x in day[0]["attendance"]}
    assert att[str(b.id)]["multiplier"]==2 and att[str(b.id)]["guest_label"]=="cousin"

@pytest.mark.django_db
def test_roster_replace_does_not_renotify_existing(api_client):
    a=User.objects.create_user(email="a@e.com",name="A"); b=User.objects.create_user(email="b@e.com",name="B")
    g=make_group(a,b); lunch=pool(g,"Lunch"); auth(api_client,a)
    eid=event(api_client,g,lunch)["id"]
    api_client.put(f"/api/haazri/{eid}/attendance/",{"entries":[{"user":str(b.id),"multiplier":1}]},format="json")
    api_client.put(f"/api/haazri/{eid}/attendance/",{"entries":[{"user":str(b.id),"multiplier":1},{"user":str(a.id),"multiplier":1}]},format="json")
    assert Notification.objects.filter(user=b,type="meal_marked").count()==1  # not renotified
    assert Notification.objects.filter(user=a,type="meal_marked").count()==1  # newly added


@pytest.mark.django_db
def test_member_cannot_set_roster(api_client):
    a = User.objects.create_user(email="a@e.com", name="A")
    b = User.objects.create_user(email="b@e.com", name="B")
    g = make_group(a, b); lunch = pool(g, "Lunch")
    auth(api_client, a)
    eid = event(api_client, g, lunch)["id"]
    auth(api_client, b)  # member, not admin
    assert api_client.put(f"/api/haazri/{eid}/attendance/", {"entries": [{"user": str(b.id), "multiplier": 1}]}, format="json").status_code == 403


@pytest.mark.django_db
def test_duplicate_user_in_roster_rejected(api_client):
    a = User.objects.create_user(email="a@e.com", name="A")
    g = make_group(a); lunch = pool(g, "Lunch")
    auth(api_client, a)
    eid = event(api_client, g, lunch)["id"]
    r = api_client.put(f"/api/haazri/{eid}/attendance/", {"entries": [
        {"user": str(a.id), "multiplier": 1}, {"user": str(a.id), "multiplier": 2}]}, format="json")
    assert r.status_code == 400
