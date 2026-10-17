import joblib
import pandas as pd
import numpy as np
from datetime import datetime, date
from pathlib import Path


# ============================================================
# 1. LOAD TRAINED ML PIPELINE
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent
model = joblib.load(BASE_DIR / "ml" / "arvf_voting_model .joblib")


# ============================================================
# 2. MODEL INPUT CONFIGURATION
# ============================================================

REQUIRED_VEHICLE_FIELDS = [
    "make",
    "model",
    "year",
    "mileage",
    "engine_hp",
    "accident_history",
    "condition",
]

OPTIONAL_MODEL_FIELDS = [
    "transmission",
    "fuel_type",
    "drivetrain",
    "body_type",
    "exterior_color",
    "interior_color",
    "owner_count",
    "seller_type",
    "trim",
]


REQUIRED_LEASE_FIELDS = [
    "lease_end_date",
    "expected_annual_mileage",
    "original_rv",
]


# Training data ranges for exptrapolation checks, to ensure
# that the projected future vehicle state is within the
# range seen during model training.
TRAIN_RANGES = {
    "min_age": 1.0,
    "max_age": 25.0,

    "min_mpy": 33.333333333333336,
    "max_mpy": 55391.0,

    "p01_age": 1.0,
    "p99_age": 17.0,

    "p01_mpy": 863.9966666666666,
    "p99_mpy": 28760.501
}

MODEL_PRICE_MIN = 1500.0
MODEL_PRICE_MAX = 93422.09

# ============================================================
# 3. INPUT VALIDATION
# ============================================================

def validate_vehicle_input(vehicle: dict):

    required_fields = (
        REQUIRED_VEHICLE_FIELDS
        + REQUIRED_LEASE_FIELDS
    )

    missing = [
        field
        for field in required_fields
        if field not in vehicle
    ]

    if missing:
        raise ValueError(
            f"Missing required field(s): {missing}"
        )
    # -----------------------------------------
    #Engine HP check
    # -----------------------------------------
    if vehicle["engine_hp"] <= 0:
        raise ValueError(
            "Engine HP must be greater than 0."
        )
    # -----------------------------------------
    # Owner count check
    # -----------------------------------------
    owner_count = vehicle.get(
    "owner_count"
)

    if (
       owner_count is not None
       and
       not (
           isinstance(owner_count, float)
           and np.isnan(owner_count)
       )
    ):
 
       if owner_count < 0:
         raise ValueError(
            "Owner count cannot be negative."
         )
    # ----------------------------
    # Mileage validation
    # ----------------------------

    if vehicle["mileage"] < 0:
        raise ValueError(
            "Current mileage cannot be negative."
        )


    if vehicle["expected_annual_mileage"] <= 0:
        raise ValueError(
            "Expected annual mileage must be greater than 0."
        )


    # ----------------------------
    # Vehicle year validation
    # ----------------------------

    current_year = datetime.now().year

    if vehicle["year"] > current_year:
        raise ValueError(
            f"Vehicle year {vehicle['year']} looks invalid."
        )


    # ----------------------------
    # Original RV validation
    # ----------------------------

    if vehicle["original_rv"] <= 0:
        raise ValueError(
            "Original RV must be greater than 0."
        )
    # -------------------------------
    #  Optional value validation
    # -------------------------------
def optional_model_value(data, field_name):
    value = data.get(field_name)

    if value is None:
        return np.nan

    if isinstance(value, str) and value.strip() == "":
        return np.nan

    return value


# ============================================================
# 4. PREDICT VALUE OF A GIVEN VEHICLE STATE
# ============================================================

def predict_vehicle_value(vehicle: dict) -> float:

    """
    Uses the trained ML model to estimate the market value
    of the supplied vehicle state.

    IMPORTANT:
    The trained model predicts vehicle market price.
    It was NOT directly trained on lease-end RV outcomes.
    """

    model_input = pd.DataFrame([{

    "make": vehicle["make"],

    "model": vehicle["model"],

    "mileage": int(
        round(vehicle["mileage"])
    ),

    "engine_hp": vehicle["engine_hp"],

    "transmission":
        optional_model_value(
            vehicle,
            "transmission"
        ),

    "fuel_type":
        optional_model_value(
            vehicle,
            "fuel_type"
        ),

    "drivetrain":
        optional_model_value(
            vehicle,
            "drivetrain"
        ),

    "body_type":
        optional_model_value(
            vehicle,
            "body_type"
        ),

    "exterior_color":
        optional_model_value(
            vehicle,
            "exterior_color"
        ),

    "interior_color":
        optional_model_value(
            vehicle,
            "interior_color"
        ),

    "owner_count":
        optional_model_value(
            vehicle,
            "owner_count"
        ),

    "accident_history":
        vehicle["accident_history"],

    "seller_type":
        optional_model_value(
            vehicle,
            "seller_type"
        ),

    "condition":
        vehicle["condition"],

    "trim":
        optional_model_value(
            vehicle,
            "trim"
        ),

    "vehicle_age":
        vehicle["vehicle_age"],

    "mileage_per_year":
        vehicle["mileage_per_year"],
  }])

    # ------------------------------------------------
    # ACTUAL ML PREDICTION HAPPENS HERE
    # ------------------------------------------------

    prediction = model.predict(model_input)[0]

    return float(prediction)


