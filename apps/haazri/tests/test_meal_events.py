import pytest
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import RefreshToken
from apps.social.models import Group, GroupMembership
from apps.ledger.models import Category

User = get_user_model()
def auth(c,u): c.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(u).access_token}")
def make_group(owner,*m):
    g=Group.objects.create(name="H",owner=owner); GroupMembership.objects.create(group=g,user=owner,role="owner",status="active")
    for x in m: GroupMembership.objects.create(group=g,user=x,role="member",status="active")
    return g
def pool(g,name): return Category.objects.create(group=g,ledger_type="kitchen_pool",name=name)

@pytest.mark.django_db
def test_admin_creates_meal_event(api_client):
    a=User.objects.create_user(email="a@e.com",name="A"); g=make_group(a); lunch=pool(g,"Lunch")
    auth(api_client,a)
    r=api_client.post(f"/api/groups/{g.id}/haazri/",{"category":str(lunch.id),"date":"2026-06-05"},format="json")
    assert r.status_code in (200,201)
    day=api_client.get(f"/api/groups/{g.id}/haazri/?date=2026-06-05").json()
    assert len(day)==1 and day[0]["category"]==str(lunch.id)

@pytest.mark.django_db
def test_member_cannot_create_event(api_client):
    a=User.objects.create_user(email="a@e.com",name="A"); b=User.objects.create_user(email="b@e.com",name="B")
    g=make_group(a,b); lunch=pool(g,"Lunch"); auth(api_client,b)
    assert api_client.post(f"/api/groups/{g.id}/haazri/",{"category":str(lunch.id),"date":"2026-06-05"},format="json").status_code==403
