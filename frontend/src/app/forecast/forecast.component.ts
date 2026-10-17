import {
  Component,
  ChangeDetectorRef,
  OnInit
} from '@angular/core';

import {
  CommonModule
} from '@angular/common';

import {
  FormsModule
} from '@angular/forms';

import {
  ActivatedRoute,
  Router
} from '@angular/router';

import {
  finalize
} from 'rxjs';

import {
  ArvfApiService
} from '../services/arvf-api.service';


@Component({

  selector: 'app-forecast',

  standalone: true,

  imports: [
    CommonModule,
    FormsModule
  ],

  templateUrl:
    './forecast.component.html',

  styleUrl:
    './forecast.component.css'

})


export class ForecastComponent implements OnInit {

  // ==========================================
  // ACTIVE PORTFOLIO
  // ==========================================

  activeImportId:
    number | null = null;

  availableImports: any[] = [];

  importsLoading = false;

  importHistoryError = '';


  // ==========================================
  // VEHICLE SEARCH
  // ==========================================

  vehicleSearchText:
    string = '';

  searchingVehicles:
    boolean = false;

  vehicleSearchError:
    string = '';

  vehicleSearchResults:
    any[] = [];


  // ==========================================
  // SELECTED VEHICLE
  // ==========================================

  selectedVehicle:
    any = null;

  selectedVehicleDetails:
    any = null;

  loadingVehicleDetails:
    boolean = false;

  vehicleDetailsError:
    string = '';


  // ==========================================
  // FORECAST INPUTS
  // ==========================================

  currentMileage:
    number | null = null;

  currentCondition:
    string = '';

  lastInspectionDate:
    string = '';

  expectedLeaseEndCondition:
    string = '';


  // ==========================================
  // FORECAST GENERATION
  // ==========================================

  generatingForecast:
    boolean = false;

  forecastError:
    string = '';

  forecastResult:
    any = null;


  // ==========================================
  // FORECAST SAVE
  // ==========================================

  savingForecast:
    boolean = false;

  saveForecastError:
    string = '';

  forecastSaved:
    boolean = false;


  constructor(

    private api:
      ArvfApiService,

    private cdr:
      ChangeDetectorRef,

    private route:
      ActivatedRoute,

    private router:
      Router

  ) {

    const savedImportId =
      localStorage.getItem(
       'activeImportId'
      );


    if (savedImportId) {

      const parsedImportId =
        Number(savedImportId);


      if (
        Number.isFinite(parsedImportId) &&
          parsedImportId > 0
      ) {

        this.activeImportId =
          parsedImportId;

      }

    }

  }

  ngOnInit(): void {
    const importId = Number(
      this.route.snapshot.queryParamMap.get('import_id')
    );
    const vehicleId = Number(
      this.route.snapshot.queryParamMap.get('vehicle_id')
    );

    if (Number.isFinite(importId) && importId > 0) {
      this.activeImportId = importId;
      localStorage.setItem('activeImportId', String(importId));
    }

    if (
      Number.isFinite(vehicleId) &&
      vehicleId > 0 &&
      this.activeImportId !== null
    ) {
      this.selectVehicle({
        vehicle_id: vehicleId,
        vehicle_code: `Vehicle ID ${vehicleId}`
      });
    }

    this.loadImports();
  }

  loadImports(): void {
    this.importsLoading = true;
    this.importHistoryError = '';

    this.api.getPortfolioImports()
      .pipe(finalize(() => {
        this.importsLoading = false;
        this.cdr.detectChanges();
      }))
      .subscribe({
        next: (imports) => {
          this.availableImports = Array.isArray(imports) ? imports : [];
          if (
            this.activeImportId !== null &&
            !this.availableImports.some(
              (item) => Number(item.import_id) === this.activeImportId
            )
          ) {
            this.activeImportId = null;
            localStorage.removeItem('activeImportId');
          }
        },
        error: () => {
          this.availableImports = [];
          this.importHistoryError = 'Unable to load portfolio import history.';
        }
      });
  }

  selectImport(importId: number | null): void {
    this.activeImportId = importId;
    this.router.navigate([], {
      relativeTo: this.route,
      queryParams: {
        import_id: importId,
        vehicle_id: null
      },
      queryParamsHandling: 'merge',
      replaceUrl: true
    });

    if (importId !== null) {
      localStorage.setItem('activeImportId', String(importId));
    } else {
      localStorage.removeItem('activeImportId');
    }

    this.selectedVehicle = null;
    this.selectedVehicleDetails = null;
    this.vehicleSearchResults = [];
    this.forecastResult = null;
    this.forecastSaved = false;
    this.vehicleSearchError = '';
    this.vehicleDetailsError = '';
    this.forecastError = '';
    this.saveForecastError = '';
  }



