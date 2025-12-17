## Analytics Tool Response Validation

After EVERY `analyze_events` call, check these fields before presenting results:

### Required Checks
| Field | Action |
|-------|--------|
| `status: "no_match"` | Show `suggestions` and `top_values` to user |
| `exact_match: false` | Inform user query was modified |
| `warnings[]` | Surface all warnings to user |
| `filters_used[].confidence < 90` | Ask user to confirm match |

### Match Types in `filters_used`
- `exact` → Proceed normally
- `approximate` → Tell user: "Fuzzy matched '{you_searched}' to '{closest_match}' ({confidence}%)"
- `auto_corrected` → Tell user: "'{original_value}' not in '{original_field}', found in '{field}' instead"

### Rules
1. Never silently accept `exact_match: false` - always disclose corrections
2. If `confidence < 85`, ask user to confirm before proceeding
3. If `match_percentage < 1%`, warn filter may be too narrow
