from unittest.mock import MagicMock

import pytest

from tutor_agent_snd.utils.agent_observation import calculate_cost


def _make_usage(**kwargs):
    usage = MagicMock()
    usage.type = kwargs.get("type", "llm_usage")
    usage.provider = kwargs.get("provider", "")
    usage.model = kwargs.get("model", "")
    usage.input_tokens = kwargs.get("input_tokens", 0)
    usage.input_cached_tokens = kwargs.get("input_cached_tokens", 0)
    usage.output_tokens = kwargs.get("output_tokens", 0)
    usage.characters_count = kwargs.get("characters_count", 0)
    usage.audio_duration = kwargs.get("audio_duration", 0)

    return usage


@pytest.mark.parametrize(
    "usage_type, provider, model, kwargs, expected",
    [
        (
            "llm_usage",
            "api.cerebras.ai",
            "zai-glm-4.7",
            {"input_tokens": 1000, "output_tokens": 500},
            0.003625,
        ),
        (
            "llm_usage",
            "groq",
            "llama-3.3-70b-versatile",
            {"input_tokens": 1000, "output_tokens": 500},
            0.000985,
        ),
        (
            "tts_usage",
            "elevenlabs",
            "eleven_flash_v2_5",
            {"characters_count": 10000},
            1.1,
        ),
        (
            "tts_usage",
            "cartesia",
            "sonic-3",
            {"characters_count": 10000},
            0.5,
        ),
        (
            "stt_usage",
            "deepgram",
            "nova-3",
            {"audio_duration": 100},
            0.00966667,
        ),
    ],
)
def test_calculate_cost_known_pricing(usage_type, provider, model, kwargs, expected):
    usage = _make_usage(type=usage_type, provider=provider, model=model, **kwargs)
    assert calculate_cost(usage) == pytest.approx(expected)


def test_calculate_cost_unknown_provider():
    usage = _make_usage(provider="unknown", model="foo", input_tokens=100)
    assert calculate_cost(usage) == 0.0


def test_calculate_cost_unknown_model():
    usage = _make_usage(
        provider="cerebras", model="unknown-model", input_tokens=100, output_tokens=50
    )
    assert calculate_cost(usage) == 0.0


def test_calculate_cost_zero_tokens():
    usage = _make_usage(provider="cerebras", model="zai-glm-4.7", input_tokens=0, output_tokens=0)
    assert calculate_cost(usage) == 0.0
