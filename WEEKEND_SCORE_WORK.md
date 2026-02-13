# Weekend Score Improvement Work - Feb 13, 2026

## ✅ Completed

### Issue Fixed: Query Length Factor Discontinuity

**File**: `backend/app/services/citation/tracker.py`  
**Method**: `_compute_relevance_score()`

**Problem**: The query length normalization factor had a discontinuity between 2 and 3 tokens, causing inconsistent ranking behavior.

**Before**:
```python
if len(query_tokens) <= 2:
    query_length_factor = 1 + math.log(len(query_tokens) + 1) * 0.1
else:
    query_length_factor = 1 + math.log(len(query_tokens)) * 0.2
```

Values: 1.069 (1 token) → 1.110 (2 tokens) → **1.220** (3 tokens) ⚠️ Jump!

**After**:
```python
query_length_factor = 1 + math.log(len(query_tokens) + 1) * 0.15
```

Values: 1.104 → 1.165 → 1.208 → 1.242 ✓ Smooth progression

**Impact**: More consistent and predictable relevance scoring across different query lengths.

**Commit**: `5cb0b39` - "Fix relevance score discontinuity in query length factor"

---

## 📊 Analysis Summary

The citation tracker's scoring system is generally well-designed with:
- **Relevance scoring**: Phrase matching + token frequency with decay
- **Authority scoring**: Source-type based weights (Database=1.0, Web=0.65, etc.)
- **Recency scoring**: Time-based decay with realistic curves
- **Validation confidence**: Multi-factor weighted composite (properly sums to 1.0)

The discontinuity fix improves scoring stability without requiring major refactoring.

---

## 🔍 Potential Future Improvements

1. **Token Contribution Decay**: Current decay `/ (1 + i * 0.5)` could be tuned based on real-world query patterns

2. **Phrase Weight Tuning**: Current weights are static:
   - title: 20.0
   - description: 10.0
   - other: 5.0
   
   Consider A/B testing or machine learning calibration

3. **Authority Weights**: Current source type weights are heuristic. Could benefit from:
   - Domain-specific authority scores
   - Citation graph analysis (PageRank-style)

4. **Recency Scoring**: The decay curve is well-designed but hardcoded. Could add:
   - Domain-specific recency windows (tech=shorter, history=longer)
   - Configurable decay profiles

5. **Test Coverage**: Add unit tests specifically for:
   - Query length factor continuity
   - Score boundary conditions (empty queries, very long queries)
   - Edge cases in recency calculation (future dates, very old dates)

---

## 📝 Branch Status

- **Branch**: `feat/score-stabilization-20260211`
- **Parent**: `main` (up to date)
- **Commits on branch**: 5 (including this fix)
- **Status**: Clean working tree, ready for review
- **Next**: NO PUSH per instructions - awaiting review

---

## 🎯 Recommendation

The fix is small, focused, and improves consistency without breaking changes. The scoring system is otherwise solid - future work should focus on tuning weights and expanding test coverage rather than structural changes.