  // ==========================================
  // SEARCH VEHICLES
  // ==========================================

  searchVehicles(): void {


    const search =
      this.vehicleSearchText.trim();


    this.vehicleSearchError = '';

    this.vehicleSearchResults = [];


    if (!search) {

      this.vehicleSearchError =
        'Enter a vehicle ID, code, make or model.';

      return;

    }
      if (this.activeImportId === null) {

      this.vehicleSearchError =
        'No active portfolio is selected. Import or select a portfolio first.';

      return;

      }


    this.searchingVehicles = true;


    this.api
      .searchVehicles(search, this.activeImportId)

      .pipe(

        finalize(() => {

          this.searchingVehicles = false;

          this.cdr.detectChanges();

        })

      )

      .subscribe({

        next: (response: any) => {


          /*
            Your search endpoint returns vehicle
            suggestions containing:

            vehicle_id
            vehicle_code

            This also safely handles either:
            - a direct array response
            - an object with items
          */

          if (
            Array.isArray(response)
          ) {

            this.vehicleSearchResults =
              response;

          }

          else if (
            response &&
            Array.isArray(response.items)
          ) {

            this.vehicleSearchResults =
              response.items;

          }

          else {

            this.vehicleSearchResults = [];

          }


          if (
            this.vehicleSearchResults.length === 0
          ) {

            this.vehicleSearchError =
              'No matching vehicle was found.';

          }


          this.cdr.detectChanges();

        },


        error: (error) => {

          console.error(
            'VEHICLE SEARCH ERROR:',
            error
          );


          this.vehicleSearchResults = [];


          if (
            error?.status === 0
          ) {

            this.vehicleSearchError =
              'Unable to connect to the ARVF backend.';

          }

          else {

            this.vehicleSearchError =
              'Unable to search vehicles. Please try again.';

          }


          this.cdr.detectChanges();

        }

      });

  }



  // ==========================================
  // SELECT VEHICLE
  // ==========================================

  selectVehicle(
    vehicle: any
  ): void {


    if (
      !vehicle ||
      vehicle.vehicle_id === null ||
      vehicle.vehicle_id === undefined
    ) {

      this.vehicleSearchError =
        'The selected vehicle does not contain a valid vehicle ID.';

      return;

    }


    this.selectedVehicle =
      vehicle;


    // Clear old state from another vehicle.
    this.selectedVehicleDetails =
      null;

    this.vehicleDetailsError =
      '';

    this.forecastError =
      '';

    this.forecastResult =
      null;

    this.forecastSaved =
      false;

    this.saveForecastError =
      '';


    this.loadVehicleDetails(
      vehicle.vehicle_id
    );

  }



  // ==========================================
  // LOAD SELECTED VEHICLE DETAILS
  // ==========================================

  loadVehicleDetails(
    vehicleId: number
  ): void {
  

    this.loadingVehicleDetails =
      true;

    this.vehicleDetailsError =
      '';
    
    if (this.activeImportId === null) {

      this.vehicleDetailsError =
        'No active portfolio is selected.';

      return;

    }

    this.api
      .getVehicleDetails(
        vehicleId,
        this.activeImportId
      )

      .pipe(

        finalize(() => {

          this.loadingVehicleDetails =
            false;

          this.cdr.detectChanges();

        })

      )

      .subscribe({

        next: (data: any) => {


          if (
            !data ||
            !data.vehicle_id
          ) {

            this.vehicleDetailsError =
              'Vehicle details could not be retrieved.';

            return;

          }


          this.selectedVehicleDetails =
            data;



          // ==================================
          // PREFILL EDITABLE FORECAST INPUTS
          // ==================================

          const inputs =
            data.current_inputs ?? {};


          this.currentMileage =
            inputs.current_mileage
            ??
            data.current_mileage
            ??
            null;


          this.currentCondition =
            inputs.current_condition
            ??
            data.current_condition
            ??
            '';


          const inspectionDate =
            inputs.last_inspection_date
            ??
            data.last_inspection_date
            ??
            '';


          this.lastInspectionDate =
            inspectionDate
              ? String(
                  inspectionDate
                ).substring(
                  0,
                  10
                )
              : '';


          this.expectedLeaseEndCondition =
            '';


          this.cdr.detectChanges();

        },


        error: (error) => {

          console.error(
            'VEHICLE DETAILS ERROR:',
            error
          );


          this.selectedVehicleDetails =
            null;


          if (
            error?.status === 404
          ) {

            this.vehicleDetailsError =
              'The selected vehicle was not found.';

          }

          else {

            this.vehicleDetailsError =
              'Unable to load vehicle details. Please try again.';

          }


          this.cdr.detectChanges();

        }

      });

  }



