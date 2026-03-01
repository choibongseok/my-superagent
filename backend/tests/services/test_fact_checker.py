"""Tests for fact checking service."""

import pytest
from datetime import datetime
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.fact_checker import FactCheckerService
from app.models.fact_check import FactCheckResult, SourceQuality, VerificationRule


@pytest.fixture
def mock_db():
    """Create mock async database session."""
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.execute = AsyncMock()
    return db


@pytest.fixture
def fact_checker_service(mock_db):
    """Create FactCheckerService instance with mock database."""
    return FactCheckerService(db=mock_db)


@pytest.fixture
def sample_task_id():
    """Generate sample task ID."""
    return str(uuid4())


@pytest.fixture
def sample_user_id():
    """Generate sample user ID."""
    return str(uuid4())


class TestFactCheckerService:
    """Test FactCheckerService class."""

    def test_initialization(self, fact_checker_service):
        """Test service initialization."""
        assert fact_checker_service is not None
        assert hasattr(fact_checker_service, "knowledge_sources")
        assert "wikipedia.org" in fact_checker_service.knowledge_sources
        assert fact_checker_service.knowledge_sources["wikipedia.org"] == 75

    @pytest.mark.asyncio
    async def test_verify_claim_no_sources(
        self, fact_checker_service, mock_db, sample_task_id, sample_user_id
    ):
        """Test claim verification with no sources provided."""
        claim = "The Earth revolves around the Sun."

        result = await fact_checker_service.verify_claim(
            claim=claim, task_id=sample_task_id, user_id=sample_user_id, sources=None
        )

        # Verify database interactions
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()
        mock_db.refresh.assert_called_once()

        # Check that FactCheckResult was created with expected values
        added_fact_check = mock_db.add.call_args[0][0]
        assert isinstance(added_fact_check, FactCheckResult)
        assert added_fact_check.claim == claim
        assert added_fact_check.task_id == sample_task_id
        assert added_fact_check.user_id == sample_user_id
        assert added_fact_check.verification_status == "unverified"
        assert added_fact_check.confidence_score == 0.0
        assert added_fact_check.sources_checked == 0
        assert added_fact_check.requires_attention is True
        assert added_fact_check.alert_reason == "no_sources"

    @pytest.mark.asyncio
    async def test_verify_claim_with_high_quality_sources(
        self, fact_checker_service, mock_db, sample_task_id, sample_user_id
    ):
        """Test claim verification with high-quality sources."""
        claim = "Water boils at 100 degrees Celsius at sea level."
        sources = [
            {
                "url": "https://wikipedia.org/wiki/Boiling_point",
                "title": "Boiling Point - Wikipedia",
                "content": "Water boils at 100°C at sea level atmospheric pressure."
            },
            {
                "url": "https://www.nature.com/articles/water-properties",
                "title": "Properties of Water - Nature",
                "content": "The boiling point of water is 100 degrees Celsius."
            },
            {
                "url": "https://britannica.com/science/boiling-point",
                "title": "Boiling Point - Britannica",
                "content": "Water's boiling point at standard pressure is 100°C."
            },
        ]

        # Mock _assess_source_quality to return high quality scores
        with patch.object(
            fact_checker_service, "_assess_source_quality", return_value=85.0
        ), patch.object(
            fact_checker_service, "_detect_contradictions", return_value=[]
        ):
            result = await fact_checker_service.verify_claim(
                claim=claim,
                task_id=sample_task_id,
                user_id=sample_user_id,
                sources=sources,
            )

        # Check that FactCheckResult was created with verified status
        added_fact_check = mock_db.add.call_args[0][0]
        assert isinstance(added_fact_check, FactCheckResult)
        assert added_fact_check.verification_status == "verified"
        assert added_fact_check.confidence_score >= 80.0
        assert added_fact_check.sources_checked == 3
        assert added_fact_check.sources_supporting == 3
        assert added_fact_check.requires_attention is False

    @pytest.mark.asyncio
    async def test_verify_claim_with_low_quality_sources(
        self, fact_checker_service, mock_db, sample_task_id, sample_user_id
    ):
        """Test claim verification with low-quality sources."""
        claim = "Aliens visited Earth in 1947."
        sources = [
            {"url": "https://random-blog.com/aliens", "title": "Alien Conspiracy", "content": "Aliens came."},
            {
                "url": "https://unknown-site.net/ufo",
                "title": "UFO Sightings",
                "content": "UFOs were seen."
            },
        ]

        # Mock _assess_source_quality to return low quality scores
        with patch.object(
            fact_checker_service, "_assess_source_quality", return_value=30.0
        ), patch.object(
            fact_checker_service, "_detect_contradictions", return_value=[]
        ):
            result = await fact_checker_service.verify_claim(
                claim=claim,
                task_id=sample_task_id,
                user_id=sample_user_id,
                sources=sources,
            )

        # Check that FactCheckResult shows low confidence
        added_fact_check = mock_db.add.call_args[0][0]
        assert isinstance(added_fact_check, FactCheckResult)
        assert added_fact_check.verification_status in [
            "insufficient_data",
            "unverified",
            "uncertain",
            "unlikely"
        ]
        assert added_fact_check.confidence_score < 70.0
        assert added_fact_check.requires_attention is True
        assert "low_confidence" in added_fact_check.alert_reason or "insufficient_sources" in added_fact_check.alert_reason

    @pytest.mark.asyncio
    async def test_verify_claim_with_numeric_data(
        self, fact_checker_service, mock_db, sample_task_id, sample_user_id
    ):
        """Test claim verification with numeric data."""
        claim = "The global temperature has increased by 1.2°C since 1900. This represents a 25% increase in atmospheric CO2."
        sources = [
            {"url": "https://www.nature.com/climate", "title": "Climate Data", "content": "Temperature increased 1.2°C."},
        ]

        with patch.object(
            fact_checker_service, "_assess_source_quality", return_value=95.0
        ), patch.object(
            fact_checker_service, "_detect_contradictions", return_value=[]
        ), patch.object(
            fact_checker_service, "_verify_with_wolfram", return_value=[]
        ):
            result = await fact_checker_service.verify_claim(
                claim=claim,
                task_id=sample_task_id,
                user_id=sample_user_id,
                sources=sources,
            )

        # Verify numeric claim detection
        assert fact_checker_service._contains_numeric_claim(claim) is True

        added_fact_check = mock_db.add.call_args[0][0]
        assert isinstance(added_fact_check, FactCheckResult)

    @pytest.mark.asyncio
    async def test_assess_source_quality_known_source(
        self, fact_checker_service, mock_db
    ):
        """Test source quality assessment for known sources."""
        # Set up mock result
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        
        # Make execute return the mock result (not a coroutine)
        mock_db.execute = AsyncMock(return_value=mock_result)

        # Wikipedia should have known quality
        quality = await fact_checker_service._assess_source_quality(
            "https://en.wikipedia.org/wiki/Test"
        )
        assert quality == 75.0

        # Nature should have high quality
        quality = await fact_checker_service._assess_source_quality(
            "https://www.nature.com/articles/test"
        )
        assert quality == 95.0

    @pytest.mark.asyncio
    async def test_assess_source_quality_unknown_source(
        self, fact_checker_service, mock_db
    ):
        """Test source quality assessment for unknown sources."""
        # Set up mock result
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        
        # Make execute return the mock result (not a coroutine)
        mock_db.execute = AsyncMock(return_value=mock_result)

        # .edu domain should get higher quality
        quality = await fact_checker_service._assess_source_quality(
            "https://university.edu/research"
        )
        assert quality == 85.0

        # .com domain should get medium quality
        quality = await fact_checker_service._assess_source_quality(
            "https://random-site.com/article"
        )
        assert quality == 50.0

    @pytest.mark.asyncio
    async def test_assess_source_quality_from_database(
        self, fact_checker_service, mock_db
    ):
        """Test source quality retrieved from database."""
        # Create a mock object with the reliability_score attribute
        mock_source_quality = MagicMock()
        mock_source_quality.reliability_score = 92.0
        mock_source_quality.domain = "trusted-news.com"

        # Set up mock result
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_source_quality
        
        # Make execute return the mock result (not a coroutine)
        mock_db.execute = AsyncMock(return_value=mock_result)

        quality = await fact_checker_service._assess_source_quality(
            "https://www.trusted-news.com/article"
        )
        assert quality == 92.0

    def test_extract_statements(self, fact_checker_service):
        """Test factual statement extraction."""
        text = "The Earth is round. Water is wet. The sky is blue. This is true. Test."

        statements = fact_checker_service._extract_statements(text)

        assert isinstance(statements, list)
        assert len(statements) <= 5  # Should limit to 5
        assert "The Earth is round" in statements
        assert "Water is wet" in statements

    def test_extract_statements_empty(self, fact_checker_service):
        """Test statement extraction with empty text."""
        statements = fact_checker_service._extract_statements("")
        assert statements == []

    def test_contains_numeric_claim_percentage(self, fact_checker_service):
        """Test numeric claim detection with percentages."""
        assert (
            fact_checker_service._contains_numeric_claim(
                "Sales increased by 25% last year."
            )
            is True
        )

    def test_contains_numeric_claim_currency(self, fact_checker_service):
        """Test numeric claim detection with currency."""
        assert (
            fact_checker_service._contains_numeric_claim("The price is $500.")
            is True
        )

    def test_contains_numeric_claim_year(self, fact_checker_service):
        """Test numeric claim detection with years."""
        assert (
            fact_checker_service._contains_numeric_claim(
                "This happened in 2020."
            )
            is True
        )

    def test_contains_numeric_claim_large_numbers(self, fact_checker_service):
        """Test numeric claim detection with large numbers."""
        assert (
            fact_checker_service._contains_numeric_claim(
                "The population is 5 million."
            )
            is True
        )
        assert (
            fact_checker_service._contains_numeric_claim(
                "Revenue reached 2 billion dollars."
            )
            is True
        )

    def test_contains_numeric_claim_no_numbers(self, fact_checker_service):
        """Test numeric claim detection with no numbers."""
        assert (
            fact_checker_service._contains_numeric_claim(
                "This is just text without numbers."
            )
            is False
        )

    @pytest.mark.asyncio
    async def test_get_task_fact_checks(
        self, fact_checker_service, mock_db, sample_task_id
    ):
        """Test retrieving fact checks for a task."""
        # Create mock fact check objects
        fact_check_1 = MagicMock()
        fact_check_1.id = uuid4()
        fact_check_1.task_id = sample_task_id
        fact_check_1.user_id = uuid4()
        fact_check_1.claim = "Test claim 1"
        fact_check_1.verification_status = "verified"
        fact_check_1.confidence_score = 85.0

        fact_check_2 = MagicMock()
        fact_check_2.id = uuid4()
        fact_check_2.task_id = sample_task_id
        fact_check_2.user_id = uuid4()
        fact_check_2.claim = "Test claim 2"
        fact_check_2.verification_status = "unverified"
        fact_check_2.confidence_score = 45.0

        # Set up mock scalars
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [fact_check_1, fact_check_2]
        
        # Set up mock result
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        
        # Make execute return the mock result (not a coroutine)
        mock_db.execute = AsyncMock(return_value=mock_result)

        # Get all fact checks
        fact_checks = await fact_checker_service.get_task_fact_checks(sample_task_id)

        assert len(fact_checks) == 2
        assert fact_checks[0].task_id == sample_task_id
        assert fact_checks[1].task_id == sample_task_id

    @pytest.mark.asyncio
    async def test_get_task_fact_checks_with_min_confidence(
        self, fact_checker_service, mock_db, sample_task_id
    ):
        """Test retrieving fact checks with minimum confidence filter."""
        # Create mock fact check with high confidence
        fact_check_high = MagicMock()
        fact_check_high.id = uuid4()
        fact_check_high.task_id = sample_task_id
        fact_check_high.user_id = uuid4()
        fact_check_high.claim = "High confidence claim"
        fact_check_high.verification_status = "verified"
        fact_check_high.confidence_score = 90.0

        # Set up mock scalars
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [fact_check_high]
        
        # Set up mock result
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        
        # Make execute return the mock result (not a coroutine)
        mock_db.execute = AsyncMock(return_value=mock_result)

        # Get fact checks with min confidence 80
        fact_checks = await fact_checker_service.get_task_fact_checks(
            sample_task_id, min_confidence=80.0
        )

        assert len(fact_checks) == 1
        assert fact_checks[0].confidence_score >= 80.0

    @pytest.mark.asyncio
    async def test_get_verification_rule(self, fact_checker_service, mock_db):
        """Test retrieving a verification rule."""
        # Create mock verification rule
        rule = MagicMock()
        rule.id = uuid4()
        rule.rule_name = "high_stakes_claim"
        rule.rule_type = "claim_type"
        rule.min_confidence_threshold = 85.0
        rule.min_sources_required = 5
        rule.min_source_quality = 70.0
        rule.auto_verify = False
        rule.alert_on_low_confidence = True
        rule.block_on_contradiction = True
        rule.enabled = True

        # Set up mock result
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = rule
        
        # Make execute return the mock result (not a coroutine)
        mock_db.execute = AsyncMock(return_value=mock_result)

        retrieved_rule = await fact_checker_service.get_verification_rule(
            "high_stakes_claim"
        )

        assert retrieved_rule is not None
        assert retrieved_rule.rule_name == "high_stakes_claim"
        assert retrieved_rule.min_confidence_threshold == 85.0

    @pytest.mark.asyncio
    async def test_get_verification_rule_not_found(
        self, fact_checker_service, mock_db
    ):
        """Test retrieving a non-existent verification rule."""
        # Set up mock result
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        
        # Make execute return the mock result (not a coroutine)
        mock_db.execute = AsyncMock(return_value=mock_result)

        retrieved_rule = await fact_checker_service.get_verification_rule(
            "nonexistent_rule"
        )

        assert retrieved_rule is None

    @pytest.mark.asyncio
    async def test_create_source_quality_rating(self, fact_checker_service, mock_db):
        """Test creating a new source quality rating."""
        # Mock the refresh to avoid database access
        mock_db.refresh.return_value = None
        
        source_quality = await fact_checker_service.create_source_quality_rating(
            domain="new-reliable-source.com",
            source_type="news",
            reliability_score=88.0,
            factual_accuracy=92.0,
            bias_score=-5.0,
        )

        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()
        mock_db.refresh.assert_called_once()

        added_source = mock_db.add.call_args[0][0]
        assert isinstance(added_source, SourceQuality)
        assert added_source.domain == "new-reliable-source.com"
        assert added_source.reliability_score == 88.0

    @pytest.mark.asyncio
    async def test_verify_with_sources_empty_list(self, fact_checker_service):
        """Test verification with empty source list."""
        statements = ["Test statement"]
        sources = []

        result = await fact_checker_service._verify_with_sources(statements, sources)

        assert result["status"] == "unverified"
        assert result["confidence"] == 0.0
        assert result["sources_checked"] == 0
        assert result["alert_reason"] == "no_sources"

    @pytest.mark.asyncio
    async def test_verify_with_sources_insufficient_sources(
        self, fact_checker_service
    ):
        """Test verification with fewer than 3 sources."""
        statements = ["Test statement"]
        sources = [
            {"url": "https://example.com/article1", "title": "Article 1", "content": "Test content"},
            {"url": "https://example.com/article2", "title": "Article 2", "content": "Test content"},
        ]

        with patch.object(
            fact_checker_service, "_assess_source_quality", return_value=70.0
        ), patch.object(
            fact_checker_service, "_detect_contradictions", return_value=[]
        ):
            result = await fact_checker_service._verify_with_sources(
                statements, sources
            )

        assert result["sources_checked"] == 2
        assert "insufficient_sources" in result["alert_reason"]

    @pytest.mark.asyncio
    async def test_verify_with_sources_high_confidence(self, fact_checker_service):
        """Test verification resulting in high confidence."""
        statements = ["Test statement"]
        sources = [
            {"url": "https://wikipedia.org/wiki/test", "title": "Test - Wikipedia", "content": "Test content"},
            {"url": "https://www.nature.com/articles/test", "title": "Test - Nature", "content": "Test content"},
            {
                "url": "https://britannica.com/topic/test",
                "title": "Test - Britannica",
                "content": "Test content"
            },
            {"url": "https://science.org/doi/test", "title": "Test - Science", "content": "Test content"},
        ]

        with patch.object(
            fact_checker_service, "_assess_source_quality", return_value=90.0
        ), patch.object(
            fact_checker_service, "_detect_contradictions", return_value=[]
        ):
            result = await fact_checker_service._verify_with_sources(
                statements, sources
            )

        assert result["status"] == "verified"
        assert result["confidence"] >= 80.0
        assert result["sources_checked"] == 4
        assert result["sources_supporting"] == 4

    @pytest.mark.asyncio
    async def test_assess_source_quality_error_handling(
        self, fact_checker_service, mock_db
    ):
        """Test source quality assessment with error."""
        # Mock database to raise an exception
        mock_db.execute.side_effect = Exception("Database error")

        quality = await fact_checker_service._assess_source_quality(
            "https://example.com"
        )

        # Should return default neutral score on error
        assert quality == 50.0


