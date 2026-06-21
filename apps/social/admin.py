from django.contrib import admin
from .models import Friendship, Group, GroupMembership

admin.site.register(Friendship)
admin.site.register(Group)
admin.site.register(GroupMembership)
