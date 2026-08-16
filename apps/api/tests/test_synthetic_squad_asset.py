from gaffertalk_api.services.synthetic_squad import (
    DEFAULT_SYNTHETIC_SQUAD_PATH,
    SyntheticSquadDefinition,
)


def test_default_synthetic_squad_is_packaged_with_api() -> None:
    definition = SyntheticSquadDefinition.model_validate_json(
        DEFAULT_SYNTHETIC_SQUAD_PATH.read_text()
    )

    assert DEFAULT_SYNTHETIC_SQUAD_PATH.parent.name == "data"
    assert DEFAULT_SYNTHETIC_SQUAD_PATH.parent.parent.name == "gaffertalk_api"
    assert definition.name == "GafferTalk Synthetic XI"
    assert len(definition.players) == 15
