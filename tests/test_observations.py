import pytest
from unittest.mock import MagicMock

from tutor_agent_snd.utils.agent_observation import calculate_cost


def _make_usage(**kwargs):
    usage = MagicMock()
    usage.provider = kwargs.get("provider", "")
    usage.model = kwargs.get("model", "")

    attrs = {
        "input_tokens": kwargs.get("input_tokens"),
        "output_tokens": kwargs.get("output_tokens"),
        "characters_count": kwargs.get("characters_count"),
        "audio_duration": kwargs.get("audio_duration"),
    }

    for attr, value in attrs.items():
        if value is not None:
            setattr(usage, attr, value)
        else:
            delattr(usage, attr)

    return usage


@pytest.mark.parametrize(
    "provider, model, kwargs, expected",
    [
        (
            "cerebras",
            "zai-glm-4.7",
            {"input_tokens": 1000, "output_tokens": 500},
            0.2,
        ),
        (
            "groq",
            "llama-3.3-70b-versatile",
            {"input_tokens": 1000, "output_tokens": 500},
            0.24,
        ),
        (
            "elevenlabs",
            "eleven_flash_v2_5",
            {"characters_count": 10000},
            0.6,
        ),
        (
            "cartesia",
            "sonic-3",
            {"audio_duration": 100},
            0.03,
        ),
        (
            "deepgram",
            "nova-3",
            {"audio_duration": 100},
            0.015,
        ),
    ],
)
def test_calculate_cost_known_pricing(provider, model, kwargs, expected):
    usage = _make_usage(provider=provider, model=model, **kwargs)
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
    usage = _make_usage(
        provider="cerebras", model="zai-glm-4.7", input_tokens=0, output_tokens=0
    )
    assert calculate_cost(usage) == 0.0