  // ==========================================
  // GENERATE UPDATED FORECAST
  // ==========================================

  generateForecast(): void {


    this.forecastError = '';

    this.saveForecastError = '';

    this.forecastSaved = false;

    if (this.activeImportId === null) {

      this.forecastError =
       'No active portfolio is selected.';

      return;

    }


    if (
      !this.selectedVehicleDetails
    ) {

      this.forecastError =
        'Select a vehicle before generating a forecast.';

      return;

    }


    if (
      this.currentMileage === null ||
      !Number.isFinite(
        Number(
          this.currentMileage
        )
      ) ||
      Number(
        this.currentMileage
      ) < 0
    ) {

      this.forecastError =
        'Enter a valid current mileage.';

      return;

    }


    if (
      !this.currentCondition ||
      ![
        'Excellent',
        'Good',
        'Fair'
      ].includes(
        this.currentCondition
      )
    ) {

      this.forecastError =
        'Select a valid current condition.';

      return;

    }


    if (
      !this.lastInspectionDate
    ) {

      this.forecastError =
        'Select the latest inspection date.';

      return;

    }


    if (
      this.expectedLeaseEndCondition &&
      ![
        'Excellent',
        'Good',
        'Fair'
      ].includes(
        this.expectedLeaseEndCondition
      )
    ) {

      this.forecastError =
        'Select a valid expected lease-end condition.';

      return;

    }



    const requestBody: any = {

      mileage:
        Number(
          this.currentMileage
        ),

      vehicle_condition:
        this.currentCondition,

      last_inspection_date:
        this.lastInspectionDate

    };


    if (
      this.expectedLeaseEndCondition
    ) {

      requestBody
        .expected_lease_end_condition =
          this.expectedLeaseEndCondition;

    }


    this.generatingForecast =
      true;

    this.forecastResult =
      null;


    this.api
      .generateForecast(

        this.selectedVehicleDetails
          .vehicle_id,

        requestBody,

        this.activeImportId

      )

      .pipe(

        finalize(() => {

          this.generatingForecast =
            false;

          this.cdr.detectChanges();

        })

      )

      .subscribe({

        next: (result: any) => {


          if (
            !result ||
            !result.forecast_id
          ) {

            this.forecastError =
              'The backend did not return a valid forecast result.';

            return;

          }


          this.forecastResult =
            result;


          this.cdr.detectChanges();

        },


        error: (error) => {

          console.error(
            'FORECAST ERROR:',
            error
          );


          if (
            error?.status === 400 &&
            error?.error?.detail
          ) {

            this.forecastError =
              error.error.detail;

          }

          else {

            this.forecastError =
              'Unable to generate the forecast. Please review the inputs and try again.';

          }


          this.cdr.detectChanges();

        }

      });

  }



  // ==========================================
  // SAVE / ACCEPT FORECAST
  // ==========================================

  saveForecast(): void {


    this.saveForecastError = '';


    if (
      !this.forecastResult ||
      !this.forecastResult.forecast_id
    ) {

      this.saveForecastError =
        'Generate a forecast before saving it.';

      return;

    }


    if (
      this.forecastSaved
    ) {

      return;

    }


    this.savingForecast =
      true;


    this.api
      .saveForecast(
        this.forecastResult
          .forecast_id
      )

      .pipe(

        finalize(() => {

          this.savingForecast =
            false;

          this.cdr.detectChanges();

        })

      )

      .subscribe({

        next: () => {

          this.forecastSaved =
            true;

          this.cdr.detectChanges();

        },


        error: (error) => {

          console.error(
            'SAVE FORECAST ERROR:',
            error
          );


          this.saveForecastError =
            'Unable to save the forecast. Please try again.';


          this.cdr.detectChanges();

        }

      });

  }



  // ==========================================
  // ADJUST INPUTS
  // ==========================================

  resetForecastResult(): void {


    this.forecastResult =
      null;

    this.forecastError =
      '';

    this.saveForecastError =
      '';

    this.forecastSaved =
      false;


    this.cdr.detectChanges();

  }

  backToPortfolio(): void {
    this.router.navigate(['/portfolio']);
  }
  
  getComparisonBarWidth(
  value: number
): number {

  if (
    !this.forecastResult
  ) {
    return 0;
  }


  const original =
    Number(
      this.forecastResult.original_rv
    ) || 0;


  const updated =
    Number(
      this.forecastResult.updated_forecast
    ) || 0;


  const maximum =
    Math.max(
      original,
      updated
    );


  if (
    maximum <= 0
  ) {
    return 0;
  }


  return Math.max(
    3,
    Math.min(
      100,
      (
        Number(value) /
        maximum
      ) * 100
    )
  );

}

}