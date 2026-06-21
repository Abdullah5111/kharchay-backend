from .models import GroupMembership


def group_role(user, group):
    m = GroupMembership.objects.filter(group=group, user=user, status=GroupMembership.ACTIVE).first()
    return m.role if m else None


def is_member(user, group):
    return group_role(user, group) is not None


def is_group_admin(user, group):
    return group_role(user, group) in (GroupMembership.OWNER, GroupMembership.ADMIN)


def is_owner(user, group):
    return group_role(user, group) == GroupMembership.OWNER
