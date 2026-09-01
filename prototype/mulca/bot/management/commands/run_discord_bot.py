"""Boots the text-only MULCA prototype (BLUEPRINT.md's second deliverable).

Wires config -> StrategyStore -> RealtimeInterventionLLM/MainLLM -> Orchestrator
-> TextChannelAdapter, exactly matching the components named in BLUEPRINT.md
§1-§3, §10.1. No audio here -- see prototype/README.md for the seam.

Runs in-process by default. Pass --autoreload to opt into Django's autoreload
utility (the same mechanism `runserver` uses) for auto-restart-on-code-change
during active debugging -- confirmed live that this prevents clean-shutdown
persistence (BLUEPRINT.md §11.1) from firing reliably on Windows (Ctrl+C
appears to kill the child subprocess it spawns before run_bot()'s own
shutdown code runs), so it's opt-in rather than the default.
"""
import asyncio
import os
from pathlib import Path

import yaml
from django.core.management.base import BaseCommand
from django.utils import autoreload
from dotenv import load_dotenv
from openai import AsyncOpenAI

from mulca.core.main_llm import MainLLM
from mulca.core.orchestrator import Orchestrator
from mulca.core.realtime_intervention import RealtimeInterventionLLM
from mulca.core.strategies import StrategyStore

from ... import experience_memory
from ...discord_adapter import build_discord_client, load_wm_snapshot, save_wm_snapshot

CONFIG_DIR = Path(__file__).resolve().parents[3] / "config"

# Three independent choices made at startup (BLUEPRINT.md §9's reuse goal --
# assemble an instance by selecting from a shared pool, not by one config
# auto-deriving another): which task/context is active, which persona files
# to use, and which strategies (from the full pool in config/strategies/) are
# switched on. Nothing here implies the others -- e.g. "keep_conversation_on_topic"
# only makes sense alongside consensus_ranking, but that's a choice you make
# by listing it here, not something the task forces automatically.
TASK_ID = "general_moderation"
ACTIVE_STRATEGY_IDS = ["participation_equality", "respond_when_addressed", "non_offensive", "provide_summary"]


def load_persona_config() -> dict:
    intervention = yaml.safe_load((CONFIG_DIR / "personas" / "intervention_default.yaml").read_text())
    main = yaml.safe_load((CONFIG_DIR / "personas" / "main_default.yaml").read_text())
    return {"intervention": intervention["persona"], "main": main["persona"]}


def load_task_config() -> dict:
    return yaml.safe_load((CONFIG_DIR / "tasks" / f"{TASK_ID}.yaml").read_text())


def load_strategy_store() -> StrategyStore:
    return StrategyStore.load_from_dir(str(CONFIG_DIR / "strategies"), active_ids=ACTIVE_STRATEGY_IDS)


def run_bot() -> None:
    load_dotenv()
    discord_token = os.environ["DISCORD_BOT_TOKEN"]
    channel_ids_raw = os.environ.get("MULCA_CHANNEL_IDS", "").strip()
    channel_ids = {c.strip() for c in channel_ids_raw.split(",") if c.strip()} or None
    # BLUEPRINT.md §11.1: persistence needs one stable identity to key a
    # snapshot by. With no MULCA_CHANNEL_IDS configured there's no single
    # "the group's channel" to persist against, so persistence is disabled
    # rather than guessing (Orchestrator checks for None and no-ops).
    persistence_channel_id = sorted(channel_ids)[0] if channel_ids else None

    strategy_store = load_strategy_store()
    openai_client = AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])
    main_llm = MainLLM(openai_client, strategy_store)
    persona_config = load_persona_config()
    task_config = load_task_config()

    def intervention_llm_factory(scope_key: str, restored_history_summary: str = "", restored_participant_roles_summary: str = ""):
        # BLUEPRINT.md §10.1 / "Channel/instance scoping": one persistent
        # session per scope ("group", or "dm:<user_id>") -- connect() is
        # called lazily by the orchestrator on first use for that scope.
        return RealtimeInterventionLLM(
            openai_client,
            strategy_store,
            persona=persona_config["intervention"],
            task_knowledge=task_config["description"],
            is_dm=scope_key.startswith("dm:"),
            restored_history_summary=restored_history_summary,
            restored_participant_roles_summary=restored_participant_roles_summary,
        )

    def orchestrator_factory(bot_user_id: str, dispatch_fn, roster_fn, bot_display_name: str):
        return Orchestrator(
            strategy_store=strategy_store,
            intervention_llm_factory=intervention_llm_factory,
            main_llm=main_llm,
            bot_user_id=bot_user_id,
            dispatch_fn=dispatch_fn,
            log_fn=experience_memory.log,
            persona_config=persona_config,
            task_config=task_config,
            roster_fn=roster_fn,
            bot_display_name=bot_display_name,
            retrieve_log_fn=experience_memory.recall_recent,
            persistence_channel_id=persistence_channel_id,
            snapshot_load_fn=load_wm_snapshot,
            snapshot_save_fn=save_wm_snapshot,
        )

    client = build_discord_client(orchestrator_factory, channel_ids)
    try:
        client.run(discord_token)
    except KeyboardInterrupt:
        # On some platforms/terminals client.run() re-raises instead of
        # swallowing SIGINT internally -- catch it here too so the shutdown
        # save below still runs either way.
        print("[MULCA debug] shutdown: KeyboardInterrupt propagated out of client.run()")  # TODO: remove once live-tested

    # client.run() is documented to return (rather than raising) after a
    # clean Ctrl+C -- discord.py handles SIGINT internally and closes the
    # client before returning. This is the shutdown half of BLUEPRINT.md
    # §11.1; does nothing if the client never reached on_ready (no
    # orchestrator to save).
    print("[MULCA debug] shutdown: client.run() returned, attempting snapshot save")  # TODO: remove once live-tested
    orchestrator = getattr(client, "mulca_orchestrator", None)
    if orchestrator is None:
        print("[MULCA debug] shutdown: no orchestrator on client (never reached on_ready?) -- nothing to save")  # TODO: remove once live-tested
    else:
        asyncio.run(orchestrator.save_group_snapshot())
        print("[MULCA debug] shutdown: save_group_snapshot() finished")  # TODO: remove once live-tested


class Command(BaseCommand):
    help = "Run the MULCA text bot against Discord."

    def add_arguments(self, parser):
        # Default is no reloader: Django's StatReloader runs run_bot() in a
        # child subprocess on Windows, which swallows Ctrl+C before
        # run_bot()'s own shutdown-save code (BLUEPRINT.md §11.1's
        # persistence) ever executes -- confirmed live. --autoreload opts
        # back into dev-convenience auto-restart-on-code-change at the cost
        # of that shutdown save not firing reliably on Windows.
        parser.add_argument(
            "--autoreload",
            action="store_true",
            help="Auto-restart on code changes (dev convenience). On Windows this "
                 "prevents clean-shutdown persistence (BLUEPRINT.md §11.1) from firing "
                 "reliably on Ctrl+C -- omit this flag when testing restart persistence.",
        )

    def handle(self, *args, **options):
        if options["autoreload"]:
            autoreload.run_with_reloader(run_bot)
        else:
            run_bot()
