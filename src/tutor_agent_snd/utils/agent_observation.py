import os
import json

from langfuse import Langfuse
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.util.types import AttributeValue
from livekit.agents.telemetry import set_tracer_provider, tracer as lk_tracer
from livekit.agents.metrics import ModelUsage, TTSMetrics
from livekit.agents.voice.events import MetricsCollectedEvent

# Define pricing models (not provided by LiveKit)
PRICING = {
    "elevenlabs": {"eleven_flash_v2_5": {"character": 0.00011}},
    "cartesia": {"sonic-3": {"character": 0.00005}},
    "deepgram": {"nova-3": {"second": 0.0000966667}},
    "munsit": {"munsit-en-ar": {"second": 0.000833333}, "munsit": {"second": 0.000833333}},
    "api.cerebras.ai": {
        "zai-glm-4.7": {"input": 0.00000225, "output": 0.00000275},
        "gpt-oss-120b": {"input": 0.000000175, "output": 0.000000350},
        "gemma-4-31b": {"input": 0.00000099, "output": 0.00000145},
    },
    "groq": {"llama-3.3-70b-versatile": {"input": 0.00000059, "output": 0.00000079}},
}


def setup_langfuse(
    metadata: dict[str, AttributeValue] | None = None,
    *,
    host: str | None = None,
    public_key: str | None = None,
    secret_key: str | None = None,
    environment: str | None = None,
) -> tuple[TracerProvider, Langfuse]:
    public_key = public_key or os.getenv("LANGFUSE_PUBLIC_KEY")
    secret_key = secret_key or os.getenv("LANGFUSE_SECRET_KEY")
    host = host or os.getenv("LANGFUSE_HOST") or os.getenv("LANGFUSE_BASE_URL")

    if not public_key or not secret_key or not host:
        raise ValueError(
            "LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, and LANGFUSE_HOST (or LANGFUSE_BASE_URL) must be set"
        )

    trace_provider = TracerProvider()
    set_tracer_provider(trace_provider, metadata=metadata)

    langfuse = Langfuse(
        public_key=public_key,
        secret_key=secret_key,
        base_url=host,
        tracer_provider=trace_provider,
        should_export_span=lambda span: True,
    )

    return trace_provider, langfuse


def collect_custom_metrics(ev: MetricsCollectedEvent) -> None:
    metrics = ev.metrics

    if isinstance(metrics, TTSMetrics):
        effective_duration = metrics.duration if metrics.duration > 0 else metrics.ttfb
        start_time_ns = int((metrics.timestamp - effective_duration) * 1e9)
        end_time_ns = int(metrics.timestamp * 1e9)

        span = lk_tracer.start_span("tts_generation", start_time=start_time_ns)
        if metrics.metadata:
            if metrics.metadata.model_name:
                span.set_attribute("gen_ai.request.model", metrics.metadata.model_name)
            if metrics.metadata.model_provider:
                span.set_attribute("gen_ai.provider.name", metrics.metadata.model_provider)
        span.set_attribute("langfuse.observation.type", "generation")
        span.set_attribute("gen_ai.response.ttft", metrics.ttfb)
        span.set_attribute("gen_ai.response.duration", metrics.duration)
        span.set_attribute(
            "langfuse.observation.usage_details",
            json.dumps(
                {
                    "timestamp": metrics.timestamp,
                    "characters_count": metrics.characters_count,
                    "audio_duration": metrics.audio_duration,
                    "duration": metrics.duration,
                    "cancelled": metrics.cancelled,
                }
            ),
        )
        span.end(end_time=end_time_ns)


def calculate_cost(usage: ModelUsage) -> float:
    pricing = PRICING.get(usage.provider.lower(), {}).get(usage.model.lower(), {})
    cost = 0.0

    if usage.type == "llm_usage":
        cost += (usage.input_tokens - usage.input_cached_tokens) * pricing.get("input", 0)
        cost += usage.input_cached_tokens * pricing.get("input_cached", 0)
        cost += usage.output_tokens * pricing.get("output", 0)
    elif usage.type == "tts_usage":
        cost += usage.characters_count * pricing.get("character", 0)
    elif usage.type == "stt_usage":
        cost += usage.audio_duration * pricing.get("second", 0)

    return cost
