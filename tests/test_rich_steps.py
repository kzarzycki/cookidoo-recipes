"""Self-check for structured Thermomix machine settings -> Cookidoo annotations.

Runnable standalone (`python tests/test_rich_steps.py`) or under pytest.
Proves: a structured TTS step, a Varoma/STEAMING MODE step, and a not-doable
program step each serialize to the correct PATCH instruction.
"""

from cookidoo_mcp.models import RecipeStep, TURBO_DEFAULT_PULSE_COUNT


def test_structured_tts_anchors_regardless_of_prose():
    """10 min / 100 C / speed 1, reverse -> TTS, anchored even when the prose
    does not contain the marker (the marker is appended and anchored)."""
    step = RecipeStep(
        text="Cook the sauce until thickened.",
        time_seconds=600,
        temperature_c=100,
        speed="1",
        reverse=True,
    )
    instr = step.to_cookidoo_instruction()
    ann = instr["annotations"][0]
    assert ann["type"] == "TTS"
    assert ann["data"] == {
        "speed": "1",
        "time": 600,
        "temperature": {"value": "100", "unit": "C"},
        "direction": "CCW",
    }
    pos = ann["position"]
    # position anchors to a real substring of the (possibly extended) text
    assert instr["text"][pos["offset"] : pos["offset"] + pos["length"]]
    assert instr["missedUsages"] == []


def test_in_prose_marker_matches_lava_cake_shape():
    """When the marker is already in the prose, text is untouched and the
    offset/length/data reproduce the captured lava-cake annotation exactly."""
    step = RecipeStep(
        text="Place egg whites and salt in the bowl and whisk 6 min/speed 3.5.",
        time_seconds=360,
        speed="3.5",
    )
    instr = step.to_cookidoo_instruction()
    assert instr["text"] == "Place egg whites and salt in the bowl and whisk 6 min/speed 3.5."
    ann = instr["annotations"][0]
    assert ann == {
        "type": "TTS",
        "position": {"offset": 48, "length": 15},
        "data": {"speed": "3.5", "time": 360},
    }


def test_steaming_varoma_mode():
    """mode=STEAMING -> MODE annotation with name sibling of data and the
    Varoma accessory (defaulted when not given)."""
    step = RecipeStep(text="Steam the vegetables.", mode="STEAMING", time_seconds=900, tm_model="TM7")
    instr = step.to_cookidoo_instruction()
    ann = instr["annotations"][0]
    assert ann["type"] == "MODE"
    # MODE name is the lowercase wire literal the created-recipe API persists.
    assert ann["name"] == "steaming"
    assert ann["data"]["accessory"] == "Varoma"
    assert ann["data"]["time"] == 900
    # STEAMING requires a direction; forward defaults to the "CW" literal.
    assert ann["data"]["direction"] == "CW"
    # STEAMING rejects temperature -> it is never emitted, even if requested.
    assert "temperature" not in ann["data"]


def test_steaming_reverse_direction_is_ccw():
    """A reverse/Linkslauf steaming step emits the case-sensitive "CCW" literal."""
    step = RecipeStep(text="Steam.", mode="STEAMING", time_seconds=600, reverse=True)
    ann = step.to_cookidoo_instruction()["annotations"][0]
    assert ann["data"]["direction"] == "CCW"


def test_browning_mode_with_tm7_power():
    """BROWNING uses its own temp enum (140..160) and a power enum (Gentle/Intense).

    Live-verified: a manual-range temp (120) is below the browning range and is
    dropped (prose), and a numeric power ("high"/"5") would silently strip the whole
    annotation, so it is coerced to a valid level.
    """
    step = RecipeStep(
        text="Brown the meat.",
        mode="BROWNING",
        time_seconds=300,
        temperature_c=160,
        power="high",
        tm_model="TM7",
    )
    ann = step.to_cookidoo_instruction()["annotations"][0]
    assert ann["type"] == "MODE" and ann["name"] == "browning"
    assert ann["data"]["temperature"] == {"value": "160", "unit": "C"}
    assert ann["data"]["power"] in ("Gentle", "Intense")


