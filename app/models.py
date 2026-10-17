from datetime import date
from typing import Optional

from pydantic import (
    BaseModel,
    Field,
    field_validator
)


# ============================================================
# VEHICLE INSPECTION
# ============================================================

class InspectionCreate(BaseModel):
    """
    Data entered by the analyst when recording
    the latest known vehicle inspection/state.
    """

    last_inspection_date: date

    mileage: int = Field(
        ge=0,
        description="Current recorded vehicle mileage."
    )

    vehicle_condition: str = Field(
        min_length=1,
        max_length=50
    )


    @field_validator("vehicle_condition")
    @classmethod
    def clean_vehicle_condition(
        cls,
        value: str
    ) -> str:

        value = value.strip()

        if not value:
            raise ValueError(
                "Vehicle condition cannot be empty."
            )

        return value



# ============================================================
# FORECAST REQUEST
# ============================================================

class ForecastRequest(BaseModel):
    """
    Current vehicle information supplied when
    requesting an updated residual-value forecast.
    """

    mileage: int = Field(
        ge=0,
        description=(
            "Latest known vehicle mileage "
            "used for the forecast."
        )
    )

    vehicle_condition: str = Field(
        min_length=1,
        max_length=50
    )

    last_inspection_date: date

    expected_lease_end_condition: Optional[str] = None


    @field_validator("vehicle_condition")
    @classmethod
    def clean_current_condition(
        cls,
        value: str
    ) -> str:

        value = value.strip()

        if not value:
            raise ValueError(
                "Vehicle condition cannot be empty."
            )

        return value


    @field_validator(
        "expected_lease_end_condition"
    )
    @classmethod
    def clean_expected_condition(
        cls,
        value: Optional[str]
    ) -> Optional[str]:

        if value is None:
            return None

        value = value.strip()

        # Treat an empty frontend field as
        # "no lease-end condition assumption".
        if not value:
            return None

        return value