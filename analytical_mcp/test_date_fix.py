"""
Test script to verify the date range expansion fix.
Ensures 'lt' is used instead of 'lte' for correct date boundary handling.
"""
import sys
from dataclasses import dataclass
from typing import Optional

# Mock the IndexMetadata for standalone testing
@dataclass
class Range:
    min: Optional[str] = None
    max: Optional[str] = None

class MockMetadata:
    def get_date_range(self, field):
        return Range(min="2020-01-01", max="2025-12-31")

    def get_numeric_range(self, field):
        return Range(min=2020, max=2025)

# Import the validator
from input_validator import InputValidator

def test_date_expansion():
    """Test that date expansion uses 'lt' instead of 'lte'."""
    validator = InputValidator(MockMetadata())

    tests = [
        # (input, expected_gte, expected_lt, description)

        # Year tests
        ("2023", "2023-01-01", "2024-01-01", "Year 2023"),
        ("2024", "2024-01-01", "2025-01-01", "Year 2024"),
        ("2020", "2020-01-01", "2021-01-01", "Year 2020"),

        # Month tests
        ("2023-01", "2023-01-01", "2023-02-01", "January 2023"),
        ("2023-06", "2023-06-01", "2023-07-01", "June 2023"),
        ("2023-12", "2023-12-01", "2024-01-01", "December 2023 (year rollover)"),
        ("2024-02", "2024-02-01", "2024-03-01", "February 2024 (leap year)"),

        # Quarter tests
        ("Q1 2023", "2023-01-01", "2023-04-01", "Q1 2023"),
        ("Q2 2023", "2023-04-01", "2023-07-01", "Q2 2023"),
        ("Q3 2023", "2023-07-01", "2023-10-01", "Q3 2023"),
        ("Q4 2023", "2023-10-01", "2024-01-01", "Q4 2023 (year rollover)"),
        ("2023-Q1", "2023-01-01", "2023-04-01", "2023-Q1 format"),
        ("2023Q2", "2023-04-01", "2023-07-01", "2023Q2 format"),
    ]

    passed = 0
    failed = 0

    print("=" * 70)
    print("Testing Date Expansion Fix (lte → lt)")
    print("=" * 70)

    for input_val, expected_gte, expected_lt, description in tests:
        result = validator.validate_date("event_date", input_val)

        if not result.valid:
            print(f"❌ FAIL: {description}")
            print(f"   Input: {input_val}")
            print(f"   Error: {result.warnings}")
            failed += 1
            continue

        normalized = result.normalized_value

        # Check it's a range (not a single date)
        if not isinstance(normalized, dict):
            print(f"❌ FAIL: {description}")
            print(f"   Input: {input_val}")
            print(f"   Expected dict, got: {normalized}")
            failed += 1
            continue

        # Check for 'lt' key (not 'lte')
        if "lte" in normalized:
            print(f"❌ FAIL: {description}")
            print(f"   Input: {input_val}")
            print(f"   Still using 'lte': {normalized}")
            print(f"   Should use 'lt' instead!")
            failed += 1
            continue

        if "lt" not in normalized:
            print(f"❌ FAIL: {description}")
            print(f"   Input: {input_val}")
            print(f"   Missing 'lt' key: {normalized}")
            failed += 1
            continue

        # Check values
        actual_gte = normalized.get("gte")
        actual_lt = normalized.get("lt")

        if actual_gte == expected_gte and actual_lt == expected_lt:
            print(f"✅ PASS: {description}")
            print(f"   {input_val} → gte: {actual_gte}, lt: {actual_lt}")
            passed += 1
        else:
            print(f"❌ FAIL: {description}")
            print(f"   Input: {input_val}")
            print(f"   Expected: gte={expected_gte}, lt={expected_lt}")
            print(f"   Got:      gte={actual_gte}, lt={actual_lt}")
            failed += 1

    print("=" * 70)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 70)

    return failed == 0