def test_turbo_pulse_count_required():
    """TURBO requires pulseCount on the wire (omitting it 400-rejects the PATCH),
    so it is always emitted, defaulted when unset."""
    step = RecipeStep(text="Pulse.", mode="TURBO", time_seconds=2, pulse_count=3, tm_model="TM6")
    ann = step.to_cookidoo_instruction()["annotations"][0]
    assert ann["data"]["pulseCount"] == 3
    step2 = RecipeStep(text="Pulse.", mode="TURBO", time_seconds=2)
    ann2 = step2.to_cookidoo_instruction()["annotations"][0]
    assert ann2["data"]["pulseCount"] == TURBO_DEFAULT_PULSE_COUNT


def test_turbo_time_out_of_enum_falls_back_to_tts():
    """TURBO time is the enum {1,2}; time:3 (or absent) would 400/strip on save,
    so an out-of-range turbo falls back to a surviving encoding, never a MODE."""
    step = RecipeStep(text="Pulse.", mode="TURBO", time_seconds=3, speed="5")
    ann = step.to_cookidoo_instruction()["annotations"][0]
    assert ann["type"] != "MODE"  # not a silently-stripped turbo MODE
    step2 = RecipeStep(text="Pulse.", mode="TURBO")  # no time
    instr2 = step2.to_cookidoo_instruction()
    assert all(a["type"] != "MODE" for a in instr2["annotations"])
    step3 = RecipeStep(text="Pulse.", mode="TURBO", time_seconds=1)  # in enum
    assert step3.to_cookidoo_instruction()["annotations"][0]["type"] == "MODE"


def test_not_doable_program_is_plain_text():
    """A named program the API cannot structure: agent renders it into prose and
    passes no machine fields -> clean text step, no fabricated annotation."""
    step = RecipeStep(text="Sous-vide 63 °C / 45 min (set program manually).")
    instr = step.to_cookidoo_instruction()
    assert instr["annotations"] == []
    assert instr["text"] == "Sous-vide 63 °C / 45 min (set program manually)."


def test_off_enum_temperature_does_not_fake_a_setting():
    """A temperature outside the fixed enum range yields no annotation rather
    than a snapped, misleading value; the prose is preserved verbatim."""
    step = RecipeStep(text="Caramelize sugar at 160 °C.", temperature_c=160)
    instr = step.to_cookidoo_instruction()
    assert instr["annotations"] == []
    assert instr["text"] == "Caramelize sugar at 160 °C."


def test_nearest_enum_snap_for_normal_temps():
    """72 C is not on the enum; the Thermomix only offers 70/75, so snap to the
    nearest real setting (faithful to the machine), not drop it."""
    step = RecipeStep(text="Heat 5 min/72°C/speed 2.", time_seconds=300, temperature_c=72, speed="2")
    ann = step.to_cookidoo_instruction()["annotations"][0]
    assert ann["data"]["temperature"]["value"] == "70"


def test_backward_compatible_plain_string_step():
    step = RecipeStep.from_any("Mix everything together.")
    instr = step.to_cookidoo_instruction()
    assert instr["type"] == "STEP"
    assert instr["annotations"] == []


def test_backward_compatible_explicit_annotations_passthrough():
    step = RecipeStep.from_any(
        {
            "text": "Mix 20 sec/speed 5.",
            "annotations": [
                {"type": "TTS", "data": {"speed": "5", "time": 20}, "position": {"offset": 4, "length": 14}}
            ],
        }
    )
    instr = step.to_cookidoo_instruction()
    assert instr["annotations"][0]["data"]["speed"] == "5"


def _run_all():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("all rich-step checks passed")


if __name__ == "__main__":
    _run_all()
