import pandas as pd
from datetime import datetime
from pathlib import Path
from typing import Any


class InferencePipeline:
    # Column order expected by Azure AutoML model
    MODEL_COLUMNS = [
        "service_date",
        "restaurant_id",
        "max_temp_c",
        "precipitation_mm",
        "is_rain_service_peak",
        "is_stadium_event",
        "is_azca_event",
        "is_holiday",
        "is_bridge_day",
        "is_payday_week",
        "is_business_day",
        "services_lag_7",
        "avg_4_weeks",
        "capacity_limit",
        "table_count",
        "min_service_duration",
        "terrace_setup_type",
        "opens_weekends",
        "has_wifi",
        "restaurant_segment",
        "menu_price",
        "dist_office_towers",
        "google_rating",
        "cuisine_type",
    ]

    def __init__(self, fixed_fields: dict | None = None) -> None:
        """
        Initialize pipeline with optional fixed field overrides.

        Args:
            fixed_fields: dict with default values for restaurant fields.
                         If None, uses generic defaults.
        """
        # Set defaults
        self.fixed_fields = {
            "restaurant_id": 1,
            "capacity_limit": 100,
            "table_count": 20,
            "min_service_duration": 45,
            "terrace_setup_type": "standard",
            "opens_weekends": True,
            "has_wifi": True,
            "restaurant_segment": "casual",
            "menu_price": 15.0,
            "dist_office_towers": 500,
            "google_rating": 4.0,
            "cuisine_type": "mediterranean",
        }
        # Override with custom values if provided
        if fixed_fields:
            self.fixed_fields.update(fixed_fields)

    def build_features(self, data: dict) -> pd.DataFrame:
        """
        Transform basic input (date, temp, rain, stadium event, payday) 
        into the exact 24-column DataFrame required by the Azure AutoML model.

        Args:
            data: dict with required keys:
                - service_date: datetime
                - max_temp_c: float
                - precipitation_mm: float (default: 0)
                - is_stadium_event: bool (default: False)
                - is_payday_week: bool (default: False)
              optional:
                - is_azca_event: bool (default: False)
                - is_holiday: bool (default: False)
                - is_bridge_day: bool (default: False)
                - services_lag_7: int (default: 100)
                - avg_4_weeks: float (default: 100.0)

        Returns:
            pd.DataFrame with 24 columns in model-expected order
        """
        # Extract and validate required fields
        service_date = data["service_date"]
        max_temp_c = data["max_temp_c"]

        # Build the feature row
        row = {
            "service_date": service_date,
            "max_temp_c": max_temp_c,
            "precipitation_mm": data.get("precipitation_mm", 0),
            "is_rain_service_peak": data.get("precipitation_mm", 0) > 10,
            "is_stadium_event": data.get("is_stadium_event", False),
            "is_azca_event": data.get("is_azca_event", False),
            "is_holiday": data.get("is_holiday", False),
            "is_bridge_day": data.get("is_bridge_day", False),
            "is_payday_week": data.get("is_payday_week", False),
            "is_business_day": service_date.weekday() < 5,
            "services_lag_7": data.get("services_lag_7", 100),
            "avg_4_weeks": data.get("avg_4_weeks", 100.0),
        }

        # Merge with fixed fields (can be overridden per restaurant)
        row.update(self.fixed_fields)

        # Create DataFrame and select columns in model order
        df = pd.DataFrame([row])
        return df[self.MODEL_COLUMNS]