# ===== V2 FEATURES TESTS =====

class TestWolframAlphaIntegration:
    """Test Wolfram Alpha calculation verification (v2 feature)."""

    def test_extract_numeric_expressions_simple_math(self, fact_checker_service):
        """Test extracting simple mathematical expressions."""
        text = "The calculation 5 + 3 equals 8."
        expressions = fact_checker_service._extract_numeric_expressions(text)
        
        assert len(expressions) > 0
        assert any("5" in expr and "3" in expr for expr in expressions)

    def test_extract_numeric_expressions_population(self, fact_checker_service):
        """Test extracting population queries."""
        text = "The population of the United States is 331 million."
        expressions = fact_checker_service._extract_numeric_expressions(text)
        
        assert len(expressions) > 0
        assert any("population" in expr.lower() for expr in expressions)

    def test_extract_numeric_expressions_distance(self, fact_checker_service):
        """Test extracting distance queries."""
        text = "The distance from Earth to Moon is 384,400 km."
        expressions = fact_checker_service._extract_numeric_expressions(text)
        
        assert len(expressions) > 0
        assert any("distance" in expr.lower() for expr in expressions)

    def test_calculate_wolfram_confidence_verified(self, fact_checker_service):
        """Test Wolfram confidence calculation with verified results."""
        wolfram_results = [
            {"query": "5+3", "result": "8", "verified": True, "source": "Wolfram Alpha"},
            {"query": "10*2", "result": "20", "verified": True, "source": "Wolfram Alpha"}
        ]
        
        confidence = fact_checker_service._calculate_wolfram_confidence(wolfram_results)
        
        assert confidence > 0
        assert confidence <= 100.0
        # Should be high confidence since both verified
        assert confidence >= 90.0

    def test_calculate_wolfram_confidence_partial(self, fact_checker_service):
        """Test Wolfram confidence with partial verification."""
        wolfram_results = [
            {"query": "5+3", "result": "8", "verified": True, "source": "Wolfram Alpha"},
            {"query": "unknown", "result": None, "verified": False, "error": "Query not understood"}
        ]
        
        confidence = fact_checker_service._calculate_wolfram_confidence(wolfram_results)
        
        assert confidence > 0
        assert confidence < 100.0
        # Should be medium confidence (50%)
        assert 40.0 <= confidence <= 70.0

    def test_calculate_wolfram_confidence_none_verified(self, fact_checker_service):
        """Test Wolfram confidence with no verified results."""
        wolfram_results = [
            {"query": "unknown", "result": None, "verified": False, "error": "Error"}
        ]
        
        confidence = fact_checker_service._calculate_wolfram_confidence(wolfram_results)
        
        assert confidence == 0.0

    def test_calculate_wolfram_confidence_empty(self, fact_checker_service):
        """Test Wolfram confidence with empty results."""
        confidence = fact_checker_service._calculate_wolfram_confidence([])
        assert confidence == 0.0

    @pytest.mark.asyncio
    async def test_verify_with_wolfram_no_client(self, fact_checker_service):
        """Test Wolfram verification when client is not initialized."""
        fact_checker_service.wolfram_client = None
        
        results = await fact_checker_service._verify_with_wolfram("5 + 3 = 8")
        
        assert results == []

    @pytest.mark.asyncio
    async def test_verify_with_wolfram_success(self, fact_checker_service):
        """Test successful Wolfram verification."""
        # Mock Wolfram client
        mock_wolfram = MagicMock()
        mock_response = {
            '@success': 'true',
            'pod': [
                {
                    '@id': 'Result',
                    'subpod': {
                        'plaintext': '8'
                    }
                }
            ]
        }
        mock_wolfram.query.return_value = mock_response
        fact_checker_service.wolfram_client = mock_wolfram
        
        results = await fact_checker_service._verify_with_wolfram("5 + 3")
        
        assert len(results) > 0
        assert results[0]['verified'] is True
        assert results[0]['result'] == '8'

    @pytest.mark.asyncio
    async def test_verify_with_wolfram_failure(self, fact_checker_service):
        """Test Wolfram verification failure."""
        # Mock Wolfram client with failed response
        mock_wolfram = MagicMock()
        mock_response = {'@success': 'false'}
        mock_wolfram.query.return_value = mock_response
        fact_checker_service.wolfram_client = mock_wolfram
        
        results = await fact_checker_service._verify_with_wolfram("What is 2+2?")
        
        assert len(results) > 0
        assert results[0]['verified'] is False
        assert 'error' in results[0]


