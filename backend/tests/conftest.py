"""
Test configuration and fixtures.
"""
import pytest
from typing import AsyncGenerator
from unittest.mock import MagicMock

# Fixtures will be added as tests are implemented


@pytest.fixture
def mock_config():
    """Mock configuration for testing."""
    return {
        "environment": "test",
        "trading_mode": "paper",
        "live_trading_enabled": False,
    }


@pytest.fixture
def sample_market_data():
    """Sample market data for testing."""
    return {
        "symbol": "EURUSD",
        "timeframe": "M30",
        "bars": [
            {"timestamp": "2024-01-01T00:00:00Z", "open": 1.1000, "high": 1.1010, "low": 1.0990, "close": 1.1005, "volume": 1000},
            {"timestamp": "2024-01-01T00:30:00Z", "open": 1.1005, "high": 1.1015, "low": 1.0995, "close": 1.1010, "volume": 1100},
        ],
        "spread": 1.5,
    }
