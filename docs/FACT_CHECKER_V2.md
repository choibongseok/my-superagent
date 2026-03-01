# Fact Checker v2 Enhancement

## Overview

Enhanced fact checking service with Wolfram Alpha integration, contradiction detection, and improved confidence scoring algorithms.

**Status**: ✅ Implemented (Sprint 10 - 2026-03-01)  
**Feature Flag**: `fact_checker_v2=True`

---

## New Features

### 1. Wolfram Alpha Integration 🧮

Automatic verification of numeric claims and calculations using Wolfram Alpha API.

**Capabilities:**
- Mathematical expression verification (e.g., "5 + 3 = 8")
- Population queries (e.g., "population of US")
- Distance calculations (e.g., "distance from Earth to Moon")
- Temperature conversions
- Unit conversions
- Scientific calculations

**Configuration:**
```bash
# Set Wolfram Alpha App ID in environment
WOLFRAM_APP_ID=your_app_id_here
```

Get your free Wolfram Alpha App ID at: https://developer.wolframalpha.com/

**Example:**
```python
from app.services.fact_checker import FactCheckerService

# Claim with numeric data
claim = "The Earth's circumference is approximately 40,075 km at the equator."

# Will automatically verify with Wolfram Alpha
result = await fact_checker_service.verify_claim(
    claim=claim,
    task_id=task_id,
    user_id=user_id,
    sources=sources
)

# Check Wolfram verification results
if result.verification_details and "wolfram_results" in result.verification_details:
    wolfram_results = result.verification_details["wolfram_results"]
    for r in wolfram_results:
        print(f"Query: {r['query']}")
        print(f"Result: {r['result']}")
        print(f"Verified: {r['verified']}")
```

---

### 2. Contradiction Detection 🔍

Semantic analysis to detect contradictions between sources using GPT-4o-mini.

**How it works:**
1. Compares sources pairwise
2. Uses AI to identify semantic contradictions
3. Classifies severity (high/medium/low)
4. Reduces confidence score based on contradictions

**Example:**
```python
sources = [
    {
        "url": "https://source1.com/article",
        "content": "The event occurred in 1945."
    },
    {
        "url": "https://source2.com/article",
        "content": "The event took place in 1947."
    }
]

result = await fact_checker_service.verify_claim(
    claim="When did the event occur?",
    task_id=task_id,
    user_id=user_id,
    sources=sources
)

# Check for contradictions
if result.sources_contradicting > 0:
    print(f"Found {result.sources_contradicting} contradictions")
    contradictions = result.contradicting_evidence
    for c in contradictions:
        print(f"{c['source_a']} vs {c['source_b']}")
        print(f"Severity: {c['severity']}")
        print(f"Description: {c['description']}")
```

---

### 3. Weighted Confidence Scoring ⚖️

Advanced confidence calculation that weights sources by their reliability.

**Factors:**
- **Source Quality**: Academic sources (95), Government (90), News agencies (85)
- **Source Count**: Bonus for 5+ sources (+10), penalty for <3 sources (-10)
- **Contradictions**: High severity (-20), medium (-10), low (-5)
- **Wolfram Verification**: 30% weight if numeric claims present

**Confidence Thresholds:**
- **≥85%**: Verified (strong evidence)
- **≥70%**: Likely (good evidence)
- **≥50%**: Uncertain (mixed evidence)
- **≥30%**: Unlikely (contradictory evidence)
- **<30%**: Unverified (insufficient or poor evidence)

**Example:**
```python
# High-quality sources get higher weight
sources = [
    {"url": "https://nature.com/article", "quality": 95},      # Weight: 0.95
    {"url": "https://wikipedia.org/article", "quality": 75},   # Weight: 0.75
    {"url": "https://random-blog.com/post", "quality": 40}     # Weight: 0.40
]

# Confidence = weighted average quality + bonuses - penalties
# = (95*0.95 + 75*0.75 + 40*0.40) / (0.95+0.75+0.40) + source_bonus - contradiction_penalty
```

---

### 4. Enhanced Source Reliability Database 📊

Expanded source quality ratings with 40+ predefined sources:

**Academic & Scientific (90-95):**
- Nature, Science, PubMed, IEEE, ScienceDirect, arXiv

