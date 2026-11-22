"""Тесты профиля: чистка слотов, фильтры и разбор телефона/времени."""

from __future__ import annotations

from domain.profile import (
    MAX_DEBT_RUB,
    MIN_DEBT_RUB,
    ClientProfile,
    clean_debt,
    clean_region,
    extract_phone,
    extract_time,
    filter_state_text,
    is_excluded_region,
    qualifies_by_debt,
)


def test_debt_threshold() -> None:
    assert qualifies_by_debt(MIN_DEBT_RUB) is True
    assert qualifies_by_debt(MIN_DEBT_RUB - 1) is False
    assert qualifies_by_debt(None) is False


def test_clean_debt_drops_garbage() -> None:
    assert clean_debt(310_000) == 310_000
    assert clean_debt(0) is None
    assert clean_debt(-5) is None
    assert clean_debt(MAX_DEBT_RUB + 1) is None


def test_clean_region_keeps_only_cyrillic() -> None:
    assert clean_region("  Московская область ") == "Московская область"
    assert clean_region("RUB") is None
    assert clean_region("123") is None
    assert clean_region(None) is None


def test_excluded_region_matches_any_case() -> None:
    assert is_excluded_region("Чеченская Республика") is True
    assert is_excluded_region("Москва") is False


def test_filters_ok_needs_both_slots_and_passes_conditions() -> None:
    assert ClientProfile().filters_ok() is False
    assert ClientProfile(debt_amount=310_000).filters_ok() is False
    assert ClientProfile(debt_amount=800_000).filters_ok() is False
    assert ClientProfile(debt_amount=800_000, region="Москва").filters_ok() is True
    assert ClientProfile(debt_amount=200_000, region="Москва").filters_ok() is False
    assert ClientProfile(debt_amount=800_000, region="Владимирская область").filters_ok() is False


def test_failed_filter_checks_known_slots_only() -> None:
    assert ClientProfile(debt_amount=310_000).failed_filter() == "debt"
    assert ClientProfile(region="Владимирская область").failed_filter() == "region"
    assert ClientProfile(debt_amount=800_000).failed_filter() is None
    assert ClientProfile().failed_filter() is None


def test_missing_filter_order() -> None:
    assert ClientProfile().missing_filter() == "debt"
    assert ClientProfile(debt_amount=800_000).missing_filter() == "region"
    assert ClientProfile(debt_amount=800_000, region="Москва").missing_filter() is None


def test_filter_state_text_explains_each_case() -> None:
    assert "не указан" in filter_state_text(ClientProfile())
    assert "меньше 350 000" in filter_state_text(ClientProfile(debt_amount=200_000))
    assert "не обслуживается" in filter_state_text(ClientProfile(debt_amount=800_000, region="Чечня"))
    assert "пройдены" in filter_state_text(ClientProfile(debt_amount=800_000, region="Москва"))


def test_extract_phone() -> None:
    assert extract_phone("мой номер +7 (999) 123-45-67") == "+7 (999) 123-45-67"


def test_extract_time() -> None:
    assert extract_time("давайте в 15:30") == "15:30"
    assert extract_time("можно завтра вечером") == "завтра"
    assert extract_time("в 18 часов удобно") == "18 часов"
    assert extract_time("не важно") is None
