"""El nombre del hotel sale de los datos, no del código: es lo que permite replicar el prototipo."""

from copiloto.ai.prompts import build_system_prompt


def test_prompt_takes_the_hotel_name_from_data():
    prompt = build_system_prompt("2026-10-28", "miércoles", "full", "Hostal Los Coihues")
    assert "Hostal Los Coihues" in prompt
    assert "Bordeluz" not in prompt