def test_full_date_unchanged():
    """Test that full ISO dates are NOT expanded (returned as-is)."""
    validator = InputValidator(MockMetadata())

    print("\n" + "=" * 70)
    print("Testing Full Date (should NOT be expanded)")
    print("=" * 70)

    tests = [
        ("2023-01-15", "2023-01-15"),
        ("2023-12-31", "2023-12-31"),
        ("2024-02-29", "2024-02-29"),  # Leap day
    ]

    passed = 0
    failed = 0

    for input_val, expected in tests:
        result = validator.validate_date("event_date", input_val)

        if not result.valid:
            print(f"❌ FAIL: {input_val} - {result.warnings}")
            failed += 1
            continue

        # Full date should return string, not dict
        if isinstance(result.normalized_value, dict):
            print(f"❌ FAIL: {input_val}")
            print(f"   Should NOT be expanded, but got: {result.normalized_value}")
            failed += 1
            continue

        if result.normalized_value == expected:
            print(f"✅ PASS: {input_val} → {result.normalized_value} (not expanded)")
            passed += 1
        else:
            print(f"❌ FAIL: {input_val}")
            print(f"   Expected: {expected}")
            print(f"   Got: {result.normalized_value}")
            failed += 1

    print("=" * 70)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 70)

    return failed == 0


def test_date_range_validation():
    """Test validate_date_range converts lte to lt when date is expanded."""
    validator = InputValidator(MockMetadata())

    print("\n" + "=" * 70)
    print("Testing Date Range Validation (lte → lt conversion)")
    print("=" * 70)

    tests = [
        # (range_spec, expected_output, description)
        ({"gte": "2023", "lte": "2024"}, {"gte": "2023-01-01", "lt": "2025-01-01"}, "Year range with lte"),
        ({"gte": "2023-01", "lte": "2023-06"}, {"gte": "2023-01-01", "lt": "2023-07-01"}, "Month range with lte"),
        ({"gte": "Q1 2023", "lte": "Q2 2023"}, {"gte": "2023-01-01", "lt": "2023-07-01"}, "Quarter range with lte"),
        ({"lt": "2023"}, {"lt": "2024-01-01"}, "Only lt with year"),
    ]

    passed = 0
    failed = 0

    for range_spec, expected, description in tests:
        result = validator.validate_date_range("event_date", range_spec)

        if not result.valid:
            print(f"❌ FAIL: {description}")
            print(f"   Input: {range_spec}")
            print(f"   Error: {result.warnings}")
            failed += 1
            continue

        normalized = result.normalized_value

        # Check for 'lte' - should NOT be present if input was expanded
        if "lte" in normalized and "lte" in range_spec:
            # lte should have been converted to lt
            print(f"❌ FAIL: {description}")
            print(f"   Input: {range_spec}")
            print(f"   'lte' was NOT converted to 'lt': {normalized}")
            failed += 1
            continue

        if normalized == expected:
            print(f"✅ PASS: {description}")
            print(f"   {range_spec} → {normalized}")
            passed += 1
        else:
            print(f"❌ FAIL: {description}")
            print(f"   Input: {range_spec}")
            print(f"   Expected: {expected}")
            print(f"   Got:      {normalized}")
            failed += 1

    print("=" * 70)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 70)

    return failed == 0


def test_boundary_semantics():
    """
    Critical test: Verify the boundary semantics are correct.

    The key insight:
    - "lt": "2024-01-01" means < 2024-01-01T00:00:00 (excludes Jan 1)
    - This correctly includes 2023-12-31T23:59:59.999

    The old bug:
    - "lte": "2023-12-31" means <= 2023-12-31T00:00:00 (excludes rest of Dec 31!)
    """
    validator = InputValidator(MockMetadata())

    print("\n" + "=" * 70)
    print("Testing Boundary Semantics (Critical)")
    print("=" * 70)

    result = validator.validate_date("event_date", "2023")
    normalized = result.normalized_value

    print(f"Input: '2023'")
    print(f"Output: {normalized}")
    print()

    # The critical check: lt with next year
    if normalized.get("lt") == "2024-01-01":
        print("✅ Boundary check: 'lt: 2024-01-01' correctly includes:")
        print("   - 2023-12-31T00:00:00 ✓")
        print("   - 2023-12-31T12:00:00 ✓")
        print("   - 2023-12-31T23:59:59.999 ✓")
        print()
        print("   And correctly excludes:")
        print("   - 2024-01-01T00:00:00 ✗")
        passed = True
    else:
        print("❌ Boundary check FAILED!")
        print(f"   Expected 'lt': '2024-01-01'")
        print(f"   Got: {normalized}")
        passed = False

    print("=" * 70)
    return passed


if __name__ == "__main__":
    all_passed = True

    all_passed &= test_date_expansion()
    all_passed &= test_full_date_unchanged()
    all_passed &= test_date_range_validation()
    all_passed &= test_boundary_semantics()

    print("\n" + "=" * 70)
    if all_passed:
        print("🎉 ALL TESTS PASSED!")
    else:
        print("💥 SOME TESTS FAILED!")
    print("=" * 70)

    sys.exit(0 if all_passed else 1)
