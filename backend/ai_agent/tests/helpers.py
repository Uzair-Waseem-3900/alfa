from django.contrib.auth import get_user_model

User = get_user_model()


def tool_ctx(context, tool_name="test_tool"):
    """What the SDK hands a tool at runtime (0.24 requires a ToolContext)."""
    from agents.tool_context import ToolContext
    return ToolContext(context=context, tool_name=tool_name, tool_call_id="call_1", tool_arguments="{}")


def make_admin(email="admin1@example.com"):
    return User.objects.create_user(email=email, password="x", first_name="Ad", last_name="Min", is_staff=True)


def make_superuser(email="root@example.com"):
    return User.objects.create_superuser(email=email, password="x", first_name="Su", last_name="Per")


def make_plain_user(email="plain@example.com"):
    return User.objects.create_user(email=email, password="x", first_name="Pl", last_name="Ain")
