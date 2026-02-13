# Score Improvement Analysis - 2026-02-13

## Issue Found: Discontinuity in Query Length Factor

### Location
`backend/app/services/citation/tracker.py` - `_compute_relevance_score()` method

### Problem
The query length factor has a discontinuity between 2 and 3 tokens:

```python
if len(query_tokens) <= 2:
    query_length_factor = 1 + math.log(len(query_tokens) + 1) * 0.1
else:
    query_length_factor = 1 + math.log(len(query_tokens)) * 0.2
```

### Calculated Values
- 1 token: 1 + log(2) * 0.1 ≈ 1.069
- 2 tokens: 1 + log(3) * 0.1 ≈ 1.110
- 3 tokens: 1 + log(3) * 0.2 ≈ 1.220  ⚠️ Jump!
- 4 tokens: 1 + log(4) * 0.2 ≈ 1.277

### Impact
The sudden jump from 2→3 tokens (1.110 → 1.220) creates inconsistent scoring behavior where 3-token queries are penalized more heavily than expected, potentially ranking worse than similar 2-token queries.

### Solution
Use a smooth logarithmic curve across all query lengths to eliminate the discontinuity while maintaining the intended penalty for longer queries.

### Proposed Fix
```python
# Smooth logarithmic penalty that increases gradually with query length
# without discontinuities
query_length_factor = 1 + math.log(len(query_tokens) + 1) * 0.15
```

This creates a smooth progression:
- 1 token: 1.104
- 2 tokens: 1.165
- 3 tokens: 1.208
- 4 tokens: 1.242

The 0.15 multiplier balances the original behavior (between 0.1 and 0.2) while ensuring continuity.