# ============================================================
# 5. EXTRAPOLATION CHECK
# ============================================================

def check_extrapolation(
    vehicle_age: float,
    mileage_per_year: float
) -> list:

    """
    Warns if the projected future vehicle state is outside
    the range seen during model training.

    No warning is produced until real training ranges
    have been supplied.
    """

    warnings = []


    # ----------------------------
    # Vehicle age
    # ----------------------------

    
    if TRAIN_RANGES["max_age"] is not None:

        if vehicle_age > TRAIN_RANGES["max_age"]:

            warnings.append(

                f"Projected vehicle_age "
                f"({vehicle_age:,.0f}) exceeds the "
                f"maximum seen during training "
                f"({TRAIN_RANGES['max_age']:,.0f})."
            )

    if TRAIN_RANGES["min_age"] is not None:
    
            if vehicle_age < TRAIN_RANGES["min_age"]:
    
                warnings.append(
    
                    f"Projected vehicle_age"
                    f"({vehicle_age:,.0f}) is below the "
                    f"minimum seen during training "
                    f"({TRAIN_RANGES['min_age']:,.0f})."
                )
    



    # ----------------------------
    # Mileage per year
    # ----------------------------

    if TRAIN_RANGES["max_mpy"] is not None:

        if mileage_per_year > TRAIN_RANGES["max_mpy"]:

            warnings.append(

                f"Projected mileage/year "
                f"({mileage_per_year:,.0f}) exceeds the "
                f"maximum seen during training "
                f"({TRAIN_RANGES['max_mpy']:,.0f})."
            )


    if TRAIN_RANGES["min_mpy"] is not None:

        if mileage_per_year < TRAIN_RANGES["min_mpy"]:

            warnings.append(

                f"Projected mileage/year "
                f"({mileage_per_year:,.0f}) is below the "
                f"minimum seen during training "
                f"({TRAIN_RANGES['min_mpy']:,.0f})."
            )


    return warnings


# ============================================================
# 6. PROJECT VEHICLE TO LEASE END
# ============================================================

def project_vehicle_to_lease_end(vehicle: dict) -> dict:

    """
    Projects measurable vehicle characteristics to the
    lease-end date.

    We project:
        - mileage
        - vehicle age
        - mileage per year

    We DO NOT automatically invent:
        - future accidents
        - future condition deterioration

    Condition and accident history remain unchanged unless
    the application explicitly supplies a lease-end scenario.
    """

    today = date.today()


    # ------------------------------------------------
    # Convert lease_end_date if received as string
    # ------------------------------------------------

    lease_end_date = vehicle["lease_end_date"]

    if isinstance(lease_end_date, str):

        lease_end_date = datetime.strptime(
            lease_end_date,
            "%Y-%m-%d"
        ).date()

 
    # ------------------------------------------------
    # Validate lease-end date
    # ------------------------------------------------

    if lease_end_date <= today:

        raise ValueError(
            "Lease end date must be in the future."
        )


    # ------------------------------------------------
    # Calculate remaining lease duration
    # ------------------------------------------------

    days_remaining = (
        lease_end_date - today
    ).days

    years_remaining = (
        days_remaining / 365.25
    )


    # ------------------------------------------------
    # Current information
    # ------------------------------------------------

    current_mileage = vehicle["mileage"]

    expected_annual_mileage = (
        vehicle["expected_annual_mileage"]
    )

    vehicle_year = vehicle["year"]


    # ------------------------------------------------
    # PROJECT FUTURE MILEAGE
    # ------------------------------------------------

    added_mileage = (
        expected_annual_mileage
        * years_remaining
    )

    projected_mileage = (
        current_mileage
        + added_mileage
    )


    # ------------------------------------------------
    # PROJECT FUTURE VEHICLE AGE
    # ------------------------------------------------

    projected_vehicle_age = max(
        lease_end_date.year - vehicle_year,
        1
    )


    # ------------------------------------------------
    # PROJECT MILEAGE PER YEAR
    # ------------------------------------------------

    projected_mileage_per_year = (

        projected_mileage
        / projected_vehicle_age

    )


    # ------------------------------------------------
    # CREATE FUTURE VEHICLE STATE
    # ------------------------------------------------

    future_vehicle = vehicle.copy()

    future_vehicle["mileage"] = (
        projected_mileage
    )

    future_vehicle["vehicle_age"] = (
        projected_vehicle_age
    )

    future_vehicle["mileage_per_year"] = (
        projected_mileage_per_year
    )


    # ------------------------------------------------
    # CONDITION ASSUMPTION
    # ------------------------------------------------
    #
    # Do NOT automatically degrade condition using an
    # invented rule.
    #
    # If  application later collects something like:
    #
    # expected_lease_end_condition = "Fair"
    #
    # use it.
    #
    # Otherwise keep current condition.
    # ------------------------------------------------

    if "expected_lease_end_condition" in vehicle:

        future_vehicle["condition"] = (
            vehicle["expected_lease_end_condition"]
        )

    else:

        future_vehicle["condition"] = (
            vehicle["condition"]
        )


    # ------------------------------------------------
    # ACCIDENT HISTORY
    # ------------------------------------------------
    #
    # Future accidents cannot be known.
    # Keep current accident history unchanged.
    # ------------------------------------------------

    future_vehicle["accident_history"] = (
        vehicle["accident_history"]
    )


    return {

        "future_vehicle": future_vehicle,

        "years_remaining": years_remaining,

        "added_mileage": added_mileage,

        "projected_mileage": projected_mileage,

        "projected_vehicle_age":
            projected_vehicle_age,

        "projected_mileage_per_year":
            projected_mileage_per_year,
    }


