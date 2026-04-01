"""tobira.monitoring - prediction metrics logging and drift detection."""

__all__ = [
    "DeploymentPhase",
    "EmailNotifier",
    "JsonlStore",
    "MetricsConfig",
    "MetricsInstruments",
    "MetricsMiddleware",
    "NotificationConfig",
    "NotificationDispatcher",
    "PhaseAdvice",
    "PhaseTransitionConfig",
    "PostgresStore",
    "PredictionCollector",
    "RedisRecordStore",
    "RedisScoreStore",
    "RetrainConfig",
    "RetrainEvent",
    "SlackNotifier",
    "StoreProtocol",
    "TeamsNotifier",
    "analyze",
    "analyze_drift_from_redis",
    "append_record",
    "check_retrain_needed",
    "create_dispatcher",
    "create_metrics_endpoint",
    "create_store",
    "detect_drift",
    "load_notification_config",
    "load_retrain_config",
    "notify_analysis_results",
    "read_records",
    "setup_metrics",
    "trigger_retrain",
]


def __getattr__(name: str):  # type: ignore[no-untyped-def]
    if name == "PredictionCollector":
        from tobira.monitoring.collector import PredictionCollector

        return PredictionCollector
    if name in ("DeploymentPhase", "PhaseAdvice", "PhaseTransitionConfig"):
        from tobira.monitoring import analyzer

        return getattr(analyzer, name)
    if name == "analyze":
        from tobira.monitoring.analyzer import analyze

        return analyze
    if name == "analyze_drift_from_redis":
        from tobira.monitoring.analyzer import analyze_drift_from_redis

        return analyze_drift_from_redis
    if name == "detect_drift":
        from tobira.monitoring.drift import detect_drift

        return detect_drift
    if name in ("append_record", "read_records"):
        from tobira.monitoring import store

        return getattr(store, name)
    if name in ("RedisScoreStore", "JsonlStore", "PostgresStore",
                "RedisRecordStore", "StoreProtocol", "create_store"):
        from tobira.monitoring import store

        return getattr(store, name)
    if name in ("RetrainConfig", "RetrainEvent", "check_retrain_needed",
                "load_retrain_config", "trigger_retrain"):
        from tobira.monitoring import retrain

        return getattr(retrain, name)
    if name in ("NotificationConfig", "NotificationDispatcher",
                "create_dispatcher", "load_notification_config"):
        from tobira.monitoring import notifier

        return getattr(notifier, name)
    if name == "SlackNotifier":
        from tobira.monitoring.slack import SlackNotifier

        return SlackNotifier
    if name == "TeamsNotifier":
        from tobira.monitoring.teams import TeamsNotifier

        return TeamsNotifier
    if name == "EmailNotifier":
        from tobira.monitoring.email_notifier import EmailNotifier

        return EmailNotifier
    if name == "notify_analysis_results":
        from tobira.monitoring.analyzer import notify_analysis_results

        return notify_analysis_results
    if name in ("MetricsConfig", "MetricsInstruments", "MetricsMiddleware",
                "create_metrics_endpoint", "setup_metrics"):
        from tobira.monitoring import metrics

        return getattr(metrics, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
