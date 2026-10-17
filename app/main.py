import io
import hashlib
import pandas as pd

from pathlib import Path
from app.auth import (
    get_current_user,
    router as auth_router
)
from fastapi import Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi import (
     FastAPI, 
    Depends,
     HTTPException, 
     UploadFile, 
     File
)
from sqlalchemy import text
from pydantic import BaseModel
from datetime import date
from typing import Literal

from app.database import engine
from app.prediction import predict_lease_end_value
from app.models import (
    InspectionCreate
)
BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = BASE_DIR / "templates"



app = FastAPI()
app.include_router(auth_router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:4200"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def home():
    return {"message": "ARVF backend is running"}

# ============================================================
# PORTFOLIO IMPORT CONFIGURATION
# ============================================================

REQUIRED_PORTFOLIO_COLUMNS = [

    "vehicle_code",

    "make",
    "model",
    "model_year",

    "current_mileage",
    "current_condition",
    "engine_hp",
    "accident_history",
    "lease_start_date",
    "lease_end_date",
    "purchase_value",

    "original_rv",

    "expected_annual_mileage"
]


OPTIONAL_PORTFOLIO_COLUMNS = [
    "last_inspection_date",
    "transmission",
    "fuel_type",
    "drivetrain",
    "body_type",
    "exterior_color",
    "interior_color",
    "owner_count",
    "seller_type",
    "trim"
]


VALID_CONDITIONS = {

    "Excellent",
    "Good",
    "Fair"

}

VALID_ACCIDENT_HISTORY = {
    "Unknown",
    "Minor",
    "Major"
}

VALID_TRANSMISSIONS = {
    "Manual",
    "Automatic"
}

VALID_FUEL_TYPES = {
    "Electric",
    "Diesel",
    "Gasoline"
}

VALID_DRIVETRAINS = {
    "RWD",
    "FWD",
    "AWD"
}

VALID_SELLER_TYPES = {
    "Dealer",
    "Private"
}

MODEL_PRICE_MIN = 1500.0
MODEL_PRICE_MAX = 93422.09

# Above training range but still plausible for an expensive vehicle
MODEL_PRICE_WARNING_LIMIT = 200000.0

# So large that it likely represents another currency / scale
MONETARY_SCALE_HARD_LIMIT = 250000.0

CURRENT_YEAR = date.today().year

# Backend endpoint to retrieve a list of vehicles from the database.
@app.get("/vehicles/search")
def search_vehicles(
    q: str,
    import_id: int = Query(..., ge=1),
    current_user: dict = Depends(get_current_user)
):

    with engine.connect() as connection:

        result = connection.execute(
            text("""
                SELECT TOP 20
                    vehicle_id,
                    vehicle_code
                FROM dbo.vehicle v
                WHERE 
                    v.import_id = :import_id
                    AND EXISTS
                    (
                        SELECT 1
                        FROM dbo.portfolio_import pi
                        WHERE pi.import_id = v.import_id
                          AND pi.user_id = :user_id
                          AND pi.import_status = 'COMPLETED'
                                                    AND pi.is_archived = 0
                    )

                    AND
                    (
                       v.vehicle_code LIKE :search
                       OR CAST(v.vehicle_id AS VARCHAR) LIKE :search

                    )
                ORDER BY
                  v.vehicle_id
            """ ),
            {"import_id": import_id,
             "user_id": current_user["user_id"],
             "search": f"%{q}%"
            }
        ).mappings().all()

        return [
            {
                "vehicle_id": row["vehicle_id"],
                "vehicle_code": row["vehicle_code"]
            }
            for row in result
        ]
#backend endpoint to get a summary of the portfolio, including:
# The number of active leased vehicles, the number of vehicles
# with at least one forecast, the number of vehicles that currently
# need review, and the total potential RV exposure.
@app.get("/portfolio/summary")
def get_portfolio_summary(
    import_id: int | None = Query(default=None, ge=1),
    current_user: dict = Depends(get_current_user)
):

    with engine.connect() as connection:

        row = connection.execute(
            text("""
                WITH LatestAcceptedForecast AS
                (
                    SELECT
                        f.lease_id,
                        f.forecast_id,
                        f.review_status,
                        f.potential_exposure,
                        ROW_NUMBER() OVER
                        (
                            PARTITION BY f.lease_id
                            ORDER BY f.forecast_date DESC, f.forecast_id DESC
                        ) AS forecast_rank
                    FROM dbo.rv_forecast f
                    WHERE f.forecast_status = 'ACCEPTED'
                )
                SELECT

                    SUM(
                        CASE
                            WHEN
                                vl.lease_start_date <= CAST(GETDATE() AS date)
                                AND
                                vl.lease_end_date > CAST(GETDATE() AS date)
                            THEN 1
                            ELSE 0
                        END
                    ) AS active_leased_vehicles,

                    SUM(
                        CASE
                            WHEN rf.forecast_id IS NOT NULL
                            THEN 1
                            ELSE 0
                        END
                    ) AS vehicles_forecasted,

                    SUM(
                        CASE
                            WHEN rf.review_status IN (
                                'REVIEW',
                                'HIGH_RISK'
                            )
                            THEN 1
                            ELSE 0
                        END
                    ) AS vehicles_requiring_review,

                    SUM(
                        COALESCE(
                            rf.potential_exposure,
                            0
                        )
                    ) AS potential_rv_exposure

                FROM dbo.vehicle_lease vl

                JOIN dbo.vehicle v
                    ON v.vehicle_id = vl.vehicle_id

                JOIN dbo.portfolio_import pi
                    ON pi.import_id = vl.import_id

                LEFT JOIN LatestAcceptedForecast rf
                    ON rf.lease_id = vl.lease_id
                    AND rf.forecast_rank = 1

                WHERE
                    (:import_id IS NULL OR vl.import_id = :import_id)

                    AND
                    pi.user_id = :user_id

                    AND
                    pi.import_status = 'COMPLETED'

                    AND
                    pi.is_archived = 0

            """),

            {
                "import_id": import_id,
                "user_id": current_user["user_id"]
            }

        ).mappings().first()


        return {

            "active_leased_vehicles":
                int(
                    row["active_leased_vehicles"]
                    or 0
                ),

            "vehicles_forecasted":
                int(
                    row["vehicles_forecasted"]
                    or 0
                ),

            "vehicles_requiring_review":
                int(
                    row["vehicles_requiring_review"]
                    or 0
                ),

            "potential_rv_exposure":
                float(
                    row["potential_rv_exposure"]
                    or 0
                )
        }
# ==========================================================================================
# Backend endpoint to validate the uploaded portfolio file, that checks for required columns, 
# data types, file type, logical consistency and returns a summary of the validation results, including
# the number of valid and invalid rows, any missing rows, duplicate vehicle codes, and a list
# of validation errors for each row.
# ==========================================================================================
@app.post("/portfolio/import/validate")
async def validate_portfolio_import(
    file: UploadFile = File(...),
    _current_user: dict = Depends(get_current_user)
):

    # ========================================================
    # 1. Make sure a file was selected
    # ========================================================

    if not file.filename:
        raise HTTPException(
            status_code=400,
            detail="No file was selected."
        )


    # ========================================================
    # 2. Validate file extension
    # ========================================================

    filename = file.filename.lower()

    is_csv = filename.endswith(".csv")
    is_excel = filename.endswith(".xlsx")

    if not (is_csv or is_excel):
        raise HTTPException(
            status_code=400,
            detail=(
                "Unsupported file type. "
                "Please upload a CSV or XLSX file."
            )
        )


    # ========================================================
    # 3. Read uploaded file
    # ========================================================

    try:

        file_content = await file.read()

        if is_csv:

            dataframe = pd.read_csv(
                io.BytesIO(file_content)
            )

        else:

            dataframe = pd.read_excel(
                io.BytesIO(file_content)
            )

    except Exception:

        raise HTTPException(
            status_code=400,
            detail=(
                "The uploaded file could not be read. "
                "Please verify that it is a valid CSV "
                "or XLSX file."
            )
        )


    # ========================================================
    # 4. Reject empty portfolio
    # ========================================================

    if dataframe.empty:
        raise HTTPException(
            status_code=400,
            detail="The uploaded portfolio contains no records."
        )


    # ========================================================
    # 5. Clean column names
    # ========================================================

    dataframe.columns = [
        str(column)
        .strip()
        .lower()

        for column in dataframe.columns
    ]


    # ========================================================
    # 6. Check required columns
    # ========================================================

    missing_columns = [
        column

        for column in REQUIRED_PORTFOLIO_COLUMNS

        if column not in dataframe.columns
    ]


    if missing_columns:

        return {
            "valid": False,

            "file_name": file.filename,

            "total_rows": len(dataframe),

            "valid_rows": 0,

            "invalid_rows": len(dataframe),

            "missing_columns": missing_columns,

            "duplicate_vehicle_codes": [],

            "errors": [
                {
                    "row": None,
                    "vehicle_code": None,
                    "errors": [
                        (
                            "Required portfolio columns are missing: "
                            + ", ".join(missing_columns)
                        )
                    ]
                }
            ],

            "message":
                "Portfolio file is missing required columns."
        }


    # ========================================================
    # 7. Store row-level validation errors
    # ========================================================

    row_errors = []

    today = pd.Timestamp.today().normalize()
    current_year = date.today().year


    # ========================================================
    # 8. Validate every portfolio row
    # ========================================================

    for index, row in dataframe.iterrows():

        # +2 because:
        # dataframe index begins at 0
        # spreadsheet row 1 contains column headers
        spreadsheet_row = index + 2

        errors_for_row = []


        # ----------------------------------------------------
        # A. Required values cannot be blank
        # ----------------------------------------------------

        for column in REQUIRED_PORTFOLIO_COLUMNS:

            value = row[column]

            if (
                pd.isna(value)
                or
                str(value).strip() == ""
            ):

                errors_for_row.append(
                    f"{column} is required"
                )


        # ----------------------------------------------------
        # B. Validate current condition
        # ----------------------------------------------------

        if not pd.isna(row["current_condition"]):

            condition = str(
                row["current_condition"]
            ).strip()

            if (
                condition
                and
                condition not in VALID_CONDITIONS
            ):

                errors_for_row.append(
                    (
                        "current_condition must be "
                        "Excellent, Good or Fair"
                    )
                )


        # ----------------------------------------------------
        # C. Validate accident history
        # ----------------------------------------------------

        if not pd.isna(row["accident_history"]):

            accident_history = str(
                row["accident_history"]
            ).strip()

            if (
                accident_history
                and
                accident_history
                not in VALID_ACCIDENT_HISTORY
            ):

                errors_for_row.append(
                    (
                        "accident_history must be "
                        "Major, Minor or Unknown"
                    )
                )


        # ----------------------------------------------------
        # D. Validate required numerical fields
        # ----------------------------------------------------

        numeric_fields = [
            "model_year",
            "current_mileage",
            "engine_hp",
            "original_rv",
            "purchase_value",
            "expected_annual_mileage"
        ]


        for column in numeric_fields:

            value = row[column]

            # Missing value was already handled above
            if (
                pd.isna(value)
                or
                str(value).strip() == ""
            ):
                continue

            try:

                numeric_value = float(value)

                if numeric_value < 0:

                    errors_for_row.append(
                        f"{column} cannot be negative"
                    )

            except (ValueError, TypeError):

                errors_for_row.append(
                    f"{column} must be numeric"
                )


        # ----------------------------------------------------
        # E. Some numerical fields must be > 0
        # ----------------------------------------------------

        positive_fields = [
            "engine_hp",
            "original_rv",
            "purchase_value",
            "expected_annual_mileage"
        ]


        for column in positive_fields:

            value = row[column]

            if (
                pd.isna(value)
                or
                str(value).strip() == ""
            ):
                continue

            try:

                numeric_value = float(value)

                if numeric_value <= 0:

                    errors_for_row.append(
                        f"{column} must be greater than 0"
                    )

            except (ValueError, TypeError):
                # Already reported by numeric validation
                pass

        purchase_value = pd.to_numeric(
            row["purchase_value"],
            errors="coerce"
        )
        original_rv = pd.to_numeric(
            row["original_rv"],
            errors="coerce"
        )

        if (
            pd.notna(purchase_value)
            and purchase_value > MONETARY_SCALE_HARD_LIMIT
        ):

            errors_for_row.append(
              (
                "purchase_value is far above the monetary "
                "range supported by the ARVF prototype and "
                "may use a different currency or monetary scale"
              )
            )


        if (
            pd.notna(original_rv)
            and original_rv > MONETARY_SCALE_HARD_LIMIT
        ):

            errors_for_row.append(
              (
                 "original_rv is far above the monetary "
                 "range supported by the ARVF prototype and "
                 "may use a different currency or monetary scale"
              )
            )


        # ----------------------------------------------------
        # F. Validate model year
        # ----------------------------------------------------

        try:

            model_year = int(
                float(row["model_year"])
            )

            if model_year > current_year:

                errors_for_row.append(
                    (
                        "model_year cannot be greater "
                        "than the current year"
                    )
                )

        except (ValueError, TypeError):
            # Already handled by numeric validation
            pass


        # ----------------------------------------------------
        # G. Validate optional owner_count
        # ----------------------------------------------------

        if "owner_count" in dataframe.columns:

            owner_count_value = row["owner_count"]

            if (
                not pd.isna(owner_count_value)
                and
                str(owner_count_value).strip() != ""
            ):

                try:

                    owner_count_float = float(
                        owner_count_value
                    )

                    if not owner_count_float.is_integer():

                        errors_for_row.append(
                            "owner_count must be a whole number"
                        )

                    elif owner_count_float < 0:

                        errors_for_row.append(
                            "owner_count cannot be negative"
                        )

                except (ValueError, TypeError):

                    errors_for_row.append(
                        "owner_count must be numeric"
                    )

        # ----------------------------------------------------
        # Validate optional categorical model fields
        # ----------------------------------------------------

        optional_category_rules = {
          "transmission": VALID_TRANSMISSIONS,
          "fuel_type": VALID_FUEL_TYPES,
          "drivetrain": VALID_DRIVETRAINS,
          "seller_type": VALID_SELLER_TYPES
        }


        for column, valid_values in optional_category_rules.items():

       # Column itself is optional
           if column not in dataframe.columns:
              continue

           value = row[column]

       # Blank value is allowed
           if (
              pd.isna(value)
              or
              str(value).strip() == ""
           ):
              continue

           value = str(value).strip()

           if value not in valid_values:

              errors_for_row.append(
                (
                  f"{column} contains an unsupported value. "
                  f"Supported values are: "
                  f"{', '.join(sorted(valid_values))}"
                )
              )


        # ----------------------------------------------------
        # H. Validate lease start date
        # Required format: YYYY-MM-DD
        # ----------------------------------------------------

        lease_start = pd.to_datetime(
            row["lease_start_date"],
            format="%Y-%m-%d",
            errors="coerce"
        )


        if pd.isna(lease_start):

            errors_for_row.append(
                (
                    "lease_start_date is invalid. "
                    "Use YYYY-MM-DD format"
                )
            )

        else:

            lease_start = lease_start.normalize()

            if lease_start > today:

                errors_for_row.append(
                    (
                        "lease_start_date cannot "
                        "be in the future"
                    )
                )


        # ----------------------------------------------------
        # I. Validate lease end date
        # Required format: YYYY-MM-DD
        # ----------------------------------------------------

        lease_end = pd.to_datetime(
            row["lease_end_date"],
            format="%Y-%m-%d",
            errors="coerce"
        )


        if pd.isna(lease_end):

            errors_for_row.append(
                (
                    "lease_end_date is invalid. "
                    "Use YYYY-MM-DD format"
                )
            )

        else:

            lease_end = lease_end.normalize()

            if lease_end <= today:

                errors_for_row.append(
                    (
                        "lease_end_date must be later "
                        "than today's date"
                    )
                )


        # ----------------------------------------------------
        # J. Lease end must occur after lease start
        # ----------------------------------------------------

        if (
            not pd.isna(lease_start)
            and
            not pd.isna(lease_end)
            and
            lease_end <= lease_start
        ):

            errors_for_row.append(
                (
                    "lease_end_date must be later "
                    "than lease_start_date"
                )
            )


        # ----------------------------------------------------
        # K. Validate optional last inspection date
        # ----------------------------------------------------

        if "last_inspection_date" in dataframe.columns:

            inspection_value = row[
                "last_inspection_date"
            ]

            if (
                not pd.isna(inspection_value)
                and
                str(inspection_value).strip() != ""
            ):

                inspection_date = pd.to_datetime(
                    inspection_value,
                    format="%Y-%m-%d",
                    errors="coerce"
                )

                if pd.isna(inspection_date):

                    errors_for_row.append(
                        (
                            "last_inspection_date is invalid. "
                            "Use YYYY-MM-DD format"
                        )
                    )

                else:

                    inspection_date = (
                        inspection_date.normalize()
                    )

                    if inspection_date > today:

                        errors_for_row.append(
                            (
                                "last_inspection_date "
                                "cannot be in the future"
                            )
                        )


        # ----------------------------------------------------
        # L. Save validation errors for this row
        # ----------------------------------------------------

        if errors_for_row:

            vehicle_code = None

            if (
                not pd.isna(row["vehicle_code"])
                and
                str(row["vehicle_code"]).strip() != ""
            ):

                vehicle_code = str(
                    row["vehicle_code"]
                ).strip()


            row_errors.append({
                "row": spreadsheet_row,
                "vehicle_code": vehicle_code,
                "errors": errors_for_row
            })


    # ========================================================
    # 9. Check duplicate vehicle codes inside uploaded file
    # ========================================================

    vehicle_codes = (
        dataframe["vehicle_code"]
        .astype(str)
        .str.strip()
    )


    duplicate_mask = (
        vehicle_codes.ne("")
        &
        vehicle_codes.ne("nan")
        &
        vehicle_codes.duplicated(
            keep=False
        )
    )


    duplicate_codes = (
        vehicle_codes[
            duplicate_mask
        ]
        .unique()
        .tolist()
    )


    duplicate_row_numbers = set(
        dataframe.index[
            duplicate_mask
        ]
        + 2
    )


    # ========================================================
    # 10. Calculate final validation summary
    # ========================================================

    invalid_row_numbers = {
        error["row"]

        for error in row_errors

        if error["row"] is not None
    }


    # Duplicate rows are also invalid
    invalid_row_numbers.update(
        duplicate_row_numbers
    )


    valid_rows = (
        len(dataframe)
        -
        len(invalid_row_numbers)
    )


    # ========================================================
    # 11. Determine whether whole portfolio is valid
    # ========================================================

    portfolio_is_valid = (
        len(row_errors) == 0
        and
        len(duplicate_codes) == 0
    )


    # ========================================================
    # 12. Return validation result
    # ========================================================

    return {

        "valid":
            portfolio_is_valid,

        "file_name":
            file.filename,

        "total_rows":
            len(dataframe),

        "valid_rows":
            valid_rows,

        "invalid_rows":
            len(invalid_row_numbers),

        "missing_columns":
            [],

        "duplicate_vehicle_codes":
            duplicate_codes,

        "errors":
            row_errors[:50],

        "message":
            (
                "Portfolio file passed validation."
                if portfolio_is_valid
                else
                "Portfolio file contains validation issues."
            )
    }

# Helper function for optional values of dataset that allows allows user to
# skip the optional values (if he wants) by returning none.

def get_optional_value(row, column):

    if column not in row.index:
        return None

    value = row[column]

    if pd.isna(value):
        return None

    if isinstance(value, str):
        value = value.strip()

        if value == "":
            return None

    return value

# Helper function for lease duration

def calculate_lease_months(
    lease_start_date,
    lease_end_date
):

    months = (
        (lease_end_date.year - lease_start_date.year) * 12
        +
        (lease_end_date.month - lease_start_date.month)
    )

    if lease_end_date.day < lease_start_date.day:
        months -= 1

    return max(months, 1)
# =====================================================
# Backend endpoint for importing portfolio by validating
# all the checkpoints and saving those records to SQL data
# base
#==========================================================

@app.post("/portfolio/import")
async def import_portfolio(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):

    # ========================================================
    # 1. Basic file checks
    # ========================================================

    if not file.filename:
        raise HTTPException(
            status_code=400,
            detail="No file was selected."
        )

    filename = file.filename.lower()

    is_csv = filename.endswith(".csv")
    is_excel = filename.endswith(".xlsx")

    if not (is_csv or is_excel):
        raise HTTPException(
            status_code=400,
            detail=(
                "Unsupported file type. "
                "Please upload a CSV or XLSX file."
            )
        )


    # ========================================================
    # 2. Read the uploaded portfolio
    # ========================================================

    try:

        file_content = await file.read()

        file_hash = hashlib.sha256(
            file_content
        ).hexdigest()

        if is_csv:

            dataframe = pd.read_csv(
                io.BytesIO(file_content)
            )

        else:

            dataframe = pd.read_excel(
                io.BytesIO(file_content)
            )

    except Exception:

        raise HTTPException(
            status_code=400,
            detail=(
                "The uploaded portfolio file "
                "could not be read."
            )
        )


    if dataframe.empty:

        raise HTTPException(
            status_code=400,
            detail="The uploaded portfolio contains no records."
        )


    # ========================================================
    # 3. Clean column names
    # ========================================================

    dataframe.columns = [
        str(column)
        .strip()
        .lower()

        for column in dataframe.columns
    ]


    # ========================================================
    # 4. Safety check required columns again
    # ========================================================

    missing_columns = [
        column

        for column in REQUIRED_PORTFOLIO_COLUMNS

        if column not in dataframe.columns
    ]


    if missing_columns:

        raise HTTPException(
            status_code=400,
            detail=(
                "Import cannot continue. "
                "Missing required columns: "
                + ", ".join(missing_columns)
            )
        )


    # ========================================================
    # 5. Prevent duplicate vehicle codes inside the file
    # ========================================================

    vehicle_codes = (
        dataframe["vehicle_code"]
        .astype(str)
        .str.strip()
    )

    duplicate_codes = (
        vehicle_codes[
            vehicle_codes.duplicated(
                keep=False
            )
        ]
        .unique()
        .tolist()
    )


    if duplicate_codes:

        raise HTTPException(
            status_code=400,
            detail=(
                "Import cannot continue because "
                "duplicate vehicle codes exist: "
                + ", ".join(duplicate_codes)
            )
        )


    # ========================================================
    # 6. Begin ONE database transaction
    # ========================================================

    try:

        with engine.begin() as connection:

            # Check duplicate file
            existing_import = connection.execute (
              text("""
                     SELECT import_id
                     FROM dbo.portfolio_import
                                         WHERE user_id = :user_id
                                             AND file_hash = :file_hash
               """),
               {
                                        "user_id": current_user["user_id"],
                    "file_hash": file_hash
               }
            ).scalar()

            if existing_import is not None:
               raise ValueError(
                "This exact portfolio file has already been imported."
               )


            # =================================================
            # 7. Create portfolio_import record
            # =================================================

            import_id = connection.execute(
                text("""
                    INSERT INTO dbo.portfolio_import
                    (
                        user_id,
                        file_name,
                        file_hash,
                        total_rows,
                        successful_rows,
                        failed_rows,
                        import_status
                    )

                    OUTPUT INSERTED.import_id

                    VALUES
                    (
                        :user_id,
                        :file_name,
                        :file_hash,
                        :total_rows,
                        0,
                        0,
                        'PROCESSING'
                    )
                """),
                {
                    "user_id": current_user["user_id"],
                    "file_name": file.filename,
                    "file_hash": file_hash,
                    "total_rows": len(dataframe)
                }
            ).scalar_one()


            successful_rows = 0


            # =================================================
            # 8. Process every uploaded vehicle
            # =================================================

            for _, row in dataframe.iterrows():

                vehicle_code = str(
                    row["vehicle_code"]
                ).strip()

                make_name = str(
                    row["make"]
                ).strip()

                model_name = str(
                    row["model"]
                ).strip()


                
                # =============================================
                # 9. Find existing vehicle make
                # =============================================

                make_id = connection.execute(
                    text("""
                        SELECT make_id
                        FROM dbo.vehicle_make
                        WHERE LOWER(LTRIM(RTRIM(make_name)))
                              =
                              LOWER(LTRIM(RTRIM(:make_name)))
                    """),
                    {
                        "make_name":
                            make_name
                    }
                ).scalar()


                # =============================================
                # 10. Create make if it does not exist
                # =============================================

                if make_id is None:

                    make_id = connection.execute(
                        text("""
                            INSERT INTO dbo.vehicle_make
                            (
                                make_name
                            )

                            OUTPUT INSERTED.make_id

                            VALUES
                            (
                                :make_name
                            )
                        """),
                        {
                            "make_name":
                                make_name
                        }
                    ).scalar_one()


                # =============================================
                # 11. Find model under that make
                # =============================================

                model_id = connection.execute(
                    text("""
                        SELECT model_id
                        FROM dbo.vehicle_model
                        WHERE make_id = :make_id
                          AND LOWER(
                                LTRIM(
                                    RTRIM(model_name)
                                )
                              )
                              =
                              LOWER(
                                LTRIM(
                                    RTRIM(:model_name)
                                )
                              )
                    """),
                    {
                        "make_id":
                            make_id,

                        "model_name":
                            model_name
                    }
                ).scalar()


                # =============================================
                # 12. Create model if necessary
                # =============================================

                if model_id is None:

                    model_id = connection.execute(
                        text("""
                            INSERT INTO dbo.vehicle_model
                            (
                                make_id,
                                model_name
                            )

                            OUTPUT INSERTED.model_id

                            VALUES
                            (
                                :make_id,
                                :model_name
                            )
                        """),
                        {
                            "make_id":
                                make_id,

                            "model_name":
                                model_name
                        }
                    ).scalar_one()


                # =============================================
                # 13. Calculate current derived information
                # =============================================

                model_year = int(
                    float(row["model_year"])
                )

                current_mileage = int(
                    float(row["current_mileage"])
                )

                current_vehicle_age = max(
                    date.today().year
                    - model_year,
                    1
                )

                mileage_per_year = (
                    current_mileage
                    /
                    current_vehicle_age
                )


                # =============================================
                # 14. Insert the new vehicle
                # =============================================

                vehicle_id = connection.execute(
                    text("""
                        INSERT INTO dbo.vehicle
                        (
                            vehicle_code,
                            model_id,
                            model_year,
                            current_mileage,
                            engine_hp,

                            transmission,
                            fuel_type,
                            drivetrain,
                            body_type,
                            exterior_color,
                            interior_color,
                            owner_count,

                            accident_history,
                            seller_type,
                            current_condition,
                            trim,

                            current_vehicle_age,
                            mileage_per_year,

                            import_id
                        )

                        OUTPUT INSERTED.vehicle_id

                        VALUES
                        (
                            :vehicle_code,
                            :model_id,
                            :model_year,
                            :current_mileage,
                            :engine_hp,

                            :transmission,
                            :fuel_type,
                            :drivetrain,
                            :body_type,
                            :exterior_color,
                            :interior_color,
                            :owner_count,

                            :accident_history,
                            :seller_type,
                            :current_condition,
                            :trim,

                            :current_vehicle_age,
                            :mileage_per_year,

                            :import_id
                        )
                    """),
                    {
                        "vehicle_code":
                            vehicle_code,

                        "model_id":
                            model_id,

                        "model_year":
                            model_year,

                        "current_mileage":
                            current_mileage,

                        "engine_hp":
                            int(float(row["engine_hp"])),

                        "transmission":
                            get_optional_value(
                                row,
                                "transmission"
                            ),

                        "fuel_type":
                            get_optional_value(
                                row,
                                "fuel_type"
                            ),

                        "drivetrain":
                            get_optional_value(
                                row,
                                "drivetrain"
                            ),

                        "body_type":
                            get_optional_value(
                                row,
                                "body_type"
                            ),

                        "exterior_color":
                            get_optional_value(
                                row,
                                "exterior_color"
                            ),

                        "interior_color":
                            get_optional_value(
                                row,
                                "interior_color"
                            ),

                        "owner_count":
                            get_optional_value(
                                row,
                                "owner_count"
                            ),

                        "accident_history":
                            str(
                                row["accident_history"]
                            ).strip(),

                        "seller_type":
                            get_optional_value(
                                row,
                                "seller_type"
                            ),

                        "current_condition":
                            str(
                                row["current_condition"]
                            ).strip(),

                        "trim":
                            get_optional_value(
                                row,
                                "trim"
                            ),

                        "current_vehicle_age":
                            current_vehicle_age,

                        "mileage_per_year":
                            mileage_per_year,

                        "import_id":
                             import_id
                    }
                ).scalar_one()


                # =============================================
                # 15. Convert lease dates
                # =============================================

                lease_start_date = pd.to_datetime(
                    row["lease_start_date"],
                    format="%Y-%m-%d"
                ).date()

                lease_end_date = pd.to_datetime(
                    row["lease_end_date"],
                    format="%Y-%m-%d"
                ).date()


                lease_term_months = (
                    calculate_lease_months(
                        lease_start_date,
                        lease_end_date
                    )
                )


                # =============================================
                # 16. Insert lease and link to portfolio import
                # =============================================

                connection.execute(
                    text("""
                        INSERT INTO dbo.vehicle_lease
                        (
                            vehicle_id,
                            lease_start_date,
                            lease_end_date,
                            lease_term_months,

                            expected_annual_mileage,
                            purchase_value,
                            original_rv,

                            data_source,
                            import_id
                        )

                        VALUES
                        (
                            :vehicle_id,
                            :lease_start_date,
                            :lease_end_date,
                            :lease_term_months,

                            :expected_annual_mileage,
                            :purchase_value,
                            :original_rv,

                            'IMPORT',
                            :import_id
                        )
                    """),
                    {
                        "vehicle_id":
                            vehicle_id,

                        "lease_start_date":
                            lease_start_date,

                        "lease_end_date":
                            lease_end_date,

                        "lease_term_months":
                            lease_term_months,

                        "expected_annual_mileage":
                            int(
                                float(
                                    row[
                                        "expected_annual_mileage"
                                    ]
                                )
                            ),

                        "purchase_value":
                            float(
                                row["purchase_value"]
                            ),

                        "original_rv":
                            float(
                                row["original_rv"]
                            ),

                        "import_id":
                            import_id
                    }
                )


                # =============================================
                # 17. Insert inspection only if supplied
                # =============================================

                inspection_value = get_optional_value(
                    row,
                    "last_inspection_date"
                )


                if inspection_value is not None:

                    inspection_date = pd.to_datetime(
                        inspection_value,
                        format="%Y-%m-%d"
                    ).date()


                    connection.execute(
                       text("""
                            INSERT INTO dbo.vehicle_inspection
                            (
                                vehicle_id,
                                last_inspection_date,
                                mileage,
                                vehicle_condition,
                                accident_history
                            )

                            VALUES
                            (
                                :vehicle_id,
                                :last_inspection_date,
                                :mileage,
                                :vehicle_condition,
                                :accident_history
                            )
                     """),
                    {
                            "vehicle_id":
                               vehicle_id,

                            "last_inspection_date":
                                inspection_date,

                            "mileage":
                               current_mileage,

                            "vehicle_condition":
                                str(
                                  row["current_condition"]
                                ).strip(),

                            "accident_history":
                                str(
                                  row["accident_history"]
                                ).strip()
                    }
                    )


                successful_rows += 1


            # =================================================
            # 18. Mark import as completed
            # =================================================

            connection.execute(
                text("""
                    UPDATE dbo.portfolio_import

                    SET
                        successful_rows = :successful_rows,
                        failed_rows = 0,
                        import_status = 'COMPLETED'

                    WHERE import_id = :import_id
                """),
                {
                    "successful_rows":
                        successful_rows,

                    "import_id":
                        import_id
                }
            )


        # ====================================================
        # 19. Transaction successfully committed
        # ====================================================

        return {
            "success": True,

            "import_id":
                import_id,

            "file_name":
                file.filename,

            "total_rows":
                len(dataframe),

            "successful_rows":
                successful_rows,

            "failed_rows":
                0,

            "message":
                "Portfolio imported successfully."
        }


    # ========================================================
    # 20. Any error rolls the transaction back
    # ========================================================

    except ValueError as exc:

        raise HTTPException(
            status_code=400,
            detail=str(exc)
        )


    except Exception as exc:

        raise HTTPException(
            status_code=500,
            detail=(
                "Portfolio import failed. "
                f"{str(exc)}"
            )
        )

from fastapi.responses import FileResponse


@app.get("/portfolio/imports")
def get_portfolio_imports(
    include_archived: bool = Query(default=False),
    current_user: dict = Depends(get_current_user)
):
    """Return only this user's active imports and optionally archived imports."""
    with engine.connect() as connection:
        rows = connection.execute(
            text("""
                SELECT
                    import_id,
                    file_name,
                    total_rows,
                    successful_rows,
                    failed_rows,
                                        import_status,
                                        is_archived
                FROM dbo.portfolio_import
                                WHERE user_id = :user_id
                                    AND import_status = 'COMPLETED'
                                    AND (:include_archived = 1 OR is_archived = 0)
                ORDER BY import_id DESC
                        """),
                        {
                                "user_id": current_user["user_id"],
                                "include_archived": include_archived
                        }
        ).mappings().all()

        return [
            {
                "import_id": row["import_id"],
                "file_name": row["file_name"],
                "total_rows": row["total_rows"],
                "successful_rows": row["successful_rows"],
                "failed_rows": row["failed_rows"],
                "import_status": row["import_status"],
                "is_archived": bool(row["is_archived"])
            }
            for row in rows
        ]


@app.post("/portfolio/imports/{import_id}/archive")
def archive_portfolio_import(
    import_id: int,
    current_user: dict = Depends(get_current_user)
):
    with engine.begin() as connection:
        result = connection.execute(
            text("""
                UPDATE dbo.portfolio_import
                                SET is_archived = 1
                WHERE import_id = :import_id
                  AND user_id = :user_id
                  AND import_status = 'COMPLETED'
                                    AND is_archived = 0
            """),
            {
                "import_id": import_id,
                "user_id": current_user["user_id"]
            }
        )

        if result.rowcount == 0:
            raise HTTPException(
                status_code=404,
                detail="Active portfolio import not found."
            )

    return {
        "import_id": import_id,
        "is_archived": True,
        "message": "Portfolio import archived. Its records are preserved and can be restored."
    }


@app.post("/portfolio/imports/{import_id}/restore")
def restore_portfolio_import(
    import_id: int,
    current_user: dict = Depends(get_current_user)
):
    with engine.begin() as connection:
        result = connection.execute(
            text("""
                UPDATE dbo.portfolio_import
                                SET is_archived = 0
                WHERE import_id = :import_id
                  AND user_id = :user_id
                                    AND import_status = 'COMPLETED'
                                    AND is_archived = 1
            """),
            {
                "import_id": import_id,
                "user_id": current_user["user_id"]
            }
        )

        if result.rowcount == 0:
            raise HTTPException(
                status_code=404,
                detail="Archived portfolio import not found."
            )

    return {
        "import_id": import_id,
        "is_archived": False,
        "message": "Portfolio import restored to your active portfolio."
    }


@app.get("/portfolio/import/template")
def download_portfolio_template(
    _current_user: dict = Depends(get_current_user)
):

    template_path = (
        TEMPLATE_DIR
        / "arvf_portfolio_import_sample.csv"
    )

    if not template_path.exists():
        raise HTTPException(
            status_code=404,
            detail="Portfolio import template file was not found."
        )

    return FileResponse(
        path=str(template_path),
        media_type="text/csv",
        filename="ARVF_Portfolio_Import_Data_Template.csv"
    )


#backend endpoint to retrieve a list of vehicles in the portfolio, including their latest known state, mileage, and lease information 
#and than the latest accepted forecast for each vehicle, if available. If no forecast is available, the status "Not Forecasted" will
# will be returned, if it is available that it will give updated forecast with rv gap if applicable and a suitable status. 
# The endpoint returns a list of vehicles with their details like vehicle id, code, make, model, latest mileage/condition
# and generate updated forecast with rv gap and status.

@app.get("/portfolio/vehicles")
def get_portfolio_vehicles(

    import_id: int | None = Query(default=None, ge=1),

    limit: int = Query(
        default=20,
        ge=1,
        le=100
    ),

    page: int = Query(
        default=1,
        ge=1
    ),

    search: str = Query(
        default=""
    ),

    status: str = Query(
        default="ALL"
    ),

    current_user: dict = Depends(get_current_user)
):

    offset = (page - 1) * limit

    # One additional row tells us whether
    # another page exists.
    fetch_count = limit + 1

    clean_search = search.strip()

    search_pattern = f"{clean_search}%"

    # If search is a pure number,
    # also allow searching exact vehicle_id.
    search_vehicle_id = (
        int(clean_search)
        if clean_search.isdigit()
        else None
    )


    with engine.connect() as connection:

        rows = connection.execute(

            text("""
                /*
                    STEP 1
                    Find only the small set of vehicles
                    required for the requested page.

                    We deliberately DO NOT load inspection
                    and forecast details yet.
                */

                WITH RankedVehicles AS
                (
                    SELECT
                        v.vehicle_id,
                        v.vehicle_code,
                        v.model_id,
                        v.model_year,
                        v.current_mileage,
                        v.engine_hp,
                        v.transmission,
                        v.fuel_type,
                        v.drivetrain,
                        v.body_type,
                        v.exterior_color,
                        v.interior_color,
                        v.owner_count,
                        v.accident_history,
                        v.seller_type,
                        v.current_condition,
                        vl.lease_id,
                        vl.import_id,
                        vl.lease_start_date,
                        vl.lease_end_date,
                        vl.expected_annual_mileage,
                        vl.purchase_value,
                        vl.original_rv,
                        mk.make_name,
                        mdl.model_name,
                        pi.file_name,
                        rf_status.forecast_id AS latest_forecast_id,
                        rf_status.rv_status AS latest_rv_status,
                        ROW_NUMBER() OVER
                        (
                            PARTITION BY v.vehicle_code
                            ORDER BY
                                CASE WHEN rf_status.forecast_id IS NOT NULL THEN 0 ELSE 1 END,
                                vl.import_id DESC,
                                v.vehicle_id DESC
                        ) AS duplicate_rank

                    FROM dbo.vehicle v
                    JOIN dbo.vehicle_model mdl ON mdl.model_id = v.model_id
                    JOIN dbo.vehicle_make mk ON mk.make_id = mdl.make_id
                    JOIN dbo.vehicle_lease vl ON vl.vehicle_id = v.vehicle_id
                    JOIN dbo.portfolio_import pi ON pi.import_id = vl.import_id

                    LEFT JOIN
                    (
                        SELECT
                            f.lease_id,
                            f.forecast_id,
                            f.rv_status,
                            ROW_NUMBER() OVER
                            (
                                PARTITION BY f.lease_id
                                ORDER BY f.forecast_date DESC, f.forecast_id DESC
                            ) AS forecast_rank
                        FROM dbo.rv_forecast f
                        WHERE f.forecast_status = 'ACCEPTED'
                    ) rf_status
                        ON rf_status.lease_id = vl.lease_id
                        AND rf_status.forecast_rank = 1

                    WHERE 
                         (:import_id IS NULL OR vl.import_id = :import_id)
                        AND pi.user_id = :user_id
                        AND pi.import_status = 'COMPLETED'
                        AND pi.is_archived = 0
                        AND
                        /* ============================
                           SEARCH
                        ============================ */
                        (
                            :search = ''
                            OR v.vehicle_code LIKE :search_pattern
                            OR mk.make_name LIKE :search_pattern
                            OR mdl.model_name LIKE :search_pattern
                            OR ( :search_vehicle_id IS NOT NULL AND v.vehicle_id = :search_vehicle_id )
                        )
                        AND
                        /* ============================
                           STATUS
                        ============================ */
                        (
                            :status = 'ALL'
                            OR (:status = 'NOT_FORECASTED' AND rf_status.forecast_id IS NULL)
                            OR (:status NOT IN ('ALL', 'NOT_FORECASTED') AND rf_status.rv_status = :status)
                        )
                ),
                CandidateVehicles AS
                (
                    SELECT *
                    FROM RankedVehicles
                    WHERE duplicate_rank = 1
                    ORDER BY vehicle_id
                    OFFSET :offset ROWS
                    FETCH NEXT :fetch_count ROWS ONLY
                )

                /*
                    STEP 2
                    Only after pagination has reduced the result to roughly 20-101 records
                    do we retrieve inspection and forecast details.
                */
                SELECT
                    cv.vehicle_id,
                    cv.vehicle_code,
                    cv.import_id,
                    cv.file_name,
                    cv.make_name,
                    cv.model_name,
                    cv.model_year,

                    COALESCE(vi.mileage, cv.current_mileage) AS current_mileage,
                    COALESCE(vi.vehicle_condition, cv.current_condition) AS current_condition,
                    vi.last_inspection_date,

                    cv.lease_start_date,
                    cv.lease_end_date,
                    cv.original_rv,

                    rf.predicted_lease_end_value,
                    rf.rv_gap,
                    rf.rv_status,
                    rf.forecast_date,
                    rf.review_status,
                    rf.potential_exposure

                FROM CandidateVehicles cv

                /* ==============================
                   LOAD INSPECTION (MOVED TO STEP 2)
                ============================== */
                OUTER APPLY
                (
                    SELECT TOP 1
                        i.mileage,
                        i.vehicle_condition,
                        i.last_inspection_date
                    FROM dbo.vehicle_inspection i
                    WHERE i.vehicle_id = cv.vehicle_id
                    ORDER BY i.last_inspection_date DESC, i.inspection_id DESC
                ) vi

                /* ==============================
                   LATEST ACCEPTED FORECAST
                ============================== */
                OUTER APPLY
                (
                    SELECT TOP 1
                        rf2.predicted_lease_end_value,
                        rf2.rv_gap,
                        rf2.rv_status,
                        rf2.forecast_date,
                        rf2.review_status,
                        rf2.potential_exposure
                    FROM dbo.rv_forecast rf2
                    WHERE rf2.lease_id = cv.lease_id
                      AND rf2.forecast_status = 'ACCEPTED'
                    ORDER BY rf2.forecast_date DESC, rf2.forecast_id DESC
                ) rf
                
                ORDER BY cv.vehicle_id

            """),

            {
                "import_id":
                    import_id,

                "user_id":
                    current_user["user_id"],

                "search":
                    clean_search,

                "search_pattern":
                    search_pattern,

                "search_vehicle_id":
                    search_vehicle_id,

                "status":
                    status,

                "offset":
                    offset,

                "fetch_count":
                    fetch_count
            }

        ).mappings().all()


        # Did we get the extra row?
        has_more = len(rows) > limit

        rows = rows[:limit]


        vehicles = [

            {
                "vehicle_id":
                    row["vehicle_id"],

                "vehicle_code":
                    row["vehicle_code"],

                "import_id":
                    row["import_id"],

                "file_name":
                    row["file_name"],

                "make":
                    row["make_name"],

                "model":
                    row["model_name"],

                "model_year":
                    row["model_year"],


                "current_mileage":
                    row["current_mileage"],

                "current_condition":
                    row["current_condition"],


                "last_inspection_date":
                    (
                        str(
                            row[
                                "last_inspection_date"
                            ]
                        )

                        if row[
                            "last_inspection_date"
                        ] is not None

                        else None
                    ),


                "lease_start_date":
                    str(
                        row["lease_start_date"]
                    ),

                "lease_end_date":
                    str(
                        row["lease_end_date"]
                    ),


                "original_rv":
                    float(
                        row["original_rv"]
                    ),


                "updated_forecast":
                    (
                        float(
                            row[
                                "predicted_lease_end_value"
                            ]
                        )

                        if row[
                            "predicted_lease_end_value"
                        ] is not None

                        else None
                    ),


                "rv_gap":
                    (
                        float(
                            row["rv_gap"]
                        )

                        if row["rv_gap"]
                        is not None

                        else None
                    ),


                "status":
                    (
                        row["rv_status"]

                        if row["rv_status"]
                        is not None

                        else "Not Forecasted"
                    ),


                "forecast_date":
                    (
                        str(
                            row["forecast_date"]
                        )

                        if row["forecast_date"]
                        is not None

                        else None
                    ),

                "review_status":
                    row["review_status"],

                "potential_exposure":
                    (
                        float(row["potential_exposure"])
                        if row["potential_exposure"] is not None
                        else None
                    )
            }

            for row in rows
        ]


        return {

            "items":
                vehicles,

            "page":
                page,

            "limit":
                limit,

            "has_more":
                has_more,

            "search":
                clean_search,

            "status":
                status
        }
# backend endpoint to retrieve detailed information about a specific vehicle,
# including its lease information, vehicle details, and the latest inspection data
# if available, if not than the orignal values from the vehicle table will be used
@app.get("/vehicles/{vehicle_id}/details")
def get_vehicle_details(vehicle_id: int,
                        import_id: int = Query(..., ge=1),
                        current_user: dict = Depends(get_current_user)
):

    with engine.connect() as connection:

        result = connection.execute(
            text("""
                SELECT
                  v.vehicle_id,
                  v.vehicle_code,

                  mk.make_name,
                  mdl.model_name,

                  v.model_year,

                  COALESCE(
                    vi.mileage,
                    v.current_mileage
                  ) AS current_mileage,

                  COALESCE(
                    vi.vehicle_condition,
                    v.current_condition
                  ) AS current_condition,

                  vl.lease_id,
                  vl.purchase_value,
                  vl.lease_start_date,
                  vl.lease_end_date,
                  vl.original_rv,
                  vl.lease_term_months,

                  vi.last_inspection_date,

                  rf.forecast_id,
                  rf.predicted_lease_end_value,
                  rf.rv_gap,
                  rf.potential_exposure,
                  rf.rv_status,
                  rf.review_status,
                  rf.forecast_date

                FROM dbo.vehicle v

                JOIN dbo.vehicle_model mdl
                    ON mdl.model_id = v.model_id

                JOIN dbo.vehicle_make mk
                    ON mk.make_id = mdl.make_id

                JOIN dbo.portfolio_import pi
                    ON pi.import_id = v.import_id
                   AND pi.user_id = :user_id
                   AND pi.import_status = 'COMPLETED'
                   AND pi.is_archived = 0

                LEFT JOIN dbo.vehicle_lease vl
                    ON vl.vehicle_id = v.vehicle_id
                    AND vl.import_id = :import_id

                OUTER APPLY
                (
                    SELECT TOP 1
                        last_inspection_date,
                        mileage,
                        vehicle_condition
                    FROM dbo.vehicle_inspection
                    WHERE vehicle_id = v.vehicle_id
                    ORDER BY last_inspection_date DESC,
                             inspection_id DESC
                ) vi

                OUTER APPLY
                (
                   SELECT TOP 1
                       forecast_id,
                       predicted_lease_end_value,
                       rv_gap,
                       potential_exposure,
                       rv_status,
                       review_status,
                       forecast_date
                  FROM dbo.rv_forecast
                  WHERE lease_id = vl.lease_id
                  AND forecast_status = 'ACCEPTED'
                  ORDER BY forecast_date DESC,
                          forecast_id DESC
                ) rf

                WHERE v.vehicle_id = :vehicle_id
                AND v.import_id = :import_id
            """),
            {"vehicle_id": vehicle_id,
             "user_id": current_user["user_id"],
             "import_id": import_id}
        ).mappings().first()

        if result is None:
            return {
                "message": "Vehicle not found"
            }

        # Use the latest inspection values if an inspection exists.
        # Otherwise use the original/current values from dbo.vehicle.

        current_mileage = result["current_mileage"]

        current_condition = result["current_condition"]

        last_inspection_date = (
            result["last_inspection_date"]
            if result["last_inspection_date"] is not None
            else None
        )        

        return {

            "vehicle_id": result["vehicle_id"],
            "vehicle_code": result["vehicle_code"],

            "make": result["make_name"],
            "model": result["model_name"],
            "model_year": result["model_year"],

            "current_mileage": current_mileage,
            "current_condition": current_condition,
            "last_inspection_date": last_inspection_date,

            "purchase_value": (
              float(result["purchase_value"])
              if result["purchase_value"] is not None
              else None
            ),

            "lease_start_date": (
              str(result["lease_start_date"])
              if result["lease_start_date"] is not None
              else None
            ),

           "lease_end_date": (
             str(result["lease_end_date"])
             if result["lease_end_date"] is not None
             else None
            ),

           "original_rv": (
             float(result["original_rv"])
             if result["original_rv"] is not None
             else None
            ),

           "updated_forecast": (
             float(result["predicted_lease_end_value"])
            if result["predicted_lease_end_value"] is not None
            else None
            ),

           "rv_gap": (
             float(result["rv_gap"])
             if result["rv_gap"] is not None
             else None
            ),

           "rv_status": (
             result["rv_status"]
             if result["rv_status"] is not None
             else "Not Forecasted"
            ),

           "current_inputs": {
            "current_mileage": current_mileage,
            "current_condition": current_condition,
            "last_inspection_date": last_inspection_date
           }

        }

        
    
        

class InspectionCreate(BaseModel):
    last_inspection_date: date
    mileage: int
    vehicle_condition: str

# backend endpoint to create a new vehicle inspection record for a specific vehicle.
# The endpoint first checks if the vehicle exists in the database. If it does, it saves
# the inspection data (inspection date, mileage, and vehicle condition) into the dbo.vehicle
#_inspection table and returns a success message along with the newely created inspection ID.
# If the vehicle does not exist, it raises a 404 HTTP exeption.
@app.post("/vehicles/{vehicle_id}/inspections")
def create_inspection(
    vehicle_id: int,
    inspection: InspectionCreate,
    import_id: int = Query(..., ge=1),
    current_user: dict = Depends(get_current_user)
):

    with engine.begin() as connection:

        # Check that the selected vehicle exists
        vehicle_exists = connection.execute(
            text("""
                SELECT vehicle_id
                FROM dbo.vehicle
                WHERE vehicle_id = :vehicle_id
                   AND import_id = :import_id
                                     AND EXISTS
                                     (
                                             SELECT 1
                                             FROM dbo.portfolio_import pi
                                             WHERE pi.import_id = :import_id
                                                 AND pi.user_id = :user_id
                                                 AND pi.import_status = 'COMPLETED'
                                                 AND pi.is_archived = 0
                                     )
            """),
            {
               "vehicle_id": vehicle_id,
                             "import_id": import_id,
                             "user_id": current_user["user_id"]
            }
        ).first()

        if vehicle_exists is None:
            raise HTTPException(
                status_code=404,
                detail="Vehicle not found"
            )

        # Save the three values entered on the mockup screen
        result = connection.execute(
            text("""
                INSERT INTO dbo.vehicle_inspection
                (
                    vehicle_id,
                    last_inspection_date,
                    mileage,
                    vehicle_condition
                )
                OUTPUT INSERTED.inspection_id
                VALUES
                (
                    :vehicle_id,
                    :last_inspection_date,
                    :mileage,
                    :vehicle_condition
                )
            """),
            {
                "vehicle_id": vehicle_id,
                "last_inspection_date": inspection.last_inspection_date,
                "mileage": inspection.mileage,
                "vehicle_condition": inspection.vehicle_condition
            }
        )

        inspection_id = result.scalar()

        return {
            "message": "Vehicle information saved successfully",
            "inspection_id": inspection_id
        }

@app.get("/model-info")
def get_model_info(
    _current_user: dict = Depends(get_current_user)
):

    with engine.connect() as connection:

        result = connection.execute(
            text("""
                SELECT TOP 1
                    model_version_id,
                    model_name,
                    version_name,
                    training_date,
                    status,
                    data_scope,
                    mae,
                    rmse,
                    r_squared,
                    notes
                FROM dbo.model_version
                ORDER BY model_version_id DESC
            """)
        ).mappings().first()

        if result is None:
            return {
                "message": "No model version has been registered yet"
            }

        return {
            "model_name": result["model_name"],
            "version": result["version_name"],

            "last_trained":
                str(result["training_date"])
                if result["training_date"] is not None
                else None,

            "status": result["status"],
            "data_scope": result["data_scope"],

            "metrics": {
                "rmse":
                    float(result["rmse"])
                    if result["rmse"] is not None else None,

                "mae":
                    float(result["mae"])
                    if result["mae"] is not None else None,

                "r_squared":
                    float(result["r_squared"])
                    if result["r_squared"] is not None else None
            },

            "strengths": [
                "Uses multiple vehicle characteristics to estimate market value.",
                "Ensemble model combines multiple regression models."
            ],

            "limitations": [
                "The model was initially trained to estimate vehicle market price rather than being trained directly on historical lease-end RV outcomes,"
                "To predict the future RV after lease end things such as projected mileage, projected vehicle age at lease end were synthatecally ceated and used as features for the model,"
                "Future market conditions are not explicitly modeled."
            ],

            "notes": result["notes"]
        }

class ForecastRequest(BaseModel):
    mileage: int

    vehicle_condition: Literal[
        "Excellent",
        "Good",
        "Fair"
    ]

    last_inspection_date: date

    expected_lease_end_condition: Literal[
        "Excellent",
        "Good",
        "Fair"
    ] | None = None
# backend endpoint to generate an updated forecast for a specific vehicle based on the latest inspection data
# The endpoint retrieves the vehicle and lease information from the database, saves the latest inspection data,
# builds the input for the prediction model, runs the prediction, finds the current model version, decides the
# review status, saves the forecast in the database, and returns the result to the frontend.  
@app.post("/vehicles/{vehicle_id}/forecast")
def generate_updated_forecast(
    vehicle_id: int,
    request: ForecastRequest,
    import_id: int = Query(..., ge=1),
    current_user: dict = Depends(get_current_user)
):

    with engine.begin() as connection:

        # =====================================================
        # 1. GET VEHICLE + LEASE INFORMATION
        # =====================================================

        row = connection.execute(
            text("""
                SELECT
                    v.vehicle_id,
                    v.vehicle_code,

                    mk.make_name,
                    mdl.model_name,

                    v.model_year,
                    
                    COALESCE(
                    vi.mileage,
                    v.current_mileage
                    ) AS current_mileage,
                    
                    COALESCE(
                    vi.vehicle_condition,
                    v.current_condition
                    ) AS current_condition,
                    
                    v.engine_hp,
                    v.transmission,
                    v.fuel_type,
                    v.drivetrain,
                    v.body_type,
                    v.exterior_color,
                    v.interior_color,
                    v.owner_count,
                    v.accident_history,
                    v.seller_type,
                    v.trim,

                    vl.lease_id,
                    vl.lease_end_date,
                    vl.expected_annual_mileage,
                    vl.original_rv

                FROM dbo.vehicle v

                JOIN dbo.vehicle_model mdl
                    ON mdl.model_id = v.model_id

                JOIN dbo.vehicle_make mk
                    ON mk.make_id = mdl.make_id

                JOIN dbo.vehicle_lease vl
                    ON vl.vehicle_id = v.vehicle_id
                    AND vl.import_id = :import_id

                JOIN dbo.portfolio_import pi
                    ON pi.import_id = vl.import_id
                   AND pi.user_id = :user_id
                   AND pi.import_status = 'COMPLETED'
                   AND pi.is_archived = 0
                
                OUTER APPLY
                   (
                     SELECT TOP 1
                         i.mileage,
                         i.vehicle_condition,
                         i.last_inspection_date

                     FROM dbo.vehicle_inspection i

                     WHERE i.vehicle_id = v.vehicle_id

                     ORDER BY
                      i.last_inspection_date DESC,
                      i.inspection_id DESC
                   ) vi

                     WHERE v.vehicle_id = :vehicle_id
                     AND v.import_id = :import_id
             """),
            {
                "vehicle_id": vehicle_id,
                "import_id": import_id,
                "user_id": current_user["user_id"]
            }
        ).mappings().first()


        # Vehicle does not exist
        if row is None:
            raise HTTPException(
                status_code=404,
                detail="Vehicle or lease not found"
            )

        if request.mileage < row["current_mileage"]:
           raise HTTPException(
              status_code=400,
              detail=(
                f"Inspection mileage cannot be lower than the "
                f"currently recorded mileage of "
                f"{row['current_mileage']}."
              )
           )


        # =====================================================
        # 2. SAVE LATEST INSPECTION
        # =====================================================

        connection.execute(
            text("""
                INSERT INTO dbo.vehicle_inspection
                (
                    vehicle_id,
                    last_inspection_date,
                    mileage,
                    accident_history,
                    vehicle_condition
                )
                VALUES
                (
                    :vehicle_id,
                    :last_inspection_date,
                    :mileage,
                    :accident_history,
                    :vehicle_condition
                )
            """),
            {
                "vehicle_id": vehicle_id,
                "last_inspection_date": request.last_inspection_date,
                "mileage": request.mileage,
                "accident_history":
                   row["accident_history"],
                "vehicle_condition":
                    request.vehicle_condition
            }
        )


        # =====================================================
        # 3. BUILD INPUT FOR prediction.py
        # =====================================================

        vehicle_input = {

            "make": row["make_name"],

            "model": row["model_name"],

            # Year is still needed by prediction.py
            # to calculate future vehicle age.
            "year": row["model_year"],

            # Latest mileage entered by analyst
            "mileage": request.mileage,

            "engine_hp": row["engine_hp"],

            "transmission": row["transmission"],

            "fuel_type": row["fuel_type"],

            "drivetrain": row["drivetrain"],

            "body_type": row["body_type"],

            "exterior_color": row["exterior_color"],

            "interior_color": row["interior_color"],

            "owner_count": row["owner_count"],

            "accident_history":
                row["accident_history"],

            "seller_type":
                row["seller_type"],

            # Latest condition entered by analyst
            "condition":
                request.vehicle_condition,

            "trim":
                row["trim"],

            # Lease information
            "lease_end_date":
                row["lease_end_date"],

            "expected_annual_mileage":
                row["expected_annual_mileage"],

            "original_rv":
                float(row["original_rv"])
        }

        if request.expected_lease_end_condition:
           vehicle_input["expected_lease_end_condition"] = (
             request.expected_lease_end_condition
         )


        # =====================================================
        # 4. RUN prediction.py
        # =====================================================

        try:

            forecast = predict_lease_end_value(
                vehicle_input
            )

        except ValueError as e:

            raise HTTPException(
                status_code=400,
                detail=str(e)
            )


        # =====================================================
        # 5. FIND CURRENT MODEL VERSION
        # =====================================================

        model_version_id = connection.execute(
            text("""
                SELECT TOP 1
                    model_version_id
                FROM dbo.model_version
                ORDER BY model_version_id DESC
            """)
        ).scalar()


        # =====================================================
        # 6. DECIDE REVIEW STATUS
        # =====================================================

        if forecast["rv_gap"] < 0:

            review_status = "REVIEW"

        else:

            review_status = "NORMAL"


        # Convert warning list into database text
        warnings = forecast[
            "extrapolation_warnings"
        ]

        warning_text = (
            " | ".join(warnings)
            if warnings
            else None
        )


        # =====================================================
        # 7. SAVE FORECAST IN rv_forecast
        # =====================================================

        forecast_id = connection.execute(
            text("""
                INSERT INTO dbo.rv_forecast
                (
                    lease_id,
                    model_version_id,

                    projected_mileage,
                    projected_vehicle_age,
                    projected_mileage_per_year,

                    assumed_condition,

                    predicted_lease_end_value,

                    rv_gap,
                    potential_exposure,

                    rv_status,
                    review_status,

                    warning_text
                )

                OUTPUT INSERTED.forecast_id

                VALUES
                (
                    :lease_id,
                    :model_version_id,

                    :projected_mileage,
                    :projected_vehicle_age,
                    :projected_mileage_per_year,

                    :assumed_condition,

                    :predicted_value,

                    :rv_gap,
                    :potential_exposure,

                    :rv_status,
                    :review_status,

                    :warning_text
                )
            """),
            {
                "lease_id":
                    row["lease_id"],

                "model_version_id":
                    model_version_id,

                "projected_mileage":
                    forecast["projected_mileage"],

                "projected_vehicle_age":
                    forecast["projected_vehicle_age"],

                "projected_mileage_per_year":
                    forecast[
                        "projected_mileage_per_year"
                    ],

                "assumed_condition":
                    forecast[
                        "assumed_lease_end_condition"
                    ],

                "predicted_value":
                    forecast[
                        "predicted_lease_end_value"
                    ],

                "rv_gap":
                    forecast["rv_gap"],

                "potential_exposure":
                    forecast[
                        "potential_rv_exposure"
                    ],

                "rv_status":
                    forecast["rv_status"],

                "review_status":
                    review_status,

                "warning_text":
                    warning_text
            }
        ).scalar()


        # =====================================================
        # 8. RETURN RESULT TO FRONTEND
        # =====================================================

        return {

            "forecast_id":
                forecast_id,

            "vehicle_id":
                vehicle_id,

            "vehicle_code":
                row["vehicle_code"],

            "original_rv":
                forecast["original_rv"],

            "updated_forecast":
                forecast[
                    "predicted_lease_end_value"
                ],

            "rv_gap":
                forecast["rv_gap"],

            "potential_rv_exposure":
                forecast[
                    "potential_rv_exposure"
                ],

            "rv_status":
                forecast["rv_status"],

            "review_status":
                review_status,

            "projected_mileage":
                forecast["projected_mileage"],

            "projected_vehicle_age":
                forecast["projected_vehicle_age"],

            "warnings":
                forecast[
                    "extrapolation_warnings"
                ]
        }

#endpoint to save a specific forecast to the portfolio. The endpoint first checks if the 
# forecast exists in the database. If it does, it updates the status of any older forecasts
# for the same lease to "GENERATED" and then updates the status of the selected forecast to
# "ACCEPTED". If the forecast does not exist, it raises a 404 HTTP exception.
@app.post("/forecasts/{forecast_id}/save")
def save_forecast_to_portfolio(
    forecast_id: int,
    current_user: dict = Depends(get_current_user)
):

    with engine.begin() as connection:

        forecast = connection.execute(
            text("""
                SELECT
                    forecast_id,
                    lease_id
                FROM dbo.rv_forecast
                                WHERE forecast_id = :forecast_id
                                    AND EXISTS
                                    (
                                            SELECT 1
                                            FROM dbo.vehicle_lease vl
                                            JOIN dbo.portfolio_import pi
                                                ON pi.import_id = vl.import_id
                                            WHERE vl.lease_id = dbo.rv_forecast.lease_id
                                                AND pi.user_id = :user_id
                                                AND pi.import_status = 'COMPLETED'
                                                AND pi.is_archived = 0
                                    )
            """),
            {
                                "forecast_id": forecast_id,
                                "user_id": current_user["user_id"]
            }
        ).mappings().first()

        if forecast is None:
            raise HTTPException(
                status_code=404,
                detail="Forecast not found"
            )

        # Remove ACCEPTED status from older forecasts
        # for this same lease.
        connection.execute(
            text("""
                UPDATE dbo.rv_forecast
                SET forecast_status = 'GENERATED'
                WHERE lease_id = :lease_id
                  AND forecast_status = 'ACCEPTED'
            """),
            {
                "lease_id": forecast["lease_id"]
            }
        )

        # Accept the selected forecast.
        connection.execute(
            text("""
                UPDATE dbo.rv_forecast
                SET forecast_status = 'ACCEPTED'
                WHERE forecast_id = :forecast_id
            """),
            {
                "forecast_id": forecast_id
            }
        )

        return {
            "message": "Forecast saved to portfolio successfully",
            "forecast_id": forecast_id,
            "forecast_status": "ACCEPTED"
        }