"""
Universal Input Validator with Fuzzy Matching for ALL Field Types.

Provides validation and normalization for:
- Keyword fields: Fuzzy match against known values
- Integer fields: Parse and validate against range
- Date fields: Parse multiple formats (full date, month, quarter, year)
- Field names: Fuzzy match against allowed fields
"""
from dataclasses import dataclass, field
from typing import Any, List, Optional, Dict, TYPE_CHECKING
from datetime import datetime, date, timedelta
from rapidfuzz import process, fuzz
import re

if TYPE_CHECKING:
    from index_metadata import IndexMetadata


@dataclass
class ValidationResult:
    """Result of validating an input value."""
    valid: bool
    normalized_value: Any
    original_value: Any
    confidence: float  # 0-100
    field_type: str    # "keyword", "integer", "date", "date_range", "field"
    warnings: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)


class InputValidator:
    """
    Universal input validator with fuzzy matching for ALL field types.

    Provides:
    - Keyword validation with fuzzy matching
    - Integer validation with range checking
    - Date validation with multiple format support
    - Field name validation with suggestions
    """

    def __init__(self, metadata: 'IndexMetadata'):
        """
        Initialize validator with index metadata.

        Args:
            metadata: IndexMetadata instance with cached field values and ranges
        """
        self.metadata = metadata

    # ===== INTEGER VALIDATION =====

    def validate_integer(self, field: str, value: Any) -> ValidationResult:
        """
        Parse and validate integer value against field range.

        Args:
            field: Field name
            value: User-provided value (string or number)

        Returns:
            ValidationResult with parsed integer or error
        """
        field_range = self.metadata.get_numeric_range(field)

        # Parse value
        try:
            if isinstance(value, str):
                parsed = int(float(value.strip()))
            else:
                parsed = int(value)
        except (ValueError, TypeError):
            return ValidationResult(
                valid=False,
                normalized_value=None,
                original_value=value,
                confidence=0,
                field_type="integer",
                warnings=[f"Cannot parse '{value}' as integer"],
                suggestions=[f"Valid range: {field_range.min} - {field_range.max}"]
            )

        # Validate range
        warnings = []
        if field_range.min is not None and field_range.max is not None:
            if parsed < field_range.min or parsed > field_range.max:
                warnings.append(
                    f"{field}={parsed} outside data range "
                    f"[{field_range.min}, {field_range.max}]"
                )

        return ValidationResult(
            valid=True,
            normalized_value=parsed,
            original_value=value,
            confidence=100.0,
            field_type="integer",
            warnings=warnings,
            suggestions=[]
        )

    def validate_integer_range(self, field: str, range_spec: dict) -> ValidationResult:
        """
        Validate integer range filters (gte, gt, lte, lt).

        Args:
            field: Field name
            range_spec: Dict with range operators {gte: value, lte: value, ...}

        Returns:
            ValidationResult with normalized range or error
        """
        field_range = self.metadata.get_numeric_range(field)
        normalized = {}
        warnings = []
        valid_ops = ("gte", "gt", "lte", "lt")

        for op, value in range_spec.items():
            if op not in valid_ops:
                return ValidationResult(
                    valid=False,
                    normalized_value=None,
                    original_value=range_spec,
                    confidence=0,
                    field_type="integer",
                    warnings=[f"Invalid operator '{op}'. Use: {', '.join(valid_ops)}"],
                    suggestions=list(valid_ops)
                )

            try:
                parsed = int(float(value)) if isinstance(value, str) else int(value)
                normalized[op] = parsed

                # Warn if outside data range
                if field_range.min is not None and field_range.max is not None:
                    if op in ("gte", "gt") and parsed > field_range.max:
                        warnings.append(
                            f"{field} {op} {parsed} will match 0 documents "
                            f"(max={field_range.max})"
                        )
                    if op in ("lte", "lt") and parsed < field_range.min:
                        warnings.append(
                            f"{field} {op} {parsed} will match 0 documents "
                            f"(min={field_range.min})"
                        )
            except (ValueError, TypeError):
                return ValidationResult(
                    valid=False,
                    normalized_value=None,
                    original_value=range_spec,
                    confidence=0,
                    field_type="integer",
                    warnings=[f"Cannot parse '{value}' as integer"],
                    suggestions=[f"Valid range: {field_range.min} - {field_range.max}"]
                )

        return ValidationResult(
            valid=True,
            normalized_value=normalized,
            original_value=range_spec,
            confidence=100.0,
            field_type="integer",
            warnings=warnings,
            suggestions=[]
        )

    # ===== DATE VALIDATION =====

    def validate_date(self, field: str, value: str) -> ValidationResult:
        """
        Validate and normalize date. Supports multiple formats:
        - Full date: "2023-01-15" -> "2023-01-15"
        - Month: "2023-06" -> {"gte": "2023-06-01", "lte": "2023-06-30"}
        - Quarter: "Q1 2023" or "2023-Q1" -> {"gte": "2023-01-01", "lte": "2023-03-31"}
        - Year: "2023" -> {"gte": "2023-01-01", "lte": "2023-12-31"}

        Args:
            field: Field name
            value: User-provided date value

        Returns:
            ValidationResult with normalized date or range
        """
        date_range = self.metadata.get_date_range(field)
        value_str = str(value).strip()

        # 1. Try full ISO date (yyyy-MM-dd)
        try:
            parsed = datetime.strptime(value_str, "%Y-%m-%d").date()
            iso_str = parsed.isoformat()
            warnings = []
            if date_range.min and date_range.max:
                if iso_str < date_range.min or iso_str > date_range.max:
                    warnings.append(
                        f"Date {iso_str} outside data range "
                        f"[{date_range.min}, {date_range.max}]"
                    )
            return ValidationResult(
                valid=True,
                normalized_value=iso_str,
                original_value=value,
                confidence=100.0,
                field_type="date",
                warnings=warnings,
                suggestions=[]
            )
        except ValueError:
            pass

        # 2. Try month format (yyyy-MM)
        try:
            parsed = datetime.strptime(value_str, "%Y-%m")
            year, month = parsed.year, parsed.month
            # Calculate last day of month
            if month == 12:
                last_day = date(year + 1, 1, 1) - timedelta(days=1)
            else:
                last_day = date(year, month + 1, 1) - timedelta(days=1)
            range_result = {
                "gte": f"{year:04d}-{month:02d}-01",
                "lte": last_day.isoformat()
            }
            return ValidationResult(
                valid=True,
                normalized_value=range_result,
                original_value=value,
                confidence=100.0,
                field_type="date_range",
                warnings=[f"Expanded '{value}' to range {range_result['gte']} - {range_result['lte']}"],
                suggestions=[]
            )
        except ValueError:
            pass

        # 3. Try quarter format (Q1 2023, 2023-Q1, 2023Q1)
        quarter_match = re.match(
            r'(?:Q(\d)\s*(\d{4})|(\d{4})[-]?Q(\d))',
            value_str,
            re.IGNORECASE
        )
        if quarter_match:
            if quarter_match.group(1):
                quarter = int(quarter_match.group(1))
                year = int(quarter_match.group(2))
            else:
                year = int(quarter_match.group(3))
                quarter = int(quarter_match.group(4))

            if 1 <= quarter <= 4:
                quarter_starts = {1: "01-01", 2: "04-01", 3: "07-01", 4: "10-01"}
                quarter_ends = {1: "03-31", 2: "06-30", 3: "09-30", 4: "12-31"}
                range_result = {
                    "gte": f"{year}-{quarter_starts[quarter]}",
                    "lte": f"{year}-{quarter_ends[quarter]}"
                }
                return ValidationResult(
                    valid=True,
                    normalized_value=range_result,
                    original_value=value,
                    confidence=100.0,
                    field_type="date_range",
                    warnings=[f"Expanded 'Q{quarter} {year}' to range {range_result['gte']} - {range_result['lte']}"],
                    suggestions=[]
                )

        # 4. Try year format (yyyy)
        if re.match(r'^\d{4}$', value_str):
            year = int(value_str)
            range_result = {
                "gte": f"{year}-01-01",
                "lte": f"{year}-12-31"
            }
            return ValidationResult(
                valid=True,
                normalized_value=range_result,
                original_value=value,
                confidence=100.0,
                field_type="date_range",
                warnings=[f"Expanded '{year}' to full year range"],
                suggestions=[]
            )

        # 5. No valid format found
        return ValidationResult(
            valid=False,
            normalized_value=None,
            original_value=value,
            confidence=0,
            field_type="date",
            warnings=[f"Invalid date format '{value}'"],
            suggestions=[
                "Full date: 2023-06-15",
                "Month: 2023-06",
                "Quarter: Q1 2023 or 2023-Q1",
                "Year: 2023",
                f"Data range: {date_range.min} to {date_range.max}"
            ]
        )

    def validate_date_range(self, field: str, range_spec: dict) -> ValidationResult:
        """
        Validate date range filters (gte, gt, lte, lt).
        Each value in range_spec can use any supported date format.

        Args:
            field: Field name
            range_spec: Dict with range operators {gte: value, lte: value, ...}

        Returns:
            ValidationResult with normalized range or error
        """
        normalized = {}
        warnings = []
        valid_ops = ("gte", "gt", "lte", "lt")

        for op, value in range_spec.items():
            if op not in valid_ops:
                return ValidationResult(
                    valid=False,
                    normalized_value=None,
                    original_value=range_spec,
                    confidence=0,
                    field_type="date",
                    warnings=[f"Invalid operator '{op}'. Use: {', '.join(valid_ops)}"],
                    suggestions=list(valid_ops)
                )

            date_result = self.validate_date(field, value)
            if not date_result.valid:
                return date_result

            # If date was expanded to a range, use appropriate bound
            if date_result.field_type == "date_range":
                expanded = date_result.normalized_value
                if op in ("gte", "gt"):
                    normalized[op] = expanded["gte"]
                else:  # lte, lt
                    normalized[op] = expanded["lte"]
                warnings.extend(date_result.warnings)
            else:
                normalized[op] = date_result.normalized_value
                warnings.extend(date_result.warnings)

        return ValidationResult(
            valid=True,
            normalized_value=normalized,
            original_value=range_spec,
            confidence=100.0,
            field_type="date",
            warnings=warnings,
            suggestions=[]
        )

    # ===== FIELD NAME VALIDATION =====

    def validate_field_name(self, field: str, allowed_fields: List[str]) -> ValidationResult:
        """
        Validate field name with fuzzy matching suggestions.

        Args:
            field: User-provided field name
            allowed_fields: List of valid field names

        Returns:
            ValidationResult with exact match or suggestions
        """
        # Exact match
        if field in allowed_fields:
            return ValidationResult(
                valid=True,
                normalized_value=field,
                original_value=field,
                confidence=100.0,
                field_type="field",
                warnings=[],
                suggestions=[]
            )

        # Case-insensitive match
        field_lower = field.lower()
        for allowed in allowed_fields:
            if allowed.lower() == field_lower:
                return ValidationResult(
                    valid=True,
                    normalized_value=allowed,
                    original_value=field,
                    confidence=100.0,
                    field_type="field",
                    warnings=[],
                    suggestions=[]
                )

        # Fuzzy match for suggestions
        result = process.extractOne(
            field, allowed_fields,
            scorer=fuzz.WRatio,
            score_cutoff=70
        )
        if result:
            matched, score, _ = result
            return ValidationResult(
                valid=False,
                normalized_value=None,
                original_value=field,
                confidence=score,
                field_type="field",
                warnings=[f"Unknown field '{field}'"],
                suggestions=[f"Did you mean '{matched}'?"]
            )

        # No close match
        return ValidationResult(
            valid=False,
            normalized_value=None,
            original_value=field,
            confidence=0,
            field_type="field",
            warnings=[f"Unknown field '{field}'"],
            suggestions=allowed_fields[:5]
        )
