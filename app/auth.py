from datetime import datetime, timedelta, timezone
import os
import re

from fastapi import (
    APIRouter,
    Depends,
    HTTPException
)
from fastapi.security import (
    HTTPAuthorizationCredentials,
    HTTPBearer
)
from pydantic import BaseModel, EmailStr
from passlib.context import CryptContext
from jose import JWTError, jwt
from sqlalchemy import text

from app.database import engine


router = APIRouter(
    prefix="/auth",
    tags=["Authentication"]
)


# ============================================================
# PASSWORD HASHING
# ============================================================

# ============================================================
# PASSWORD HASHING
# ============================================================

pwd_context = CryptContext(
    schemes=["bcrypt"],
    bcrypt__rounds=4,
    deprecated="auto"
)


# ============================================================
# JWT CONFIGURATION
# ============================================================

# For local development this fallback works,
# but preferably define ARVF_SECRET_KEY as an environment variable.
SECRET_KEY = os.getenv(
    "ARVF_SECRET_KEY",
    "CHANGE_THIS_TO_A_LONG_RANDOM_SECRET"
)

ALGORITHM = "HS256"

ACCESS_TOKEN_MINUTES = 60

bearer_scheme = HTTPBearer(auto_error=False)


# ============================================================
# LOGIN SECURITY
# ============================================================

MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 5


# ============================================================
# REQUEST MODELS
# ============================================================

class RegisterRequest(BaseModel):

    full_name: str
    email: EmailStr
    password: str
    confirm_password: str


class LoginRequest(BaseModel):

    email: EmailStr
    password: str


# ============================================================
# PASSWORD VALIDATION
# ============================================================

def validate_password(
    password: str,
    email: str
):

    errors = []


    if len(password) < 8:

        errors.append(
            "Password must contain at least 8 characters."
        )


    if len(password) > 50:

        errors.append(
            "Password cannot exceed 50 characters."
        )


    if not re.search(
        r"[A-Z]",
        password
    ):

        errors.append(
            "Password must contain an uppercase letter."
        )


    if not re.search(
        r"[a-z]",
        password
    ):

        errors.append(
            "Password must contain a lowercase letter."
        )


    if not re.search(
        r"\d",
        password
    ):

        errors.append(
            "Password must contain a number."
        )


    # Clean special-character validation
    if not re.search(
        r"""[!@#$%^&*()_+\-=\[\]{};':"\\|,.<>/?]""",
        password
    ):

        errors.append(
            "Password must contain a special character."
        )


    if " " in password:

        errors.append(
            "Password cannot contain spaces."
        )


    email_name = (
        email
        .split("@")[0]
        .lower()
    )


    if (
        len(email_name) >= 4
        and
        email_name in password.lower()
    ):

        errors.append(
            "Password should not contain your email name."
        )


    return errors


# ============================================================
# FULL NAME / EMAIL MATCH VALIDATION
# ============================================================

def email_matches_full_name(
    full_name: str,
    email: str
) -> bool:

    email_username = (
        email
        .split("@")[0]
        .strip()
        .lower()
    )


    name_parts = [

        part.lower()

        for part in
        full_name.strip().split()

        if len(part) >= 3
    ]


    if not name_parts:

        return False


    return any(

        part in email_username

        for part in name_parts
    )


# ============================================================
# JWT CREATION
# ============================================================

def create_access_token(
    user_id: int,
    email: str
):
    expires_at = (
        datetime.now(timezone.utc)
        + timedelta(minutes=ACCESS_TOKEN_MINUTES)
    )

    payload = {
        "sub": str(user_id),
        "email": email,
        "exp": expires_at
    }

    return jwt.encode(
        payload,
        SECRET_KEY,
        algorithm=ALGORITHM
    )


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme)
) -> dict:
    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail="Authentication required.",
            headers={"WWW-Authenticate": "Bearer"}
        )

    try:
        payload = jwt.decode(
            credentials.credentials,
            SECRET_KEY,
            algorithms=[ALGORITHM]
        )
        user_id = int(payload["sub"])
    except (JWTError, KeyError, TypeError, ValueError):
        raise HTTPException(
            status_code=401,
            detail="Your session is invalid or expired. Please sign in again.",
            headers={"WWW-Authenticate": "Bearer"}
        )

    with engine.connect() as connection:
        user = connection.execute(
            text("""
                SELECT user_id, email
                FROM dbo.app_user
                WHERE user_id = :user_id
                  AND is_active = 1
            """),
            {"user_id": user_id}
        ).mappings().first()

    if user is None:
        raise HTTPException(
            status_code=401,
            detail="This account is unavailable. Please sign in again.",
            headers={"WWW-Authenticate": "Bearer"}
        )

    return {
        "user_id": user["user_id"],
        "email": user["email"]
    }


# ============================================================
# REGISTER
# ============================================================

