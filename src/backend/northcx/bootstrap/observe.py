import os
import sys
from northcx.db import PgAlertState
from northcx.alerts import AlertConfigError, AlertManager, WebhookAlerts, load_rules
from northcx.insights import InMemoryInsightsSource, InsightsService
from northcx.regression import RegressionRunner
from northcx.secrets import env_or_file
from types import SimpleNamespace


def _window_days() -> float:
    raw = os.environ.get("NORTHCX_RESOLUTION_WINDOW_DAYS", "").strip()
    try:
        days = float(raw) if raw else 3.0
    except ValueError:
        sys.exit("NORTHCX_RESOLUTION_WINDOW_DAYS must be a number of days between 0.5 and 30")
    if not 0.5 <= days <= 30:
        sys.exit("NORTHCX_RESOLUTION_WINDOW_DAYS must be a number of days between 0.5 and 30")
    return days


def build_observability(c: SimpleNamespace) -> None:
    """Regression reruns, insights and alerts."""
    demo = c.demo
    feedback_repo = c.feedback_repo
    insights_source = c.insights_source
    monitor_repo = c.monitor_repo
    runtime = c.runtime
    simulations = c.simulations
    regression = None
    rerun = os.environ.get("NORTHCX_RERUN_ON_KNOWLEDGE", "off")
    if rerun != "off":
        if rerun not in ("scripted", "live") or simulations is None:
            sys.exit("NORTHCX_RERUN_ON_KNOWLEDGE must be off, scripted or live, and needs scenarios (NORTHCX_SCENARIOS_DIR)")
        if rerun == "live" and demo:
            sys.exit("NORTHCX_RERUN_ON_KNOWLEDGE=live needs a real model (not the demo)")
        regression = RegressionRunner(simulations, monitor_repo, rerun, debounce=float(os.environ.get("NORTHCX_RERUN_DEBOUNCE_SECONDS", 60)))
    insights_service = InsightsService(insights_source or InMemoryInsightsSource(runtime, feedback_repo),
                                       float(os.environ["NORTHCX_PRICE_PER_MILLION_TOKENS"]) if os.environ.get("NORTHCX_PRICE_PER_MILLION_TOKENS") else None,
                                       resolution_window_days=_window_days())
    alert_manager = None
    if os.environ.get("NORTHCX_ALERTS", "on") != "off":
        try:
            alert_hook = None
            if os.environ.get("NORTHCX_ALERT_WEBHOOK_URL"):
                alert_hook = WebhookAlerts(os.environ["NORTHCX_ALERT_WEBHOOK_URL"], env_or_file("NORTHCX_ALERT_WEBHOOK_SECRET") or "")
            alert_manager = AlertManager(insights_service, monitor_repo, load_rules(os.environ["NORTHCX_ALERT_RULES"]) if os.environ.get("NORTHCX_ALERT_RULES") else None, alert_hook,
                                         state=PgAlertState(c.engine) if c.db_url else None)
        except (AlertConfigError, ValueError) as e:
            sys.exit(f"Configuration error: {e}")
    c.alert_manager = alert_manager
    c.insights_service = insights_service
    c.regression = regression