**News Agencies (85-90):**
- Reuters, AP News, BBC, NPR, The Guardian

**Government & Official (90-95):**
- CDC, NIH, NASA, .gov domains

**Educational (85-92):**
- Stanford, MIT, Harvard, .edu domains

**Financial (85):**
- Bloomberg, Wall Street Journal, Financial Times

**Reference (75-88):**
- Britannica, Wikipedia

---

## API Changes

### FactCheckResult Schema (Enhanced)

```python
{
    "id": "uuid",
    "task_id": "uuid",
    "user_id": "uuid",
    "claim": "string",
    "verification_status": "verified|likely|uncertain|unlikely|unverified",
    "confidence_score": 85.5,  # 0-100
    "sources_checked": 5,
    "sources_supporting": 4,
    "sources_contradicting": 1,  # NEW: Count of contradicting sources
    "source_quality_avg": 82.0,
    "supporting_evidence": [...],
    "contradicting_evidence": [    # NEW: Contradiction details
        {
            "source_a": "url1",
            "source_b": "url2",
            "description": "Date discrepancy",
            "severity": "high"
        }
    ],
    "verification_method": "multi_source",
    "verification_details": {
        "statements_checked": 3,
        "source_breakdown": [...],
        "contradictions_detected": 1,  # NEW
        "confidence_calculation": "weighted_by_source_reliability",  # NEW
        "wolfram_results": [           # NEW: Wolfram Alpha verification
            {
                "query": "population of US",
                "result": "331 million",
                "verified": true,
                "source": "Wolfram Alpha"
            }
        ],
        "wolfram_confidence": 95.0     # NEW
    },
    "requires_attention": false,
    "alert_reason": null,
    "checked_at": "2026-03-01T10:30:00Z"
}
```

---

## Test Coverage

**Total Tests**: 50+  
**Coverage Target**: 95%+

### Test Categories:

1. **Wolfram Alpha Integration (8 tests)**
   - Expression extraction
   - Confidence calculation
   - Success/failure handling
   - Population/distance queries

2. **Contradiction Detection (6 tests)**
   - Pairwise comparison
   - Severity classification
   - OpenAI integration
   - Empty content handling

3. **Weighted Confidence (6 tests)**
   - High-quality sources
   - Mixed quality
   - Contradiction penalties
   - Source count bonuses

4. **Enhanced Source Assessment (8 tests)**
   - Academic sources
   - Government sources
   - News agencies
   - Educational institutions

5. **Backward Compatibility (22 tests)**
   - All existing functionality maintained

### Run Tests:

```bash
cd backend

# Run all fact checker tests
pytest tests/services/test_fact_checker.py -v

# Run only v2 feature tests
pytest tests/services/test_fact_checker.py -v -k "Wolfram or Contradiction or Weighted or Enhanced"

# Check coverage
pytest tests/services/test_fact_checker.py --cov=app.services.fact_checker --cov-report=html
```

---

## Performance Considerations

### Wolfram Alpha
- **Rate Limits**: 2,000 queries/month (free tier)
- **Optimization**: Only queries numeric claims
- **Caching**: Consider caching common queries
- **Timeout**: 5 seconds per query

### Contradiction Detection
- **OpenAI Costs**: ~$0.0001 per comparison (GPT-4o-mini)
- **Optimization**: Limits to 5 contradictions max
- **Pairwise Complexity**: O(n²) - consider limiting for large source sets
- **Token Usage**: ~200 tokens per comparison

### Recommendations:
1. Enable Wolfram Alpha for high-stakes claims only
2. Limit source count to 10-15 for contradiction detection
3. Cache source quality ratings in database
4. Use Redis for Wolfram query caching

---

## Configuration

### Environment Variables:

```bash
# Wolfram Alpha (optional)
WOLFRAM_APP_ID=your_app_id

# OpenAI (required for contradiction detection)
OPENAI_API_KEY=your_openai_key
```

### Feature Flags:

