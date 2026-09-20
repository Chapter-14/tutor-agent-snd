"""Replay a tutor transcript against an authored topic and print the board timeline.

This is the loop for judging beat-binding quality and iterating on the Board Director
prompt without starting a LiveKit session. It runs the real Director against the real
cursor, state and pacing, on a fake clock, so a thirty-second explanation replays in
about as long as the LLM takes to answer.

    uv run python scripts/replay_board.py \\
        --lesson tests/fixtures/ch18_v2/revenue_recognition_model.json \\
        --topic model-objective \\
        --transcript tests/fixtures/ch18_v2/transcript_model_objective_ar.txt

Add --dry-run to exercise the pipeline with a Director that never fires anything,
which checks the plan loads and the transcript segments correctly without an API key.

What to look for in the output:

* a beat firing on the sentence that states its anchor, not three sentences early;
* ``fire_refused`` in the stats, meaning the Director named beats out of order;
* a high ``improvised`` count, meaning the topic's anchors do not match real speech.
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from tutor_agent_snd.board.director import BoardDirector  # noqa: E402
from tutor_agent_snd.board.models import DirectorPlan  # noqa: E402
from tutor_agent_snd.board.runtime import BoardRuntime  # noqa: E402
from tutor_agent_snd.domain_types import Topic  # noqa: E402
from tutor_agent_snd.utils.plan_helpers import parse_plan  # noqa: E402

DEFAULT_PROMPT = REPO_ROOT / "prompts" / "snd-board-director-prompt-v2.md"


class FakeClock:
    """Advances only when the runtime sleeps, so pacing is simulated, not waited out."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    async def sleep(self, delay: float) -> None:
        self.now += delay
        await asyncio.sleep(0)


class SilentDirector:
    async def plan(self, *, window, snapshot, context) -> DirectorPlan:
        print(f"    [window] {' '.join(window)[:100]}")
        return DirectorPlan()


def _load_topic(lesson_path: Path, topic_id: str | None) -> Topic:
    plan = parse_plan(json.loads(lesson_path.read_text()))
    if topic_id is None:
        return plan.topics[0]
    for topic in plan.topics:
        if topic.id == topic_id:
            return topic
    known = ", ".join(topic.id for topic in plan.topics)
    raise SystemExit(f"No topic '{topic_id}' in {lesson_path.name}. Known topics: {known}")


def _build_director(prompt_path: Path, language: str, model: str):
    try:
        from livekit.plugins import cerebras
    except ImportError as error:  # pragma: no cover - environment dependent
        raise SystemExit(f"Cerebras plugin unavailable: {error}") from error
    if not os.getenv("CEREBRAS_API_KEY"):
        raise SystemExit("CEREBRAS_API_KEY is not set. Use --dry-run to replay without an LLM.")

    return BoardDirector(
        llm=cerebras.LLM(model=model, temperature=0.2, parallel_tool_calls=False),
        system_prompt=prompt_path.read_text(),
        language=language,
        model=model,
    )


def _describe(payload: dict) -> str:
    action = payload["action"].removeprefix("board_")
    if action == "add":
        return f"add {payload['kind']:<11} [{payload['region']}] {json.dumps(payload['payload'], ensure_ascii=False)[:90]}"
    if action == "set_title":
        return f"title            {payload['text']}"
    if action == "clear":
        return f"clear            scope={payload['scope']}"
    if action == "update":
        detail = payload.get("text") or payload.get("state")
        return f"update           slot={payload.get('slot')} -> {detail}"
    if action == "annotate":
        return f"annotate         kind={payload.get('kind')}"
    if action == "reveal":
        return f"reveal           chunk {payload['index']}"
    if action == "pin":
        return f"pin              region={payload['region']}"
    if action == "group":
        return f"group {payload['kind']:<9}  {payload['heading']}"
    return action


async def replay(args: argparse.Namespace) -> None:
    topic = _load_topic(Path(args.lesson), args.topic)
    transcript = Path(args.transcript).read_text().strip()
    if not transcript:
        raise SystemExit("Transcript is empty.")

    clock = FakeClock()
    director = (
        SilentDirector()
        if args.dry_run
        else _build_director(Path(args.prompt), args.language, args.model)
    )

    async def publish(payload: dict) -> None:
        print(f"  t={clock.now:6.1f}s  rev={payload['rev']:<3} {_describe(payload)}")

    runtime = BoardRuntime(
        publish=publish,
        director=director,
        words_per_second=args.words_per_second,
        clock=clock,
        sleep=clock.sleep,
    )
    await runtime.start()

    print(f"\nTOPIC  {topic.title}  ({topic.knowledge_type})")
    print(f"BEATS  {', '.join(beat.id for beat in topic.beats) or '(none)'}\n")

    await runtime.begin_topic(topic)

    async def stream():
        # One word at a time, the way a streaming LLM delivers it.
        for word in transcript.split(" "):
            yield word + " "
            await asyncio.sleep(0)

    async for _ in runtime.tee(stream(), "replay-1"):
        pass

    # Let the Director and executor drain; the clock only moves when they sleep.
    for _ in range(2000):
        await asyncio.sleep(0)
        if runtime.stats["plans"] and clock.now > args.max_seconds:
            break

    await runtime.aclose()

    pending = runtime.cursor.previews(limit=20)
    print(f"\nSTATS  {dict(sorted(runtime.stats.items()))}")
    print(f"UNFIRED  {', '.join(preview.beat_id for preview in pending) or '(none)'}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--lesson", required=True, help="Path to a v2 lesson JSON file")
    parser.add_argument("--topic", default=None, help="Topic id (default: the first topic)")
    parser.add_argument("--transcript", required=True, help="Path to the tutor transcript")
    parser.add_argument("--prompt", default=str(DEFAULT_PROMPT), help="Director system prompt")
    parser.add_argument("--language", default="Arabic")
    parser.add_argument("--model", default=os.getenv("BOARD_DIRECTOR_MODEL", "qwen-3.8-27b"))
    parser.add_argument("--words-per-second", type=float, default=2.0)
    parser.add_argument("--max-seconds", type=float, default=600.0)
    parser.add_argument("--dry-run", action="store_true", help="Replay without calling an LLM")
    asyncio.run(replay(parser.parse_args()))


if __name__ == "__main__":
    main()
