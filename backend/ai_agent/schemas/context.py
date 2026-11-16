from dataclasses import dataclass, field

from django.contrib.auth import get_user_model

User = get_user_model()


@dataclass
class LookupLog:
    """The customer/product ids the find_* tools returned DURING THIS RUN. A write may only use an id
    from here: a model that skips the lookup invents an integer, and that integer is a real,
    different customer (seen live: a draft for AZEEM STATIONERS went to MIAN FLOWER DECORATION).
    Tool threads only ever add to these sets."""
    customers: set[int] = field(default_factory=set)
    products: set[int] = field(default_factory=set)


@dataclass
class BulkOutcome:
    """What the bulk agent reported through its two "stop" tools. The row's status is decided in code from
    this and from the AgentAction rows (never from the model's wording)."""
    question: str = ""
    options: list[str] = field(default_factory=list)
    not_invoice: str = ""


@dataclass(frozen=True)
class AgentContext:
    """Passed to the Runner as `context=`; every tool reads the asking user
    from here (never from globals) so each tool runs AS that user."""
    user: "User"
    run_id: str | None = None    # the ChatRun answering this message (audit + idempotency key)
    chat_id: str | None = None
    source: str = "chat"         # "chat" | "bulk": which write budget applies
    link_name_id: int | None = None   # bulk only: customer search is limited to this sales-man link name
    lookups: LookupLog = field(default_factory=LookupLog)
    outcome: BulkOutcome = field(default_factory=BulkOutcome)

    @property
    def name(self) -> str:
        return f"{self.user.first_name} {self.user.last_name}".strip() or self.user.email

    @property
    def role(self) -> str:
        return self.user.role