class TestContradictionDetection:
    """Test contradiction detection between sources (v2 feature)."""

    @pytest.mark.asyncio
    async def test_detect_contradictions_no_openai(self, fact_checker_service):
        """Test contradiction detection without OpenAI client."""
        fact_checker_service.openai_client = None
        
        source_analyses = [
            {"url": "source1.com", "quality": 80, "content": "Content 1", "reliability_weight": 0.8},
            {"url": "source2.com", "quality": 85, "content": "Content 2", "reliability_weight": 0.85}
        ]
        statements = ["Test statement"]
        
        contradictions = await fact_checker_service._detect_contradictions(
            source_analyses, statements
        )
        
        assert contradictions == []

    @pytest.mark.asyncio
    async def test_detect_contradictions_single_source(self, fact_checker_service):
        """Test contradiction detection with single source."""
        source_analyses = [
            {"url": "source1.com", "quality": 80, "content": "Content 1", "reliability_weight": 0.8}
        ]
        statements = ["Test statement"]
        
        contradictions = await fact_checker_service._detect_contradictions(
            source_analyses, statements
        )
        
        # Should return empty - need at least 2 sources
        assert contradictions == []

    @pytest.mark.asyncio
    async def test_check_contradiction_pair_no_openai(self, fact_checker_service):
        """Test contradiction pair check without OpenAI."""
        fact_checker_service.openai_client = None
        
        source_a = {"url": "source1.com", "content": "Content A"}
        source_b = {"url": "source2.com", "content": "Content B"}
        statements = ["Test"]
        
        result = await fact_checker_service._check_contradiction_pair(
            source_a, source_b, statements
        )
        
        assert result is None

    @pytest.mark.asyncio
    async def test_check_contradiction_pair_empty_content(self, fact_checker_service):
        """Test contradiction check with empty content."""
        # Mock OpenAI client
        fact_checker_service.openai_client = MagicMock()
        
        source_a = {"url": "source1.com", "content": ""}
        source_b = {"url": "source2.com", "content": ""}
        statements = ["Test"]
        
        result = await fact_checker_service._check_contradiction_pair(
            source_a, source_b, statements
        )
        
        assert result is None

    @pytest.mark.asyncio
    async def test_check_contradiction_pair_with_contradiction(self, fact_checker_service):
        """Test detecting a contradiction between sources."""
        # Mock OpenAI client
        mock_openai = MagicMock()
        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_message = MagicMock()
        mock_message.content = '{"has_contradiction": true, "description": "Sources disagree on date", "severity": "high"}'
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]
        
        mock_openai.chat.completions.create = AsyncMock(return_value=mock_response)
        fact_checker_service.openai_client = mock_openai
        
        source_a = {"url": "source1.com", "content": "Event occurred in 1945"}
        source_b = {"url": "source2.com", "content": "Event occurred in 1947"}
        statements = ["Event date"]
        
        result = await fact_checker_service._check_contradiction_pair(
            source_a, source_b, statements
        )
        
        assert result is not None
        assert result["source_a"] == "source1.com"
        assert result["source_b"] == "source2.com"
        assert result["severity"] == "high"
        assert "description" in result


