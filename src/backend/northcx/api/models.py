"""Request bodies for the HTTP API (moved out of server.py; behaviour unchanged)."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from northcx.tokens import DEFAULT_TTL


class ChatBody(BaseModel):
    session_id: str = Field(alias="sessionId", min_length=1, max_length=200)
    message: str = Field(min_length=1, max_length=8000)
    customer_id: str | None = Field(default=None, alias="customerId", max_length=200)
    channel: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_-]{1,19}$")
    environment: str | None = Field(default=None, pattern=r"^(dev|staging|production)$")  # internal keys only; customers always get production
    attachments: list[str] = Field(default_factory=list, max_length=5)  # ids returned by the attachment upload
    model_config = {"populate_by_name": True}


class SourceBody(BaseModel):
    id: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=200)
    stale_after_days: int | None = Field(default=None, alias="staleAfterDays")
    model_config = {"populate_by_name": True}


class DocumentBody(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    text: str = Field(min_length=1, max_length=500_000)
    url: str | None = Field(default=None, max_length=2000)
    source_updated_at: float | None = Field(default=None, alias="sourceUpdatedAt")
    model_config = {"populate_by_name": True}


class RetentionBody(BaseModel):
    older_than_days: float = Field(alias="olderThanDays", ge=1, le=3650)
    model_config = {"populate_by_name": True}


class RolloutBody(BaseModel):
    version: int
    percent: int
    environment: str = "production"
    by: str | None = Field(default=None, max_length=200)
    note: str | None = Field(default=None, max_length=1000)


class CrawlBody(BaseModel):
    url: str = Field(min_length=8, max_length=500)
    max_pages: int = Field(default=50, alias="maxPages")
    max_depth: int = Field(default=2, alias="maxDepth")
    delay_seconds: float = Field(default=1.0, alias="delaySeconds")
    include_paths: list[str] = Field(default_factory=list, alias="includePaths")
    exclude_paths: list[str] = Field(default_factory=list, alias="excludePaths")
    use_sitemap: bool = Field(default=True, alias="useSitemap")
    prune: bool = False
    model_config = {"populate_by_name": True}


class ScheduleBody(CrawlBody):
    every_hours: float = Field(alias="everyHours")


class TemplateSendBody(BaseModel):
    phone_id: str | None = Field(default=None, alias="phoneId", max_length=20)
    to: str = Field(min_length=8, max_length=16)
    template: str = Field(min_length=1, max_length=100, pattern=r"^[a-z0-9_]+$")
    params: list[str] = Field(default_factory=list, max_length=10)
    model_config = {"populate_by_name": True}


class EventTestBody(BaseModel):
    type: str = Field(max_length=60)


class ConnectionBody(BaseModel):
    name: str = Field(max_length=24)
    url: str = Field(max_length=500)
    secret: str | None = Field(default=None, max_length=40)
    trusted: bool = False


class ConnectionUpdateBody(BaseModel):
    trusted: bool | None = None
    enabled: bool | None = None
    secret: str | None = Field(default=None, max_length=40)  # a new credential name; send `clearSecret` to remove it
    clear_secret: bool = Field(default=False, alias="clearSecret")
    model_config = {"populate_by_name": True}


class ApproveBody(BaseModel):
    tools: dict[str, str] = Field(max_length=200)  # tool name to the fingerprint the operator saw in the review


class EnabledBody(BaseModel):
    enabled: bool


class BuilderSource(BaseModel):
    kind: str
    name: str = Field(default="", max_length=80)
    text: str = Field(min_length=1, max_length=20000)


class ScenarioDraftBody(BaseModel):
    spec: str = Field(min_length=10, max_length=60000)
    examples: list[str] = Field(default_factory=list, max_length=8)


class RefineBody(BaseModel):
    current: str = Field(min_length=10, max_length=60000)
    instruction: str = Field(min_length=5, max_length=1000)


class BuilderBody(BaseModel):
    agent_id: str = Field(alias="agentId", min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_.-]+$")
    goal: str = Field(min_length=10, max_length=2000)
    sources: list[BuilderSource] = Field(min_length=1, max_length=8)
    model_config = {"populate_by_name": True}


class AskBody(BaseModel):
    question: str = Field(min_length=3, max_length=500)
    environment: str = "production"


class JourneyDraftBody(BaseModel):
    description: str = Field(min_length=10, max_length=3000)


class JourneyScenariosBody(BaseModel):
    journey: dict[str, Any]


class PercentBody(BaseModel):
    percent: int


class PromoteBody(BaseModel):
    to: str
    by: str | None = Field(default=None, max_length=200)
    note: str | None = Field(default=None, max_length=1000)


class TemplateBody(BaseModel):
    agent_id: str = Field(alias="agentId", min_length=2, max_length=40)
    params: dict[str, Any] = Field(default_factory=dict)
    save_scenarios: bool = Field(default=False, alias="saveScenarios")
    by: str | None = Field(default=None, max_length=200)
    note: str | None = Field(default=None, max_length=1000)
    model_config = {"populate_by_name": True}


class FeedbackBody(BaseModel):
    rating: int = Field(ge=1, le=5)
    comment: str = Field(default="", max_length=1000)


class ScenarioBody(BaseModel):
    yaml: str | None = Field(default=None, max_length=100_000)
    scenario: dict[str, Any] | None = None


class ReviewBody(BaseModel):
    verdict: str
    handoff: str = "not_applicable"
    failures: list[str] = Field(default_factory=list, max_length=9)
    note: str = Field(default="", max_length=1000)


class DecisionBody(BaseModel):
    approved: bool
    by: str | None = Field(default=None, max_length=200)  # only used when the server has no authentication configured
    note: str | None = Field(default=None, max_length=1000)


class ResolveBody(BaseModel):
    by: str | None = Field(default=None, max_length=200)
    note: str | None = Field(default=None, max_length=1000)
    returnToAgent: bool = True  # the agent carries on with the customer, told what the person did


class ReplyBody(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    by: str | None = Field(default=None, max_length=200)


class QualifyBody(BaseModel):
    model: str = Field(min_length=1, max_length=300)
    run_id: str = Field(alias="runId", min_length=1, max_length=64)
    model_config = {"populate_by_name": True}


class SimRunBody(BaseModel):
    mode: str = "scripted"
    only: str | None = Field(default=None, max_length=100)
    skip_judge: bool = Field(default=False, alias="skipJudge")
    agent: str | None = None
    version: int | None = Field(default=None, ge=1)  # run against this saved version of `agent`
    model: str | None = Field(default=None, max_length=300)  # with `version` and live mode: run the agent on this candidate model (for qualification)
    model_config = {"populate_by_name": True}


class VersionBody(BaseModel):
    spec: dict[str, Any] | None = None
    spec_yaml: str | None = Field(default=None, alias="specYaml", max_length=100_000)
    from_baseline: bool = Field(default=False, alias="fromBaseline")
    by: str | None = Field(default=None, max_length=200)
    note: str | None = Field(default=None, max_length=1000)
    model_config = {"populate_by_name": True}


class PublishBody(BaseModel):
    version: int = Field(ge=1)
    environment: str = "production"
    by: str | None = Field(default=None, max_length=200)
    note: str | None = Field(default=None, max_length=1000)


class RequestDecisionBody(BaseModel):
    note: str | None = Field(default=None, max_length=1000)


class RollbackBody(BaseModel):
    environment: str = "production"
    to_version: int | None = Field(default=None, alias="toVersion", ge=1)
    by: str | None = Field(default=None, max_length=200)
    note: str | None = Field(default=None, max_length=1000)
    model_config = {"populate_by_name": True}


class TokenBody(BaseModel):
    session_id: str | None = Field(default=None, alias="sessionId", pattern=r"^[A-Za-z0-9_.:-]{1,200}$")
    customer_id: str | None = Field(default=None, alias="customerId", max_length=200)
    agent: str | None = Field(default=None, max_length=200)
    ttl_seconds: float = Field(default=DEFAULT_TTL, alias="ttlSeconds")
    model_config = {"populate_by_name": True}


class GroupBody(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    roles: list[str] = Field(default_factory=list, max_length=6)
    external_name: str | None = Field(default=None, alias="externalName", max_length=200)  # the identity provider's name for this group
    description: str = Field(default="", max_length=500)
    model_config = {"populate_by_name": True}


class GroupUpdateBody(BaseModel):
    roles: list[str] | None = Field(default=None, max_length=6)
    external_name: str | None = Field(default=None, alias="externalName", max_length=200)  # "" clears the mapping
    description: str | None = Field(default=None, max_length=500)
    model_config = {"populate_by_name": True}


class MemberBody(BaseModel):
    subject: str = Field(min_length=1, max_length=200)  # an email address or identity provider id


class WorkspaceChatBody(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    space_id: str | None = Field(default=None, alias="spaceId", max_length=20)     # work inside a space: its instructions apply
    chat_id: str | None = Field(default=None, alias="chatId", pattern=r"^[A-Za-z0-9_-]{1,64}$")  # leave out to start a new chat
    style: str = Field(default="quick", pattern="^(quick|research|think|do)$")
    memory: bool = True        # false: this chat neither reads nor writes the person's memory
    temporary: bool = False    # true: nothing is kept (history, traces) and no memory is used
    model_config = {"populate_by_name": True}


class TaskBody(BaseModel):
    prompt: str = Field(min_length=1, max_length=4000)
    style: str = Field(default="research", pattern="^(research)$")


class AnswersBody(BaseModel):
    answers: list[str] = Field(default_factory=list, max_length=3)


class PlanBody(BaseModel):
    steps: list[dict[str, Any]] = Field(min_length=1, max_length=8)


class NoteBody(BaseModel):
    note: str = Field(min_length=5, max_length=300)


class HubBody(BaseModel):
    agent_id: str = Field(alias="agentId", min_length=2, max_length=40)
    params: dict[str, Any] = Field(default_factory=dict)
    by: str | None = Field(default=None, max_length=200)
    note: str | None = Field(default=None, max_length=1000)
    model_config = {"populate_by_name": True}


class OrgPolicyProveBody(BaseModel):
    policy: str = Field(min_length=1, max_length=60)
    config: dict[str, Any] = Field(default_factory=dict)
    cases: list[dict[str, Any]] = Field(default_factory=list, max_length=50)


class OrgPolicyBody(OrgPolicyProveBody):
    name: str = Field(min_length=3, max_length=80)
    applies_to: list[str] | None = Field(default=None, alias="appliesTo", max_length=100)  # leave out for every customer agent
    model_config = {"populate_by_name": True}


class OrgPolicyEditBody(BaseModel):
    config: dict[str, Any] | None = None
    cases: list[dict[str, Any]] | None = Field(default=None, max_length=50)
    applies_to: list[str] | None = Field(default=None, alias="appliesTo", max_length=100)
    model_config = {"populate_by_name": True}


class OrgPolicyDecisionBody(BaseModel):
    note: str | None = Field(default=None, max_length=1000)


class OrgTemplateBody(BaseModel):
    yaml: str | None = Field(default=None, max_length=60000)
    template: dict[str, Any] | None = None             # the same document as a JSON object


class RubricBody(BaseModel):
    criteria: list[dict[str, Any]] = Field(min_length=1, max_length=20)
    pass_mark: float = Field(default=70, alias="passMark", ge=1, le=100)
    sample: float = Field(default=0.1, ge=0, le=1)
    model_config = {"populate_by_name": True}


class CoachingBody(BaseModel):
    session_id: str = Field(alias="sessionId", min_length=1, max_length=200)
    about: str = Field(min_length=2, max_length=80)
    note: str = Field(min_length=5, max_length=300)
    model_config = {"populate_by_name": True}


class CustomerLookupBody(BaseModel):
    customer_id: str | None = Field(default=None, alias="customerId", min_length=1, max_length=200)
    session_id: str | None = Field(default=None, alias="sessionId", min_length=1, max_length=200)    # "the customer of this conversation", for results found without the identifier
    model_config = {"populate_by_name": True}


class CustomerFindBody(BaseModel):
    order_number: str = Field(alias="orderNumber", min_length=3, max_length=40, pattern=r"^[A-Za-z0-9#][A-Za-z0-9#_\-./]{1,38}[A-Za-z0-9]$")
    model_config = {"populate_by_name": True}


class CustomerRevealBody(CustomerLookupBody):
    reason: str = Field(min_length=10, max_length=300)


class CustomerRemoveBody(CustomerLookupBody):
    reason: str = Field(min_length=5, max_length=300)


class CustomerNoteBody(CustomerLookupBody):
    note: str = Field(min_length=5, max_length=300)


class CustomerSettingsBody(BaseModel):
    enabled: bool


class AutomationBody(BaseModel):
    yaml: str | None = Field(default=None, max_length=30000)
    definition: dict[str, Any] | None = None


class AutomationRunBody(BaseModel):
    input: str = Field(default="", max_length=2000)


class AutomationDraftBody(BaseModel):
    description: str = Field(min_length=10, max_length=1500)


class AutomationDecisionBody(BaseModel):
    approve: bool
    note: str | None = Field(default=None, max_length=300)


class AutomationSettingsBody(BaseModel):
    enabled: bool


class OutputBody(BaseModel):
    title: str = Field(min_length=2, max_length=120)
    body: str = Field(min_length=1, max_length=100000)
    kind: str = "note"
    visibility: str = "private"
    space_id: str | None = Field(default=None, alias="spaceId", max_length=20)
    source: str = Field(default="manual", pattern="^(manual|pilot)$")           # a person can say where it came from, but not pretend to be a routine
    days: int = Field(default=90, ge=1, le=365)
    model_config = {"populate_by_name": True}


class OutputEditBody(BaseModel):
    title: str | None = Field(default=None, max_length=120)
    body: str | None = Field(default=None, max_length=100000)
    visibility: str | None = None


class SpaceBody(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    description: str = Field(default="", max_length=500)
    instructions: str = Field(default="", max_length=2000)
    visibility: str = "private"


class SpaceFileBody(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    text: str | None = Field(default=None, max_length=200000)
    data_base64: str | None = Field(default=None, alias="dataBase64", max_length=7_500_000)      # for a PDF: the file itself, read here for its text
    model_config = {"populate_by_name": True}


class SpaceEditBody(BaseModel):
    name: str | None = Field(default=None, max_length=80)
    description: str | None = Field(default=None, max_length=500)
    instructions: str | None = Field(default=None, max_length=2000)
    visibility: str | None = None


class JudgeBody(BaseModel):
    session_id: str = Field(alias="sessionId", min_length=1, max_length=200)
    model_config = {"populate_by_name": True}


class LibraryItemBody(BaseModel):
    title: str = Field(min_length=2, max_length=120)
    body: str = Field(min_length=1, max_length=20000)
    kind: str = "macro"
    visibility: str = "private"
    tags: list[str] = Field(default_factory=list, max_length=8)


class LibraryEditBody(BaseModel):
    title: str | None = Field(default=None, max_length=120)
    body: str | None = Field(default=None, max_length=20000)
    visibility: str | None = None
    tags: list[str] | None = Field(default=None, max_length=8)


class LibrarySuggestBody(BaseModel):
    text: str = Field(min_length=2, max_length=4000)
    limit: int = Field(default=5, ge=1, le=10)


class ImproveBody(BaseModel):
    days: int = Field(default=14, ge=1, le=90)
    focus: str | None = Field(default=None, max_length=300)
    create_draft: bool = Field(default=False, alias="createDraft")
    model_config = {"populate_by_name": True}


class KeyBody(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    role: str
    expires_in_days: float | None = Field(default=None, alias="expiresInDays")
    agents: list[str] | None = None  # limit the key to these agents (leave out for all)
    environments: list[str] | None = None  # limit the key to these environments (leave out for all)
    model_config = {"populate_by_name": True}


class ExpireBody(BaseModel):
    older_than_seconds: float = Field(alias="olderThanSeconds", ge=0)
    model_config = {"populate_by_name": True}