@router.post("/register")
def register_user(
    request: RegisterRequest
):

    full_name = (
        request.full_name
        .strip()
    )


    email = (
        str(request.email)
        .strip()
        .lower()
    )


    # --------------------------------------------------------
    # 1. Validate full name
    # --------------------------------------------------------

    if len(full_name) < 2:

        raise HTTPException(
            status_code=400,
            detail="Please enter a valid full name."
        )


    # --------------------------------------------------------
    # 2. Require password confirmation
    # --------------------------------------------------------

    if request.password != request.confirm_password:

        raise HTTPException(
            status_code=400,
            detail="Passwords do not match."
        )


    # --------------------------------------------------------
    # 3. Validate password security
    # --------------------------------------------------------

    password_errors = validate_password(
        request.password,
        email
    )


    if password_errors:

        raise HTTPException(
            status_code=400,
            detail=password_errors
        )


    # --------------------------------------------------------
    # 4. Check email matches at least one part of full name
    # --------------------------------------------------------

    if not email_matches_full_name(
        full_name,
        email
    ):

        raise HTTPException(
            status_code=400,
            detail=(
                "Your email address should contain "
                "at least one part of your full name."
            )
        )
    # ----------------------------------------------------
    # 5. Hash password
    # --------------------------------------------------------

    password_hash = (
        pwd_context.hash(
            request.password
        )
    )

    # --------------------------------------------------------
    # 6. Check duplicate email and create account
    # --------------------------------------------------------

    with engine.begin() as connection:

        existing_user = connection.execute(

            text("""
                SELECT user_id
                FROM dbo.app_user
                WHERE LOWER(email) = LOWER(:email)
            """),

            {
                "email": email
            }

        ).scalar()


        if existing_user is not None:

            raise HTTPException(
                status_code=409,
                detail=(
                    "An account with this email "
                    "already exists."
                )
            )

        
        user_id = connection.execute(

            text("""
                INSERT INTO dbo.app_user
                (
                    full_name,
                    email,
                    password_hash
                )

                OUTPUT INSERTED.user_id

                VALUES
                (
                    :full_name,
                    :email,
                    :password_hash
                )
            """),

            {
                "full_name":
                    full_name,

                "email":
                    email,

                "password_hash":
                    password_hash
            }

        ).scalar_one()


    return {

        "message":
            "Account created successfully.",

        "user": {

            "user_id":
                user_id,

            "full_name":
                full_name,

            "email":
                email
        }
    }


# ============================================================
# LOGIN
# ============================================================

@router.post("/login")
def login_user(
    request: LoginRequest
):

    email = (
        str(request.email)
        .strip()
    )


    with engine.begin() as connection:

        user = connection.execute(

            text("""
                SELECT
                    user_id,
                    full_name,
                    email,
                    password_hash,
                    failed_login_attempts,
                    locked_until,
                    email_verified,
                    is_active

                FROM dbo.app_user

                    WHERE email COLLATE Latin1_General_100_CS_AS
                        = :email COLLATE Latin1_General_100_CS_AS
            """),

            {
                "email":
                    email
            }

        ).mappings().first()


        # ----------------------------------------------------
        # Do not reveal whether an email exists
        # ----------------------------------------------------

        if user is None:

            raise HTTPException(
                status_code=401,
                detail="Invalid email or password."
            )


        # ----------------------------------------------------
        # Check account status
        # ----------------------------------------------------

        if not user["is_active"]:

            raise HTTPException(
                status_code=403,
                detail=(
                    "This account is currently disabled."
                )
            )


        now = (
            datetime.now(timezone.utc)
        )


        # ----------------------------------------------------
        # Check account lockout
        # ----------------------------------------------------

        if user["locked_until"] is not None:

            locked_until = (
                user["locked_until"]
            )


            if locked_until.tzinfo is None:

                locked_until = (
                    locked_until.replace(
                        tzinfo=timezone.utc
                    )
                )


            if locked_until > now:

                raise HTTPException(
                    status_code=423,
                    detail=(
                        "Too many failed login attempts. "
                        "Please try again later."
                    )
                )


        # ----------------------------------------------------
        # Verify password
        # ----------------------------------------------------

        password_valid = (
            pwd_context.verify(
                request.password,
                user["password_hash"]
            )
        )


        if not password_valid:

            attempts = (

                user["failed_login_attempts"]
                + 1
            )


            if attempts >= MAX_FAILED_ATTEMPTS:

                locked_until = (

                    now

                    + timedelta(
                        minutes=LOCKOUT_MINUTES
                    )
                )


                connection.execute(

                    text("""
                        UPDATE dbo.app_user

                        SET
                            failed_login_attempts = 0,
                            locked_until = :locked_until

                        WHERE user_id = :user_id
                    """),

                    {
                        "locked_until":
                            locked_until,

                        "user_id":
                            user["user_id"]
                    }

                )


            else:

                connection.execute(

                    text("""
                        UPDATE dbo.app_user

                        SET
                            failed_login_attempts = :attempts

                        WHERE user_id = :user_id
                    """),

                    {
                        "attempts":
                            attempts,

                        "user_id":
                            user["user_id"]
                    }

                )


            raise HTTPException(
                status_code=401,
                detail="Invalid email or password."
            )


        # ----------------------------------------------------
        # Successful login
        # ----------------------------------------------------

        connection.execute(

            text("""
                UPDATE dbo.app_user

                SET
                    failed_login_attempts = 0,
                    locked_until = NULL,
                    last_login_at = SYSUTCDATETIME()

                WHERE user_id = :user_id
            """),

            {
                "user_id":
                    user["user_id"]
            }

        )


        # ----------------------------------------------------
        # Create access token
        # ----------------------------------------------------

        access_token = (
            create_access_token(
                user["user_id"],
                user["email"]
            )
        )


        return {

            "access_token":
                access_token,

            "token_type":
                "bearer",

            "user": {

                "user_id":
                    user["user_id"],

                "full_name":
                    user["full_name"],

                "email":
                    user["email"]
            }
        }