class TestWeightedConfidenceScoring:
    """Test weighted confidence scoring with source reliability (v2 feature)."""

    @pytest.mark.asyncio
    async def test_calculate_weighted_confidence_high_quality(self, fact_checker_service):
        """Test weighted confidence with high-quality sources."""
        source_analyses = [
            {"url": "nature.com", "quality": 95, "reliability_weight": 0.95},
            {"url": "science.org", "quality": 95, "reliability_weight": 0.95},
            {"url": "pubmed.gov", "quality": 95, "reliability_weight": 0.95},
            {"url": "mit.edu", "quality": 92, "reliability_weight": 0.92},
        ]
        contradictions = []
        
        confidence = await fact_checker_service._calculate_weighted_confidence(
            source_analyses, contradictions
        )
        
        # Should be very high confidence
        assert confidence >= 90.0
        assert confidence <= 100.0

    @pytest.mark.asyncio
    async def test_calculate_weighted_confidence_mixed_quality(self, fact_checker_service):
        """Test weighted confidence with mixed-quality sources."""
        source_analyses = [
            {"url": "nature.com", "quality": 95, "reliability_weight": 0.95},
            {"url": "random-blog.com", "quality": 40, "reliability_weight": 0.40},
            {"url": "news.com", "quality": 70, "reliability_weight": 0.70},
        ]
        contradictions = []
        
        confidence = await fact_checker_service._calculate_weighted_confidence(
            source_analyses, contradictions
        )
        
        # Should be medium-to-high confidence: weighted avg ~75.7 + 5 (3 sources) = ~80.7
        assert 50.0 <= confidence <= 85.0

    @pytest.mark.asyncio
    async def test_calculate_weighted_confidence_with_contradictions(self, fact_checker_service):
        """Test weighted confidence with contradictions."""
        source_analyses = [
            {"url": "source1.com", "quality": 80, "reliability_weight": 0.80},
            {"url": "source2.com", "quality": 80, "reliability_weight": 0.80},
            {"url": "source3.com", "quality": 80, "reliability_weight": 0.80},
        ]
        contradictions = [
            {"source_a": "source1.com", "source_b": "source2.com", "severity": "high"}
        ]
        
        confidence = await fact_checker_service._calculate_weighted_confidence(
            source_analyses, contradictions
        )
        
        # Should be significantly reduced due to high-severity contradiction
        assert confidence < 80.0

    @pytest.mark.asyncio
    async def test_calculate_weighted_confidence_multiple_contradictions(self, fact_checker_service):
        """Test weighted confidence with multiple contradictions."""
        source_analyses = [
            {"url": "source1.com", "quality": 85, "reliability_weight": 0.85},
            {"url": "source2.com", "quality": 85, "reliability_weight": 0.85},
        ]
        contradictions = [
            {"source_a": "source1.com", "source_b": "source2.com", "severity": "medium"},
            {"source_a": "source1.com", "source_b": "source2.com", "severity": "low"}
        ]
        
        confidence = await fact_checker_service._calculate_weighted_confidence(
            source_analyses, contradictions
        )
        
        # Should be reduced by multiple penalties
        assert confidence < 85.0

    @pytest.mark.asyncio
    async def test_calculate_weighted_confidence_empty_sources(self, fact_checker_service):
        """Test weighted confidence with no sources."""
        source_analyses = []
        contradictions = []
        
        confidence = await fact_checker_service._calculate_weighted_confidence(
            source_analyses, contradictions
        )
        
        assert confidence == 0.0

    @pytest.mark.asyncio
    async def test_calculate_weighted_confidence_bonus_for_many_sources(self, fact_checker_service):
        """Test confidence bonus for having many sources."""
        # Create 5+ sources for bonus
        source_analyses = [
            {"url": f"source{i}.com", "quality": 80, "reliability_weight": 0.80}
            for i in range(6)
        ]
        contradictions = []
        
        confidence = await fact_checker_service._calculate_weighted_confidence(
            source_analyses, contradictions
        )
        
        # Should get +10 bonus for 5+ sources
        assert confidence >= 85.0  # 80 base + bonus


