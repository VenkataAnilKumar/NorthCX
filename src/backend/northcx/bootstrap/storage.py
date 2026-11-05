import os
from northcx.access import InMemoryKeys
from northcx.voice import InMemoryCalls
from northcx.attachments import InMemoryAttachments
from northcx.inbox import InMemoryInbox
from northcx.trace_export import InMemoryExports
from northcx.reviews import InMemoryReviews
from northcx.rollout import InMemoryRollouts
from northcx.simulation.managed import InMemoryScenarios
from northcx.insights import InMemoryTags, InMemoryFeedback
from northcx.audit import InMemoryAudit
from northcx.channels.sms import InMemorySmsRepo
from northcx.channels.email import InMemoryEmailRepo
from northcx.memory import InMemoryMemories
from northcx.knowledge import InMemoryKnowledge
from northcx.idempotency import InMemoryIdempotency
from northcx.monitor import InMemoryMonitor
from northcx.db import PgApprovalStore, PgAudit, PgEmailRepo, PgExports, PgFeedback, PgInsightsSource, PgAttachments, PgCalls, PgReviews, PgRollouts, PgScenarios, PgTags, PgHandoffs, PgIdempotency, PgInbox, PgKeys, PgKnowledge, PgMemories, PgMemoryStore, PgMonitor, PgPrivacy, PgOutbox, PgSmsRepo, PgReleases, PgSimRuns, PgTraceStore, PgVersions, create_engine, database_url_from_env, migrate
from northcx.secrets import env_or_file
from northcx.simulation import InMemorySimRuns
from northcx.store import InMemoryStore
from northcx.trace import TraceStore
from northcx.versions import InMemoryReleases, InMemoryVersions
from types import SimpleNamespace


def build_storage(c: SimpleNamespace) -> None:
    """Repositories: Postgres when a database URL is set, in memory otherwise."""
    engine = None
    db_url = database_url_from_env(env_or_file("NORTHCX_DATABASE_URL"))
    if db_url:
        migrate(db_url)  # apply pending migrations before serving
        engine = create_engine(db_url)
        store, traces, approvals = PgMemoryStore(engine), PgTraceStore(engine), PgApprovalStore(engine)
        outbox_repo, handoffs, sim_runs = PgOutbox(engine), PgHandoffs(engine), PgSimRuns(engine)
        versions_repo, releases_repo = PgVersions(engine), PgReleases(engine)
        keys_repo, audit_repo = PgKeys(engine), PgAudit(engine)
        email_repo = PgEmailRepo(engine)
        sms_repo = PgSmsRepo(engine)
        monitor_repo, idem_repo = PgMonitor(engine), PgIdempotency(engine)
        knowledge_repo = PgKnowledge(engine)
        privacy_backend = PgPrivacy(engine)
        export_repo = PgExports(engine)
        feedback_repo = PgFeedback(engine)
        tag_repo = PgTags(engine)
        review_repo = PgReviews(engine)
        rollout_repo = PgRollouts(engine)
        attachment_repo = PgAttachments(engine)
        call_repo = PgCalls(engine)
        scenario_repo = PgScenarios(engine)
        insights_source = PgInsightsSource(engine)
        inbox_repo = PgInbox(engine)
        memory_repo = PgMemories(engine)
        print("Using Postgres storage.")
    else:
        store, traces, approvals = InMemoryStore(), TraceStore(os.environ.get("NORTHCX_TRACE_DIR")), None
        outbox_repo, handoffs, sim_runs = None, None, InMemorySimRuns()
        versions_repo, releases_repo = InMemoryVersions(), InMemoryReleases()
        keys_repo, audit_repo = InMemoryKeys(), InMemoryAudit()
        email_repo = InMemoryEmailRepo()
        sms_repo = InMemorySmsRepo()
        monitor_repo, idem_repo = InMemoryMonitor(), InMemoryIdempotency()
        knowledge_repo = InMemoryKnowledge()
        privacy_backend = None  # the runtime builds the in-memory one
        export_repo = InMemoryExports()
        feedback_repo = InMemoryFeedback()
        tag_repo = InMemoryTags()
        review_repo = InMemoryReviews()
        rollout_repo = InMemoryRollouts()
        attachment_repo = InMemoryAttachments()
        call_repo = InMemoryCalls()
        scenario_repo = InMemoryScenarios()
        insights_source = None  # built over the runtime below
        inbox_repo = InMemoryInbox()
        memory_repo = InMemoryMemories()
        print("Using in-memory storage: state is lost on restart. Set NORTHCX_DATABASE_URL for Postgres.")
    c.approvals = approvals
    c.attachment_repo = attachment_repo
    c.audit_repo = audit_repo
    c.call_repo = call_repo
    c.db_url = db_url
    c.email_repo = email_repo
    c.engine = engine
    c.export_repo = export_repo
    c.feedback_repo = feedback_repo
    c.handoffs = handoffs
    c.idem_repo = idem_repo
    c.inbox_repo = inbox_repo
    c.insights_source = insights_source
    c.keys_repo = keys_repo
    c.knowledge_repo = knowledge_repo
    c.memory_repo = memory_repo
    c.monitor_repo = monitor_repo
    c.outbox_repo = outbox_repo
    c.privacy_backend = privacy_backend
    c.releases_repo = releases_repo
    c.review_repo = review_repo
    c.rollout_repo = rollout_repo
    c.scenario_repo = scenario_repo
    c.sim_runs = sim_runs
    c.sms_repo = sms_repo
    c.store = store
    c.tag_repo = tag_repo
    c.traces = traces
    c.versions_repo = versions_repo
