"""
MulcaInstance: which text channel + voice channel + participant roster make
up one MULCA bot's persistent memory, and how a raw channel id resolves back
to the instance (and therefore the conversation_id/DB file) that owns it.
"""

from mulca_discord.instances import (
    MulcaInstance,
    instance_for_channel,
    instance_for_participant,
    load_instances,
)


def test_conversation_id_is_derived_from_the_instance_name_not_a_channel_id():
    instance = MulcaInstance(name="team-alpha", text_channel_id=111)

    assert instance.conversation_id == "instance:team-alpha"


def test_an_instance_owns_both_its_text_and_voice_channel():
    instance = MulcaInstance(
        name="team-alpha", text_channel_id=111, voice_channel_id=222
    )

    assert instance.owns_channel(111)
    assert instance.owns_channel(222)
    assert not instance.owns_channel(333)


def test_an_instance_without_a_voice_channel_only_owns_its_text_channel():
    instance = MulcaInstance(name="team-alpha", text_channel_id=111)

    assert instance.owns_channel(111)
    assert not instance.owns_channel(None)


def test_instance_for_channel_finds_the_owning_instance_by_either_channel():
    alpha = MulcaInstance(name="team-alpha", text_channel_id=111, voice_channel_id=222)
    beta = MulcaInstance(name="team-beta", text_channel_id=333, voice_channel_id=444)

    assert instance_for_channel([alpha, beta], 111) is alpha
    assert instance_for_channel([alpha, beta], 222) is alpha
    assert instance_for_channel([alpha, beta], 444) is beta


def test_instance_for_channel_is_none_for_an_unconfigured_channel():
    alpha = MulcaInstance(name="team-alpha", text_channel_id=111)

    assert instance_for_channel([alpha], 999) is None


def test_load_instances_parses_the_yaml_shape(tmp_path):
    config = tmp_path / "instances.yaml"
    config.write_text(
        """
instances:
  - name: team-alpha
    text_channel_id: 111
    voice_channel_id: 222
    participant_ids: [1, 2]
  - name: team-beta
    text_channel_id: 333
""",
        encoding="utf-8",
    )

    instances = load_instances(config)

    assert len(instances) == 2
    assert instances[0] == MulcaInstance(
        name="team-alpha",
        text_channel_id=111,
        voice_channel_id=222,
        participant_ids=frozenset({1, 2}),
    )
    # voice_channel_id and participant_ids are both optional.
    assert instances[1] == MulcaInstance(name="team-beta", text_channel_id=333)


def test_load_instances_is_empty_for_a_config_with_no_instances(tmp_path):
    config = tmp_path / "instances.yaml"
    config.write_text("instances: []\n", encoding="utf-8")

    assert load_instances(config) == []


def test_instance_for_participant_finds_the_instance_that_lists_them():
    alpha = MulcaInstance(
        name="team-alpha", text_channel_id=111, participant_ids=frozenset({1, 2})
    )
    beta = MulcaInstance(
        name="team-beta", text_channel_id=333, participant_ids=frozenset({3})
    )

    assert instance_for_participant([alpha, beta], 1) is alpha
    assert instance_for_participant([alpha, beta], 3) is beta


def test_instance_for_participant_is_none_for_an_unrecognized_user():
    alpha = MulcaInstance(
        name="team-alpha", text_channel_id=111, participant_ids=frozenset({1})
    )

    assert instance_for_participant([alpha], 999) is None


def test_mulca_instances_points_at_another_file(tmp_path, monkeypatch):
    from mulca_discord.instances import DEFAULT_CONFIG_PATH, configured_instances_path

    local = tmp_path / "instances.local.yaml"
    local.write_text(
        "instances:\n  - name: mulca-test\n    text_channel_id: 1\n    voice_channel_id: 2\n",
        encoding="utf-8",
    )

    monkeypatch.delenv("MULCA_INSTANCES", raising=False)
    assert configured_instances_path() == DEFAULT_CONFIG_PATH

    monkeypatch.setenv("MULCA_INSTANCES", str(local))
    [instance] = load_instances(configured_instances_path())
    assert instance.name == "mulca-test"
    assert instance.voice_channel_id == 2
