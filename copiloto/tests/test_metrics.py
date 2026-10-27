import json
from types import SimpleNamespace

import pytest

from copiloto import events
from copiloto.metrics import compute_metrics

START = 1_700_000_000.0
END = START + 1_000_000


@pytest.fixture
def conn():
    connection = events.connect(":memory:")
    events.init_db(connection)
    yield connection
    connection.close()


def add(conn, conversation_id, kind, offset=0, **payload):
    return events.record_event(conn, conversation_id, kind, START + offset, payload)


def compute(conn, config=None):
    return compute_metrics(conn, START, END, config if config is not None else SimpleNamespace())


def test_empty_data(conn):
    result = compute(conn)
    for key in (
        "faq_latency_median_s", "faq_latency_p95_s", "commercial_response_compliance_pct",
        "night_capture_rate_pct", "direct_conversion_pct", "cost_per_query_clp",
    ):
        assert result[key] is None
    assert result["commercial_started_in_shift"] == 0
    assert result["commercial_answered_within_180"] == 0
    assert result["queries"] == 0
    assert result["fixed_monthly_clp"] == 90000
    assert result["usage_m_clp"] == 0
    assert result["counts"] == dict.fromkeys(events.EVENT_KINDS, 0)
    assert result["range"] == {"start": START, "end": END}
    json.dumps(result, allow_nan=False)


def test_all_compliant(conn):
    for conversation_id, latency in enumerate([0, 20, 179], start=1):
        add(conn, conversation_id, "commercial_started", in_shift=True)
        add(conn, conversation_id, "human_first_reply", latency, user_id=1)
    result = compute(conn)
    assert result["commercial_response_compliance_pct"] == 100
    assert result["commercial_started_in_shift"] == 3
    assert result["commercial_answered_within_180"] == 3


def test_one_breach(conn):
    for conversation_id, latency in enumerate([179, 181], start=1):
        add(conn, conversation_id, "commercial_started", in_shift=True)
        add(conn, conversation_id, "human_first_reply", latency, user_id=1)
    result = compute(conn)
    assert result["commercial_response_compliance_pct"] == 50
    assert result["commercial_answered_within_180"] == 1


def test_exactly_180_seconds_fails(conn):
    add(conn, 1, "commercial_started", in_shift=True)
    add(conn, 1, "human_first_reply", 180, user_id=1)
    assert compute(conn)["commercial_response_compliance_pct"] == 0


def test_unanswered_at_deadline_counts_as_failure(conn):
    add(conn, 1, "commercial_started", in_shift=True)
    add(conn, 2, "commercial_started", in_shift=True)
    add(conn, 2, "human_first_reply", 100, user_id=1)
    result = compute(conn)
    assert result["commercial_started_in_shift"] == 2
    assert result["commercial_answered_within_180"] == 1
    assert result["commercial_response_compliance_pct"] == 50


def test_night_split(conn):
    add(conn, 1, "commercial_started", in_shift=True)
    add(conn, 1, "human_first_reply", 10, user_id=1)
    add(conn, 2, "commercial_started", in_shift=False)
    add(conn, 3, "commercial_started", in_shift=False)
    add(conn, 2, "night_capture", 5, complete=True)
    add(conn, 2, "night_capture", 6, complete=True)
    add(conn, 3, "night_capture", 5, complete=False)
    add(conn, 99, "night_capture", 5, complete=True)
    result = compute(conn)
    assert result["commercial_started_in_shift"] == 1
    assert result["commercial_response_compliance_pct"] == 100
    assert result["night_capture_rate_pct"] == 50


def test_cost_per_query_in_metrics(conn):
    assert compute(conn)["cost_per_query_clp"] is None
    for conversation_id in range(30):
        add(conn, conversation_id, "inbound", text="Consulta", greeting=False)
    add(conn, 99, "inbound", text="Hola", greeting=True)
    result = compute(conn)
    assert result["queries"] == 30
    assert result["cost_per_query_clp"] == 3000.0


