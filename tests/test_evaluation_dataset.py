import json
from pathlib import Path
import pytest

from app.agent import sanitize_pricing_hallucinations, TekTutorsAgentManager
from app.cache import check_fast_path

TEST_DATASET_PATH = Path(__file__).resolve().parent / "evaluation_test_set.json"


def load_test_cases():
    with open(TEST_DATASET_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data


def test_dataset_structure_and_coverage():
    """Verify test set has 100-200 questions covering all 9 required categories."""
    data = load_test_cases()
    test_cases = data.get("test_cases", [])
    total = len(test_cases)

    # Must be between 100 and 200 questions
    assert 100 <= total <= 200, f"Expected 100-200 questions, got {total}"

    required_categories = {
        "courses_and_curriculum",
        "pricing_and_discounts",
        "objection_handling",
        "ambiguous_queries",
        "registration_and_enrollment",
        "human_escalation_and_advisor_calls",
        "irrelevant_and_out_of_scope",
        "hallucination_prevention",
        "nigerian_and_whatsapp_conversational_language"
    }

    found_categories = {tc["category"] for tc in test_cases}
    missing = required_categories - found_categories
    assert not missing, f"Missing required categories: {missing}"

    # Verify each category has at least 10 questions
    category_counts = {}
    for tc in test_cases:
        cat = tc["category"]
        category_counts[cat] = category_counts.get(cat, 0) + 1

    for cat in required_categories:
        assert category_counts[cat] >= 10, f"Category '{cat}' has fewer than 10 test cases ({category_counts[cat]})"


def test_every_item_has_valid_schema():
    """Ensure each test item has id, category, user_input, intent, and expected_criteria."""
    data = load_test_cases()
    test_cases = data.get("test_cases", [])

    for tc in test_cases:
        assert "id" in tc and tc["id"], "Test case missing valid id"
        assert "category" in tc and tc["category"], f"Test case {tc.get('id')} missing category"
        assert "user_input" in tc and len(tc["user_input"].strip()) > 0, f"Test case {tc.get('id')} missing user_input"
        assert "intent" in tc and tc["intent"], f"Test case {tc.get('id')} missing intent"
        assert "expected_criteria" in tc and isinstance(tc["expected_criteria"], list), f"Test case {tc.get('id')} missing criteria"


@pytest.mark.asyncio
async def test_fast_paths_resolve_for_key_evaluation_cases():
    """Verify instant fast paths correctly trigger on greetings, registration links, and track menu items."""
    # AMBIG-009: "Hello"
    res_hello = await check_fast_path("2348011223344", "Hello")
    assert res_hello is not None
    assert "TekTutors" in res_hello["response"]

    # REG-002: "Send me the registration link"
    res_reg = await check_fast_path("2348011223344", "Send me the registration link")
    assert res_reg is not None
    assert "https://tektutors.com.ng/registration" in res_reg["response"]

    # AMBIG-010: "1"
    res_t1 = await check_fast_path("2348011223344", "1")
    assert res_t1 is not None
    assert "Data Analytics" in res_t1["response"]


def test_pricing_hallucination_prevention_on_dataset_queries():
    """Verify pricing guard sanitizes 900,000 and 1,000,000 hallucinations."""
    hallucinated_texts = [
        "10-wk Data Analytics = ₦900,000 tuition",
        "The total tuition for 10 weeks is 900,000 naira",
        "The full track costs ₦1,000,000"
    ]
    for text in hallucinated_texts:
        cleaned = sanitize_pricing_hallucinations(text)
        assert "900,000" not in cleaned
        assert "1,000,000" not in cleaned
        assert "₦90,000" in cleaned or "₦100,000" in cleaned
