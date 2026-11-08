import os
import sys
from northcx.crawler import Crawler, hosts_from as crawl_hosts_from
from northcx.voice import VoiceConfig
from northcx.attachments import HttpScanner
from northcx.residency import ResidencyError, build_report, parse_policy
from northcx.crawl_schedule import CrawlScheduler, InMemorySchedules
from northcx.transcribe import HttpTranscriber
from northcx.embeddings import EmbeddingIndexer, HttpEmbedder, HybridKnowledge, parse_source_models
from northcx.db import PgSchedules, PgCrawlJobs
from northcx.secrets import env_or_file
from types import SimpleNamespace


def build_optional(c: SimpleNamespace) -> None:
    """Optional services: embeddings, transcription, crawling, voice, scanning, residency."""
    db_url = c.db_url
    engine = c.engine
    knowledge_repo = c.knowledge_repo
    if os.environ.get("NORTHCX_EMBEDDINGS_URL"):
        try:
            embedder = HttpEmbedder(os.environ["NORTHCX_EMBEDDINGS_URL"], os.environ.get("NORTHCX_EMBEDDINGS_MODEL", ""), os.environ.get("NORTHCX_EMBEDDINGS_API_KEY") or None,
                                    int(os.environ["NORTHCX_EMBEDDINGS_DIMENSIONS"]) if os.environ.get("NORTHCX_EMBEDDINGS_DIMENSIONS") else None)
        except ValueError as e:
            sys.exit(str(e))
        try:
            src_models = parse_source_models(os.environ.get("NORTHCX_EMBEDDINGS_SOURCE_MODELS", ""))
            knowledge_repo = HybridKnowledge(knowledge_repo, embedder, source_models=src_models)
        except ValueError as e:
            sys.exit(str(e))
        knowledge_repo.indexer = EmbeddingIndexer(knowledge_repo.store, embedder, source_models=src_models)
        if hasattr(knowledge_repo.store, "ann_threshold") and os.environ.get("NORTHCX_ANN_THRESHOLD"):
            knowledge_repo.store.ann_threshold = int(os.environ["NORTHCX_ANN_THRESHOLD"])
        print(f"Meaning-based knowledge search is ON (model {embedder.model}); passages are sent to the embeddings endpoint you configured.")
    transcriber = None
    if os.environ.get("NORTHCX_TRANSCRIBE_URL"):
        try:
            transcriber = HttpTranscriber(os.environ["NORTHCX_TRANSCRIBE_URL"], os.environ.get("NORTHCX_TRANSCRIBE_MODEL", ""), env_or_file("NORTHCX_TRANSCRIBE_API_KEY") or None)
        except ValueError as e:
            sys.exit(str(e))
        print("Recording transcription is ON; uploaded recordings are sent to the transcription service you configured.")
    crawler = crawl_scheduler = None
    if os.environ.get("NORTHCX_CRAWL_HOSTS"):
        try:
            crawler = Crawler(knowledge_repo, crawl_hosts_from(os.environ["NORTHCX_CRAWL_HOSTS"]), os.environ.get("NORTHCX_CRAWL_ALLOW_PRIVATE") == "1",
                                jobs_repo=PgCrawlJobs(engine) if db_url else None)
        except ValueError as e:
            sys.exit(str(e))
        print(f"Knowledge crawling is ON for: {', '.join(sorted(crawler.allowed))}.")
        schedule_repo = PgSchedules(engine) if db_url else InMemorySchedules()
        crawl_scheduler = CrawlScheduler(crawler, schedule_repo)
    voice_cfg = None
    if os.environ.get("NORTHCX_VOICE_AGENT"):
        try:
            transfers = dict(p.split("=", 1) for p in os.environ.get("NORTHCX_VOICE_TRANSFER", "").replace(" ", "").split(",") if p)
            voice_cfg = VoiceConfig(os.environ["NORTHCX_VOICE_AGENT"], os.environ.get("NORTHCX_VOICE_BRAND") or "our support line", os.environ.get("NORTHCX_VOICE_LANGUAGE") or "en",
                                    os.environ.get("NORTHCX_VOICE_RECORDING") or "off", transfers, os.environ.get("NORTHCX_VOICE_TRUST_CALLER_ID") == "1")
        except ValueError as e:
            sys.exit(f"Voice: {e}")
        print(f"Voice calls are ON for agent '{voice_cfg.agent_id}' (recording: {voice_cfg.recording}).")
    attachment_scanner = None
    if os.environ.get("NORTHCX_ATTACHMENT_SCAN_URL"):
        try:
            attachment_scanner = HttpScanner(os.environ["NORTHCX_ATTACHMENT_SCAN_URL"])
        except ValueError as e:
            sys.exit(str(e))

    residency_policy = None
    if os.environ.get("NORTHCX_RESIDENCY_FILE"):
        try:
            residency_policy = parse_policy(open(os.environ["NORTHCX_RESIDENCY_FILE"], encoding="utf-8").read())
        except (OSError, ResidencyError) as e:
            sys.exit(f"Residency: {e}")
    residency = build_report(os.environ, residency_policy)
    if residency_policy is not None:
        for p_ in residency["problems"]:
            print(f"Residency {'ERROR' if residency_policy.strict else 'warning'}: {p_}")
        if residency["problems"] and residency_policy.strict:
            sys.exit("Residency is strict and some destinations are not in an allowed region; fix the residency file or the configuration above.")
        print(f"Data residency: deployment region '{residency_policy.region}', data may go to: {', '.join(residency_policy.allowed)}.")
    c.attachment_scanner = attachment_scanner
    c.crawl_scheduler = crawl_scheduler
    c.crawler = crawler
    c.knowledge_repo = knowledge_repo
    c.residency = residency
    c.transcriber = transcriber
    c.voice_cfg = voice_cfg
