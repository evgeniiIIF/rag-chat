"""Тесты профиля клиента и сценария консультации (документ ¶59-¶60)."""

from __future__ import annotations

from core.behavior import (
    ASK_DEBT,
    ASK_PROPERTY,
    ASK_REGION,
    INVITE,
    NOT_OUR_CASE_DEBT,
    NOT_OUR_CASE_REGION,
)
from domain.profile import ClientProfile, next_question, qualify, scenario_reply

MIN_DEBT = 350_000
EXCLUDED = ("чечня", "днр", "лнр", "владимирская")


def test_scenario_asks_for_debt_first() -> None:
    assert next_question(ClientProfile()) == ASK_DEBT


def test_scenario_goes_step_by_step() -> None:
    with_debt = ClientProfile(debt_amount=800_000)

    assert next_question(with_debt) == ASK_REGION
    assert next_question(ClientProfile(debt_amount=800_000, region="Москва")) == ASK_PROPERTY
    assert next_question(ClientProfile(debt_amount=800_000, region="Москва", has_property=True)) is None


def test_qualification_rejects_small_debt_and_excluded_region() -> None:
    small = ClientProfile(debt_amount=200_000, region="Москва")
    banned = ClientProfile(debt_amount=800_000, region="Владимирская область")
    ok = ClientProfile(debt_amount=350_000, region="Москва")

    assert qualify(small, min_debt_rub=MIN_DEBT, excluded_regions=EXCLUDED) == "small_debt"
    assert qualify(banned, min_debt_rub=MIN_DEBT, excluded_regions=EXCLUDED) == "excluded_region"
    assert qualify(ok, min_debt_rub=MIN_DEBT, excluded_regions=EXCLUDED) == "ok"


def test_qualification_is_quiet_while_data_is_missing() -> None:
    assert qualify(ClientProfile(), min_debt_rub=MIN_DEBT, excluded_regions=EXCLUDED) == "ok"


def test_scenario_reply_covers_all_outcomes() -> None:
    full = ClientProfile(debt_amount=800_000, region="Москва", has_property=True)

    assert scenario_reply(full, "ok") == INVITE
    assert scenario_reply(ClientProfile(), "ok") == ASK_DEBT
    assert scenario_reply(full, "small_debt") == NOT_OUR_CASE_DEBT
    assert scenario_reply(full, "excluded_region") == NOT_OUR_CASE_REGION
