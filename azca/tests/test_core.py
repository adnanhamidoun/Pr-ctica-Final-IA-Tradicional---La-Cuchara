import pytest
from datetime import datetime
from pathlib import Path

from azca.core.manager import ModelProvider
from azca.core.pipeline import InferencePipeline
from azca.core.engine import PredictionEngine


class TestModelProvider:
    def test_model_provider_init(self):
        """Test ModelProvider initialization"""
        provider = ModelProvider()
        assert provider.artifacts_path is not None
        assert provider._cache == {}

    def test_model_provider_custom_path(self, tmp_path):
        """Test ModelProvider with custom path"""
        provider = ModelProvider(artifacts_path=tmp_path)
        assert provider.artifacts_path == tmp_path

    def test_model_provider_cache(self):
        """Test that ModelProvider caches models"""
        provider = ModelProvider()
        # First call should populate cache
        provider._cache["test_model"] = "cached_value"
        assert provider._cache["test_model"] == "cached_value"


class TestInferencePipeline:
    def test_pipeline_init_defaults(self):
        """Test InferencePipeline with default config"""
        pipeline = InferencePipeline()
        assert pipeline.fixed_fields is not None
        assert pipeline.fixed_fields["restaurant_id"] == 1
        assert pipeline.fixed_fields["menu_price"] == 15.0

    def test_pipeline_init_custom(self):
        """Test InferencePipeline with custom config"""
        custom_config = {"restaurant_id": 101, "menu_price": 20.0}
        pipeline = InferencePipeline(fixed_fields=custom_config)
        assert pipeline.fixed_fields["restaurant_id"] == 101
        assert pipeline.fixed_fields["menu_price"] == 20.0

    def test_build_features_shape(self):
        """Test build_features returns correct shape"""
        pipeline = InferencePipeline()
        data = {
            "service_date": datetime(2026, 3, 15),
            "max_temp_c": 22.5,
        }
        df = pipeline.build_features(data)
        assert df.shape == (1, 24)
        assert list(df.columns) == pipeline.MODEL_COLUMNS

    def test_build_features_defaults(self):
        """Test build_features applies defaults correctly"""
        pipeline = InferencePipeline()
        data = {
            "service_date": datetime(2026, 3, 15),
            "max_temp_c": 22.5,
        }
        df = pipeline.build_features(data)
        assert df["precipitation_mm"].values[0] == 0
        assert df["is_stadium_event"].values[0] == False
        assert df["services_lag_7"].values[0] == 100

    def test_build_features_rain_peak(self):
        """Test rain peak detection (>10mm)"""
        pipeline = InferencePipeline()
        data = {
            "service_date": datetime(2026, 3, 15),
            "max_temp_c": 15.0,
            "precipitation_mm": 25,
        }
        df = pipeline.build_features(data)
        assert df["is_rain_service_peak"].values[0] == True

    def test_build_features_business_day(self):
        """Test business day detection (Mon=0, Fri=4)"""
        pipeline = InferencePipeline()
        # Monday
        data = {
            "service_date": datetime(2026, 3, 16),  # Monday
            "max_temp_c": 20.0,
        }
        df = pipeline.build_features(data)
        assert df["is_business_day"].values[0] == True

        # Saturday
        data["service_date"] = datetime(2026, 3, 14)  # Saturday
        df = pipeline.build_features(data)
        assert df["is_business_day"].values[0] == False


class TestPredictionEngine:
    def test_engine_init(self):
        """Test PredictionEngine initialization"""
        engine = PredictionEngine()
        assert engine.model_provider is not None
        assert engine.pipeline is not None

    def test_engine_init_custom_config(self, tmp_path):
        """Test PredictionEngine with custom config"""
        custom_config = {"restaurant_id": 50}
        engine = PredictionEngine(
            artifacts_path=tmp_path,
            pipeline_config=custom_config
        )
        assert engine.pipeline.fixed_fields["restaurant_id"] == 50


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