```python
# In your agent configuration
fact_checker_config = {
    "enable_wolfram": True,           # Enable Wolfram Alpha verification
    "enable_contradiction": True,     # Enable contradiction detection
    "weighted_confidence": True,      # Use weighted scoring (always on in v2)
    "max_sources": 15,                # Limit sources for performance
    "max_contradictions": 5,          # Limit contradiction checks
}
```

---

## Migration Notes

### From v1 to v2:

1. **Database**: No schema changes required (backward compatible)
2. **API**: All v1 endpoints work unchanged
3. **New Fields**: `contradicting_evidence`, `wolfram_results` added to details
4. **Dependencies**: Add `wolframalpha==5.0.0` to requirements.txt

### Breaking Changes:

**None** - Fully backward compatible. V2 features enhance existing functionality without breaking changes.

---

## Examples

### Complete Fact Check Flow:

```python
from app.services.fact_checker import FactCheckerService
from sqlalchemy.ext.asyncio import AsyncSession

async def comprehensive_fact_check(db: AsyncSession):
    fact_checker = FactCheckerService(db)
    
    # Claim with numeric data and multiple sources
    claim = """
    The James Webb Space Telescope launched on December 25, 2021.
    It cost approximately $10 billion to develop.
    The telescope operates at a distance of 1.5 million km from Earth.
    """
    
    sources = [
        {
            "url": "https://nasa.gov/webb",
            "title": "James Webb Space Telescope - NASA",
            "content": "JWST launched Dec 25, 2021. Cost ~$10B. Located at L2, 1.5M km from Earth."
        },
        {
            "url": "https://nature.com/articles/jwst-launch",
            "title": "Webb Telescope Launch - Nature",
            "content": "The $10 billion telescope launched Christmas Day 2021."
        },
        {
            "url": "https://space.com/jwst",
            "title": "JWST Facts - Space.com",
            "content": "Launched December 25, 2021 to L2 point, 1.5 million kilometers away."
        }
    ]
    
    result = await fact_checker.verify_claim(
        claim=claim,
        task_id="task-123",
        user_id="user-456",
        sources=sources
    )
    
    print(f"Status: {result.verification_status}")
    print(f"Confidence: {result.confidence_score}%")
    print(f"Sources checked: {result.sources_checked}")
    print(f"Contradictions: {result.sources_contradicting}")
    
    # Check Wolfram results
    if result.verification_details and "wolfram_results" in result.verification_details:
        print("\nWolfram Alpha Verification:")
        for wr in result.verification_details["wolfram_results"]:
            if wr["verified"]:
                print(f"  ✓ {wr['query']}: {wr['result']}")
    
    # Check contradictions
    if result.contradicting_evidence:
        print("\nContradictions Found:")
        for c in result.contradicting_evidence:
            print(f"  ⚠ {c['severity']}: {c['description']}")
    
    return result
```

---

## Troubleshooting

### Wolfram Alpha Not Working:

```bash
# Check if WOLFRAM_APP_ID is set
echo $WOLFRAM_APP_ID

# Test Wolfram Alpha API
python -c "import wolframalpha; client = wolframalpha.Client('YOUR_APP_ID'); print(client.query('2+2'))"
```

### Contradiction Detection Slow:

Reduce max sources or max contradictions:
```python
# In fact_checker.py, adjust limits
for i, source_a in enumerate(source_analyses):
    for source_b in source_analyses[i+1:i+4]:  # Limit to 3 comparisons per source
        ...
```

### Low Confidence Scores:

Check source quality in logs:
```python
logger.info(f"Source {url}: quality={quality}, weight={weight}")
```

---

## Future Enhancements

- [ ] Knowledge graph integration
- [ ] Time-based fact decay (older facts get lower confidence)
- [ ] User reputation system (trusted users boost confidence)
- [ ] Machine learning model for claim classification
- [ ] Real-time fact checking dashboard
- [ ] Batch processing for multiple claims

---

## References

- [Wolfram Alpha API Documentation](https://products.wolframalpha.com/api/)
- [OpenAI GPT-4o-mini Pricing](https://openai.com/pricing)
- [Source Quality Research Paper](https://www.nature.com/articles/s41586-021-03344-2)

---

**Last Updated**: 2026-03-01  
**Implemented By**: SuperAgent Dev (Sprint 10)  
**Status**: ✅ Production Ready