class TestEnhancedSourceQualityAssessment:
    """Test enhanced source quality assessment (v2 feature)."""

    @pytest.mark.asyncio
    async def test_assess_academic_sources(self, fact_checker_service, mock_db):
        """Test assessment of academic sources."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        # Academic journals should have very high scores
        quality = await fact_checker_service._assess_source_quality(
            "https://www.nature.com/articles/test"
        )
        assert quality == 95.0

        quality = await fact_checker_service._assess_source_quality(
            "https://science.org/doi/test"
        )
        assert quality == 95.0

    @pytest.mark.asyncio
    async def test_assess_government_sources(self, fact_checker_service, mock_db):
        """Test assessment of government sources."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        quality = await fact_checker_service._assess_source_quality(
            "https://www.cdc.gov/health"
        )
        assert quality == 95.0

        quality = await fact_checker_service._assess_source_quality(
            "https://nasa.gov/mission"
        )
        assert quality == 95.0

    @pytest.mark.asyncio
    async def test_assess_news_agencies(self, fact_checker_service, mock_db):
        """Test assessment of news agencies."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        quality = await fact_checker_service._assess_source_quality(
            "https://reuters.com/article/test"
        )
        assert quality == 90.0

        quality = await fact_checker_service._assess_source_quality(
            "https://apnews.com/article/test"
        )
        assert quality == 90.0

    @pytest.mark.asyncio
    async def test_assess_educational_institutions(self, fact_checker_service, mock_db):
        """Test assessment of educational institutions."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        quality = await fact_checker_service._assess_source_quality(
            "https://stanford.edu/research/test"
        )
        assert quality == 92.0

        quality = await fact_checker_service._assess_source_quality(
            "https://mit.edu/lab/test"
        )
        assert quality == 92.0

    @pytest.mark.asyncio
    async def test_assess_generic_edu_domain(self, fact_checker_service, mock_db):
        """Test assessment of generic .edu domains."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        quality = await fact_checker_service._assess_source_quality(
            "https://unknown-university.edu/paper"
        )
        assert quality == 85.0

    @pytest.mark.asyncio
    async def test_assess_generic_gov_domain(self, fact_checker_service, mock_db):
        """Test assessment of generic .gov domains."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        quality = await fact_checker_service._assess_source_quality(
            "https://agency.gov/data"
        )
        assert quality == 90.0


