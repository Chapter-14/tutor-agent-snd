import os
import json

from langfuse import Langfuse
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.util.types import AttributeValue
from livekit.agents.telemetry import set_tracer_provider, tracer as lk_tracer
from livekit.agents.metrics import TTSMetrics, STTMetrics
from livekit.agents.voice.events import MetricsCollectedEvent
from requests import session


def setup_langfuse(
    metadata: dict[str, AttributeValue] | None = None,
    *,
    host: str | None = None,
    public_key: str | None = None,
    secret_key: str | None = None,
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
            span.set_attribute("langfuse.observation.type", "speech_synthesis")
            span.set_attribute(
                "langfuse.observation.usage_details",
                json.dumps(
                    {
                        "type": metrics.type,
                        "label": metrics.label,
                        "timestamp": metrics.timestamp,
                        "characters_count": metrics.characters_count,
                        "audio_duration": metrics.audio_duration,
                        "ttft": metrics.ttfb,
                        "duration": metrics.duration,
                        "cancelled": metrics.cancelled,
                    }
                ),
            )
            span.end(end_time=end_time_ns)