@pytest.mark.parametrize("config", [
    {"fixed_monthly_clp": 600, "usage_m_clp": 40},
    SimpleNamespace(fixed_monthly_clp=600, usage_m_clp=40),
])
def test_config_dict_and_object(conn, config):
    add(conn, 1, "inbound", greeting=False, text="Consulta")
    result = compute(conn, config)
    assert result["fixed_monthly_clp"] == 600
    assert result["usage_m_clp"] == 40
    assert result["cost_per_query_clp"] == 640


def test_partial_config_defaults(conn):
    result = compute(conn, {"usage_m_clp": 100})
    assert result["fixed_monthly_clp"] == 90000
    assert result["usage_m_clp"] == 100


def test_faq_latency_median_and_nearest_rank_p95(conn):
    # Veinte valores desordenados distinguen rango más cercano de interpolación.
    for latency in [20, 1, 3, 2, 4, 6, 5, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19]:
        add(conn, latency, "faq_answered", 100, faq_id="desayuno", inbound_ts=START + 100 - latency)
    add(conn, 99, "inbound", greeting=True, text="Hola")
    result = compute(conn)
    assert result["faq_latency_median_s"] == 10.5
    assert result["faq_latency_p95_s"] == 19


def test_conversion_within_seven_days_and_after(conn):
    for conversation_id in (1, 2, 3, 4):
        add(conn, conversation_id, "commercial_started", in_shift=conversation_id % 2 == 0)
    add(conn, 1, "booking_confirmed", 604799, booking_id=1)
    add(conn, 1, "booking_confirmed", 604800, booking_id=2)
    add(conn, 2, "booking_confirmed", 604800, booking_id=3)
    add(conn, 3, "booking_confirmed", 604801, booking_id=4)
    add(conn, 99, "booking_confirmed", 100, booking_id=5)
    result = compute(conn)
    assert result["direct_conversion_pct"] == 50


def test_first_commercial_start_and_first_reply(conn):
    add(conn, 1, "human_first_reply", 1, user_id=1)
    add(conn, 1, "commercial_started", 10, in_shift=True)
    add(conn, 1, "commercial_started", 100, in_shift=True)
    add(conn, 1, "human_first_reply", 191, user_id=1)
    add(conn, 1, "human_first_reply", 192, user_id=1)
    result = compute(conn)
    assert result["counts"]["commercial_started"] == 2
    assert result["commercial_started_in_shift"] == 1
    assert result["commercial_response_compliance_pct"] == 0


def test_booking_before_commercial_start_is_ignored(conn):
    add(conn, 1, "booking_confirmed", 10, booking_id=1)
    add(conn, 1, "commercial_started", 20, in_shift=True)
    assert compute(conn)["direct_conversion_pct"] == 0


def test_range_filtering(conn):
    add(conn, 1, "inbound", -1, greeting=False, text="Antes")
    add(conn, 2, "inbound", 0, greeting=False, text="Dentro")
    events.record_event(conn, 3, "inbound", END, {"greeting": False, "text": "Fuera"})
    add(conn, 4, "commercial_started", -1, in_shift=True)
    add(conn, 4, "booking_confirmed", 50, booking_id=1)
    add(conn, 5, "commercial_started", 0, in_shift=True)
    events.record_event(conn, 5, "human_first_reply", END, {"user_id": 1})
    add(conn, 6, "commercial_started", -1, in_shift=False)
    add(conn, 6, "night_capture", 20, complete=True)
    result = compute(conn)
    assert result["queries"] == 1
    assert result["counts"]["inbound"] == 1
    assert result["counts"]["commercial_started"] == 1
    assert result["counts"]["human_first_reply"] == 0
    assert result["commercial_response_compliance_pct"] == 0
    assert result["night_capture_rate_pct"] is None
    assert result["direct_conversion_pct"] == 0