class TestFactCheckResultModel:
    """Test FactCheckResult model."""

    def test_fact_check_result_creation(self):
        """Test creating a FactCheckResult instance."""
        # Note: This test verifies model structure, not actual database creation
        # which would require a full database setup
        task_id = uuid4()
        user_id = uuid4()

        # Simply verify that FactCheckResult class exists and has expected attributes
        assert hasattr(FactCheckResult, 'task_id')
        assert hasattr(FactCheckResult, 'user_id')
        assert hasattr(FactCheckResult, 'claim')
        assert hasattr(FactCheckResult, 'confidence_score')


class TestSourceQualityModel:
    """Test SourceQuality model."""

    def test_source_quality_creation(self):
        """Test creating a SourceQuality instance."""
        # Note: This test verifies model structure, not actual database creation
        assert hasattr(SourceQuality, 'domain')
        assert hasattr(SourceQuality, 'reliability_score')
        assert hasattr(SourceQuality, 'bias_score')


class TestVerificationRuleModel:
    """Test VerificationRule model."""

    def test_verification_rule_creation(self):
        """Test creating a VerificationRule instance."""
        # Note: This test verifies model structure, not actual database creation
        assert hasattr(VerificationRule, 'rule_name')
        assert hasattr(VerificationRule, 'min_confidence_threshold')
        assert hasattr(VerificationRule, 'enabled')
