from dataclasses import dataclass

from django.contrib.auth import get_user_model

User = get_user_model()


@dataclass(frozen=True)
class AgentContext:
    """Passed to the Runner as `context=`; every tool reads the asking user
    from here (never from globals) so each tool runs AS that user."""
    user: "User"

    @property
    def name(self) -> str:
        return f"{self.user.first_name} {self.user.last_name}".strip() or self.user.email

    @property
    def role(self) -> str:
        return self.user.role