# ============================================================
# 7. COMPLETE ARVF FORECAST
# ============================================================

def predict_lease_end_value(vehicle: dict) -> dict:

    """
    Main function used by the ARVF backend.

    Current vehicle
            ↓
    Project lease-end vehicle state
            ↓
    ML valuation model
            ↓
    Estimated lease-end market value
            ↓
    Compare with Original RV
            ↓
    RV Gap
    """

    # ------------------------------------------------
    # Validate inputs
    # ------------------------------------------------

    validate_vehicle_input(vehicle)


    # ------------------------------------------------
    # Project vehicle to lease end
    # ------------------------------------------------

    projection = (
        project_vehicle_to_lease_end(vehicle)
    )


    future_vehicle = (
        projection["future_vehicle"]
    )
    # ------------------------------------------------
    # Check whether projected state is outside
    # training range
    # ------------------------------------------------

    extrapolation_warnings = (
        check_extrapolation(

            projection[
                "projected_vehicle_age"
            ],

            projection[
                "projected_mileage_per_year"
            ]
        )
    )


    # ------------------------------------------------
    # ESTIMATE VALUE OF PROJECTED VEHICLE
    # ------------------------------------------------

    predicted_future_value = (
        predict_vehicle_value(
            future_vehicle
        )
    )


    # ------------------------------------------------
    # CHECK PREDICTED VALUE AGAINST TRAINING RANGE
    # ------------------------------------------------

    if predicted_future_value > MODEL_PRICE_MAX:

        extrapolation_warnings.append(
            (
                "Predicted vehicle value exceeds the maximum "
                "price observed during model training. "
                "Forecast reliability may be lower."
            )
        )


    # ------------------------------------------------
    # ORIGINAL RV
    # ------------------------------------------------

    original_rv = float(
        vehicle["original_rv"]
    )


    # ------------------------------------------------
    # RV GAP
    #
    # Positive = forecast above Original RV
    # Negative = potential RV exposure
    # ------------------------------------------------

    rv_gap = (
        predicted_future_value
        - original_rv
    )


    potential_exposure = max(
        -rv_gap,
        0
    )


    # ------------------------------------------------
    # SIMPLE BUSINESS STATUS
    # ------------------------------------------------

    if rv_gap < 0:

        rv_status = "Potential Exposure"

    else:

        rv_status = "Above Original RV"


    # =================================================
    # FINAL OUTPUT
    # =================================================

    return {

        "forecast_type":
            "Scenario-based lease-end market value estimate",

        "years_remaining":
            round(
                projection["years_remaining"],
                2
            ),

        "current_mileage":
            round(vehicle["mileage"]),

        "projected_added_mileage":
            round(
                projection["added_mileage"]
            ),

        "projected_mileage":
            round(
                projection["projected_mileage"]
            ),

        "projected_vehicle_age":
            projection[
                "projected_vehicle_age"
            ],

        "projected_mileage_per_year":
            round(
                projection[
                    "projected_mileage_per_year"
                ]
            ),

        "current_condition":
            vehicle["condition"],

        "assumed_lease_end_condition":
            future_vehicle["condition"],

        "predicted_lease_end_value":
            round(
                predicted_future_value,
                2
            ),

        "original_rv":
            round(
                original_rv,
                2
            ),

        "rv_gap":
            round(
                rv_gap,
                2
            ),

        "potential_rv_exposure":
            round(
                potential_exposure,
                2
            ),

        "rv_status":
            rv_status,

        "extrapolation_warnings":
            extrapolation_warnings,

        "assumptions": [

            "Lease-end mileage is projected using expected annual mileage.",

            "Current condition is assumed to remain unchanged unless an expected lease-end condition is supplied.",

            "Current accident history is held constant because future accidents cannot be predicted from the available data.",

            "The ML model was trained to estimate vehicle market price, not directly on historical lease-end residual-value outcomes.",

            "No future market inflation, demand shift, or macroeconomic adjustment is currently modeled."
        ],

        "model_limitation":
            "The estimate values a projected future vehicle state using a static vehicle-price model. It is not a directly validated time-series residual-value forecast."
    }