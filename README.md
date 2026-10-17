# ARVF Engine

**ARVF Engine (Automotive Residual Value Forecasting Engine)** is a prototype decision-support application for automotive leasing.

It helps an analyst import a vehicle portfolio using CSV or XLSX file, review vehicle and lease information, generate an updated lease-end value estimate, and compare that estimate with the vehicle's original residual value (RV).

---

## What problem does it address?

In vehicle leasing, an original residual value is set when the lease begins.

If the expected vehicle value at lease end is lower than that original RV, the vehicle may represent potential residual-value exposure.

This application provides that same workflow that how much an item is at risk at the lease end, by calculating the potential RV exposure by subtracting the expected future RV of vehicle with the it's orignal RV.

It uses different trained ML models, trained to predict the RV of vehicle based on it's characteristics and than uses sythetically calculated values like projected mileage/mileage per year/vehicle age to calculate the estimated future RV of the vehicle

---

## Main Workflow

1. Sign in to the application.
2. Import a vehicle portfolio using CSV or XLSX.
3. Review the portfolio summary and vehicle records.
4. Open an individual vehicle to inspect its vehicle and lease information.
5. Generate an updated lease-end value estimate.
6. Compare the estimate with the original RV.
7. Review the RV gap and potential exposure.
8. Save accepted forecasts for later portfolio review.
9. Review the trained model information, the user guide on how predictions are generated step by step, honest strengths and limitations of the application and link to the kaggle notebook containing all trained models

---

## Main Features

- User registration and login
- JWT-based authentication
- CSV/XLSX portfolio import and validation
- Portfolio summary
- Vehicle search and filtering
- Paginated vehicle records
- Vehicle detail view
- Inspection data support
- Lease-end forecast generation
- Original RV vs updated forecast comparison
- Potential RV exposure calculation
- Forecast saving
- Portfolio import history and archive/restore support
- Model information and transparency page

---

## Machine Learning Model

The forecasting workflow uses a **Voting Regressor** built from:

- XGBoost
- LightGBM
- CatBoost

The trained model estimates **vehicle market price** using vehicle characteristics such as mileage, age, condition, make, model, engine information and other vehicle attributes.

ARVF then applies the model to a projected lease-end vehicle state to support the residual-value comparison.

---

## Important Limitation

ARVF is currently a prototype.

The machine-learning model was trained for **vehicle market-price prediction** using a public vehicle dataset. It was not directly trained and validated on historical commercial lease-end residual values.

Because of this, the application should currently be treated as a **decision-support and demonstration system**, rather than a production-grade financial valuation tool.

A stronger real-world version would require validation and possible retraining using historical leasing data with known lease-end outcomes.

---

## Technology Stack

### Frontend
- Angular
- TypeScript
- HTML
- CSS
- RxJS

### Backend
- Python
- FastAPI
- SQLAlchemy

### Database
- Microsoft SQL Server

### Machine Learning
- scikit-learn
- XGBoost
- LightGBM
- CatBoost
- pandas
- NumPy

### Authentication
- JWT
- Passlib / bcrypt

---

## Project Architecture

```text
Angular Frontend
        ↓
FastAPI REST API
        ↓
SQL Server Database
        ↓
Prediction Pipeline
        ↓
Voting Regressor
```

## How to run project locally

- From the main project directory, install the Python dependencies:
```text
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

- Start the FAST API backend
```text
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8001
```
Backend runs locally at:
```text
http://127.0.0.1:8001
```
FastAPI Swagger documentation is available at:
```text
http://127.0.0.1:8001/docs
```

- Once FAST API opens and runs on the browser open new terminal with directory setup as:
```text
cd frontend
```

- Once directory is setup open the angular frontend page using command:
```text
npm.cmd start
```

If Angular reports that port `4200` is already in use, stop the process currently using that port using following commands in the terminal:
```text
netstat -ano | findstr :4200
taskkill /PID 12345 /F
```
(Replace the 12345 number with the number shown on the first line where listening is written)

Once process is stopped than reopen the frontend page using the command
```text
npm.cmd start
```

## Conclusion

Overall this project demonstrates how:

- machine learning can be integrated into a full-stack application
- vehicle and lease information can be managed through a database
- portfolio-level residual-value risk can be reviewed through a frontend interface
- ML predictions can be connected with business decision-support workflows
- model assumptions and limitations can be communicated transparently



