import { Router } from '@angular/router';
import {
  Component,
  OnDestroy,
  OnInit,
  ChangeDetectorRef
} from '@angular/core';

import {
  CommonModule
} from '@angular/common';

import {
  FormsModule
} from '@angular/forms';

import {
  Subscription,
  finalize
} from 'rxjs';

import {
  ArvfApiService
} from '../services/arvf-api.service';


@Component({

  selector:
    'app-portfolio',

  standalone:
    true,

  imports: [
    CommonModule,
    FormsModule
  ],

  templateUrl:
    './portfolio.component.html',

  styleUrl:
    './portfolio.component.css'

})

export class PortfolioComponent
    implements OnInit, OnDestroy {


  activeImportId:
    number | null = null;

  availableImports: any[] = [];

  archivedImports: any[] = [];

  showArchivedImports = false;

  archiveInProgressId: number | null = null;

  restoreInProgressId: number | null = null;

  importManagerError = '';

  importManagerMessage = '';

  importsLoading = false;

  importHistoryError = '';

  selectedFile:
    File | null = null;

  validationResult:
    any = null;

  importError:
    string = '';

  importSuccessMessage:
    string = '';

  showImportPanel:
    boolean = true;


  // ==========================================
  // PORTFOLIO DATA
  // ==========================================

  summary: any = null;

  vehicles: any[] = [];


  // ==========================================
  // SEARCH / FILTER / PAGINATION
  // ==========================================

  selectedLimit:
    number = 20;

  searchText:
    string = '';

  selectedStatus:
    string = 'ALL';

  currentPage:
    number = 1;

  hasMore:
    boolean = false;


  // ==========================================
  // LOADING STATES
  // ==========================================

  loadingSummary:
    boolean = false;

  loadingVehicles:
    boolean = false;


  // ==========================================
  // MESSAGES
  // ==========================================

  summaryError:
    string = '';

  vehicleError:
    string = '';

  informationMessage:
    string = '';

  emptyResultMessage:
    string = '';


  // ==========================================
  // CURRENT VEHICLE REQUEST
  // ==========================================

  private vehicleRequest?:
    Subscription;


  constructor(
  private api: ArvfApiService,
  private router: Router,
  private cdr: ChangeDetectorRef
  ) {}
  
  // ==========================================
  // PAGE START
  // ==========================================

  ngOnInit(): void {

  const savedImportId =
    localStorage.getItem('activeImportId');

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

  this.loadImports();

  if (this.activeImportId !== null) {
    this.loadPortfolio();
  }
  }

  loadPortfolio(): void {

  if (this.activeImportId === null) {

    this.summary = null;
    this.vehicles = [];
    this.hasMore = false;

    return;
  }

  this.loadSummary();
  this.loadVehicles();
  }

  loadImports(): void {
    this.importsLoading = true;
    this.importHistoryError = '';

    this.api.getPortfolioImports(true)
      .pipe(finalize(() => {
        this.importsLoading = false;
        this.cdr.detectChanges();
      }))
      .subscribe({
        next: (imports) => {
          const importRecords = Array.isArray(imports) ? imports : [];
          this.availableImports = importRecords.filter(
            (item) => item.import_status === 'COMPLETED' && !item.is_archived
          );
          this.archivedImports = importRecords.filter(
            (item) => item.import_status === 'COMPLETED' && item.is_archived
          );
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

  toggleArchivedImports(): void {
    this.showArchivedImports = !this.showArchivedImports;
    this.importManagerError = '';
    this.importManagerMessage = '';
  }

  archiveImport(importItem: any): void {
    if (!importItem) {
      return;
    }

    const confirmed = window.confirm(
      `Archive "${importItem.file_name}"? Its records and forecasts will be preserved, removed from your active portfolio, and restorable later.`
    );

    if (!confirmed) {
      return;
    }

    this.archiveInProgressId = Number(importItem.import_id);
    this.importManagerError = '';
    this.importManagerMessage = '';

    this.api.archivePortfolioImport(Number(importItem.import_id))
      .pipe(finalize(() => {
        this.archiveInProgressId = null;
        this.cdr.detectChanges();
      }))
      .subscribe({
        next: () => {
          if (this.activeImportId === Number(importItem.import_id)) {
            this.activeImportId = null;
            localStorage.removeItem('activeImportId');
          }
          this.importManagerMessage = `${importItem.file_name} was archived. Its records have not been deleted.`;
          this.loadImports();
          this.loadPortfolio();
        },
        error: (error) => {
          this.importManagerError = error?.error?.detail
            ?? 'Unable to archive this import. No portfolio records were deleted.';
        }
      });
  }

  restoreImport(importItem: any): void {
    this.restoreInProgressId = Number(importItem.import_id);
    this.importManagerError = '';
    this.importManagerMessage = '';

    this.api.restorePortfolioImport(Number(importItem.import_id))
      .pipe(finalize(() => {
        this.restoreInProgressId = null;
        this.cdr.detectChanges();
      }))
      .subscribe({
        next: () => {
          this.importManagerMessage = `${importItem.file_name} was restored to your active portfolio.`;
          this.loadImports();
          this.loadPortfolio();
        },
        error: (error) => {
          this.importManagerError = error?.error?.detail
            ?? 'Unable to restore this import.';
        }
      });
  }

  selectImport(importId: number | null): void {
    this.activeImportId = importId;
    if (importId !== null) {
      localStorage.setItem('activeImportId', String(importId));
    } else {
      localStorage.removeItem('activeImportId');
    }
    this.currentPage = 1;
    this.loadPortfolio();
  }

  // ==========================================
// FILE SELECTED
// ==========================================

onFileSelected(
  event: Event
): void {

  const input =
    event.target as HTMLInputElement;

  if (
    input.files &&
    input.files.length > 0
  ) {

    this.selectedFile =
      input.files[0];

    // Reset previous messages/results
    this.validationResult = null;

    this.importError = '';

    this.importSuccessMessage = '';

  }

}


// ==========================================
// CANCEL SELECTED IMPORT
// ==========================================

cancelImport(): void {

  this.selectedFile = null;

  this.validationResult = null;

  this.importError = '';

  this.importSuccessMessage = '';

}


// ==========================================
// VALIDATE PORTFOLIO FILE
// ==========================================

validateImport(): void {

  if (!this.selectedFile) {

    this.importError =
      'Please select a CSV or XLSX file first.';

    return;
  }


  this.importError = '';

  this.importSuccessMessage = '';


  this.api
    .validatePortfolioImport(
      this.selectedFile
    )
    .subscribe({

      next: (response: any) => {

        this.validationResult =
          response;

        if (response.valid === true) {

          this.importSuccessMessage =
            'Portfolio file validated successfully.';

        }

        else {

          this.importError = '';

        }

        this.cdr.detectChanges();

      },

      error: (error: any) => {

        console.error(
          'PORTFOLIO VALIDATION ERROR:',
          error
        );

        this.validationResult = null;

        this.importError =
          error?.error?.detail
          ??
          'Unable to validate portfolio file.';

        this.cdr.detectChanges();

      }

    });

}


// ==========================================
// IMPORT PORTFOLIO
// ==========================================

importPortfolio(): void {

  if (!this.selectedFile) {

    this.importError =
      'Please select a CSV or XLSX file first.';

    return;
  }


  // Optional safety:
  // Do not import if validation already says invalid.
  if (
    this.validationResult &&
    this.validationResult.valid === false
  ) {

    this.importError =
      'Please fix the validation errors before importing.';

    return;
  }


  this.importError = '';

  this.importSuccessMessage = '';


  this.api
    .importPortfolio(
      this.selectedFile
    )
    .subscribe({

      next: (response: any) => {

        // ----------------------------------
        // Save newly created portfolio ID
        // ----------------------------------

        // ----------------------------------
        // Remember active portfolio
        // after browser refresh
        // ----------------------------------

        localStorage.setItem(
          'activeImportId',
          response.import_id.toString()
        );

        this.activeImportId =
          Number(response.import_id);

        this.showImportPanel = false;


        // ----------------------------------
        // Reset pagination
        // ----------------------------------

        this.currentPage = 1;


        // ----------------------------------
        // Success message
        // ----------------------------------

        this.importSuccessMessage =
          response.message
          ??
          'Portfolio imported successfully.';


        // ----------------------------------
        // Clear validation state
        // ----------------------------------

        this.validationResult = null;

        this.loadImports();


        // ----------------------------------
        // Load imported portfolio
        // ----------------------------------

        this.loadPortfolio();


        this.cdr.detectChanges();

      },

      error: (error: any) => {

        console.error(
          'PORTFOLIO IMPORT ERROR:',
          error
        );

        this.importError =
          error?.error?.detail
          ??
          'Unable to import portfolio.';

        this.cdr.detectChanges();

      }

    });

}

openImportPanel(): void {

  this.showImportPanel = true;

  this.importError = '';

  this.importSuccessMessage = '';

}

closeImportPanel(): void {

  this.cancelImport();

  this.showImportPanel = false;

}

downloadTemplate(): void {

  this.api
    .downloadPortfolioTemplate()
    .subscribe({

      next: (blob: Blob) => {
        const url =
          window.URL.createObjectURL(blob);

        const link =
          document.createElement('a');

        link.href = url;

        link.download =
          'ARVF_Portfolio_Import_Template.csv';

        link.click();

        window.URL.revokeObjectURL(url);

      },

      error: (error: any) => {

        console.error(
          'TEMPLATE DOWNLOAD ERROR:',
          error
        );

        this.importError =
          'Unable to download the portfolio template.';

        this.cdr.detectChanges();

      }

    });

}




  // ==========================================
  // PAGE DESTROY
  // ==========================================

  ngOnDestroy(): void {

    this.vehicleRequest
      ?.unsubscribe();

  }


  // ==========================================
  // LOAD SUMMARY
  // ==========================================

  loadSummary(): void {
     this.loadingSummary = true;
     this.summaryError = '';

     this.api
      .getPortfolioSummary(this.activeImportId)

      .pipe(

        finalize(() => {

           this.loadingSummary = false;

           this.cdr.detectChanges();

        })

      )

      .subscribe({

        next: (data) => {

          this.summary = data;

        },

        error: (error) => {

          console.error(
            'SUMMARY ERROR:',
            error
          );

          this.summaryError =
            'Unable to load portfolio summary.';

        }

      });

  }
  // ==========================================
  // LOAD VEHICLES
  // ==========================================

  loadVehicles(): void {
  // ==========================================
  // 1. VALIDATE VEHICLES PER PAGE
  // Backend accepts only 1 to 100.
  // ==========================================

  if (
    !Number.isFinite(this.selectedLimit)
  ) {

    this.selectedLimit = 20;

  }


  this.selectedLimit =
    Math.floor(this.selectedLimit);


  if (
    this.selectedLimit < 1
  ) {

    this.selectedLimit = 1;

  }


  if (
    this.selectedLimit > 100
  ) {

    this.selectedLimit = 100;

  }



  // ==========================================
  // 2. VALIDATE CURRENT PAGE
  // Backend requires page >= 1.
  // ==========================================

  if (
    !Number.isFinite(this.currentPage)
    ||
    this.currentPage < 1
  ) {

    this.currentPage = 1;

  }


  this.currentPage =
    Math.floor(this.currentPage);



  // ==========================================
  // 3. PREPARE SEARCH VALUE
  //
  // Backend supports:
  // - exact numeric vehicle_id
  // - vehicle_code prefix
  // - make prefix
  // - model prefix
  // ==========================================

  const cleanSearch =
    (
      this.searchText ?? ''
    ).trim();



  // ==========================================
  // 4. PREPARE STATUS
  //
  // ALL             -> all vehicles
  // NOT_FORECASTED  -> no accepted forecast
  // Other values    -> matched against rv_status
  // ==========================================

  const cleanStatus =
    (
      this.selectedStatus ?? ''
    ).trim();


  if (
    cleanStatus === ''
  ) {

    this.selectedStatus = 'ALL';

  }



  // ==========================================
  // 5. CANCEL PREVIOUS VEHICLE REQUEST
  //
  // Prevents an older request from updating
  // the table after a newer search/filter.
  // ==========================================

  this.vehicleRequest
    ?.unsubscribe();



  // ==========================================
  // 6. RESET PAGE STATE
  // ==========================================

  this.loadingVehicles = true;

  this.vehicleError = '';

  this.emptyResultMessage = '';

  this.informationMessage = '';



  // ==========================================
  // 7. CALL PORTFOLIO VEHICLES ENDPOINT
  // ==========================================

  this.vehicleRequest =

    this.api
      .getPortfolioVehicles(

        this.activeImportId,

        this.selectedLimit,

        this.currentPage,

        cleanSearch,

        this.selectedStatus

      )

      .pipe(

        finalize(() => {

          // API request has either completed,
          // failed or been cancelled.
          this.loadingVehicles = false;

          // Required in your application because
          // the view was previously remaining in
          // its loading state after HTTP completion.
          this.cdr.detectChanges();

        })

      )

      .subscribe({

  // ======================================
     // SUCCESS
  // ======================================

  next: (response) => {
          
    
          // ------------------------------------
          // Protect against malformed/missing
          // items returned by the API.
          // ------------------------------------

          if (
            response &&
            Array.isArray(response.items)
          ) {

            this.vehicles =
              response.items;

          }

          else {

            this.vehicles = [];

          }



          // ------------------------------------
          // Backend returns has_more because
          // it requests limit + 1 records.
          // ------------------------------------

          this.hasMore =
            response?.has_more === true;



          // ------------------------------------
          // No vehicles matched current
          // page/search/status.
          // ------------------------------------

          if (
            this.vehicles.length === 0
          ) {

            this.setEmptyResultMessage();

          }


          // ------------------------------------
          // Force table/cards to reflect the
          // newly returned vehicle data.
          // ------------------------------------

          this.cdr.detectChanges();

        },


        // ======================================
        // ERROR
        // ======================================

        error: (error) => {

          console.error(
            'VEHICLES ERROR:',
            error
          );


          // Never leave previous rows visible
          // after a failed request.
          this.vehicles = [];


          // We cannot claim another page exists
          // if this request failed.
          this.hasMore = false;



          // ------------------------------------
          // Give a clearer message for invalid
          // request parameters.
          // ------------------------------------

          if (
            error?.status === 422
          ) {

            this.vehicleError =
              'Invalid portfolio filter or pagination values. '
              +
              'Vehicles per page must be between 1 and 100.';

          }

          else if (
            error?.status === 0
          ) {

            this.vehicleError =
              'Unable to connect to the ARVF backend. '
              +
              'Please confirm that the FastAPI server is running.';

          }

          else {

            this.vehicleError =
              'Unable to retrieve portfolio vehicles. '
              +
              'Please try again.';

          }


          this.cdr.detectChanges();

        }

      });

  }
  
  get firstVisibleRecord(): number {

  if (this.vehicles.length === 0) {
    return 0;
  }

  return (
    (this.currentPage - 1)
    * this.selectedLimit
  ) + 1;
  }


  get lastVisibleRecord(): number {

    if (this.vehicles.length === 0) {
    return 0;
    }

    return (
      (this.currentPage - 1)
       * this.selectedLimit
    )  + this.vehicles.length;
  }

  // ==========================================
  // BUILD EMPTY RESULT MESSAGE
  // ==========================================

  private setEmptyResultMessage():
    void {


    const search =
      this.searchText
        .trim();


    const status =
      this.selectedStatus;


    // Search + status filter
    if (
      search &&
      status !== 'ALL'
    ) {

      this.emptyResultMessage =

        `No vehicle matching "${search}" `
        +
        `with status "${status}" was found `
        +
        `on page ${this.currentPage}.`;

      return;

    }


    // Search only
    if (search) {

      this.emptyResultMessage =

        `No vehicle matching ID, make or model `
        +
        `"${search}" was found on page `
        +
        `${this.currentPage}.`;

      return;

    }


    // Status only
    if (
      status !== 'ALL'
    ) {

      this.emptyResultMessage =

        `No vehicles with status "${status}" `
        +
        `were found on page `
        +
        `${this.currentPage}.`;

      return;

    }


    // Page contains no rows
    this.emptyResultMessage =

      `No portfolio vehicles were found `
      +
      `on page ${this.currentPage}.`;

  }


  // ==========================================
  // APPLY SEARCH + FILTER
  // ==========================================

  applyFilters(): void {

    /*
      Whenever filters change,
      start again from page 1.
    */

    this.currentPage =
      1;


    this.loadVehicles();

  }


  // ==========================================
  // CLEAR RESULTS
  // ==========================================

  clearFilters(): void {


    // Cancel current API request.
    this.vehicleRequest
      ?.unsubscribe();


    // Stop spinner immediately.
    this.loadingVehicles =
      false;


    // Reset controls.
    this.searchText =
      '';

    this.selectedStatus =
      'ALL';

    this.currentPage =
      1;


    // Remove current vehicle table.
    this.vehicles =
      [];


    this.hasMore =
      false;


    this.vehicleError =
      '';

    this.emptyResultMessage =
      '';


    // Explain what happened.
    this.informationMessage =

      'Vehicle results cleared. '
      +
      'Enter a search or choose filters, '
      +
      'then select Apply to retrieve '
      +
      'vehicles again.';

  }


  // ==========================================
  // REFRESH
  // ==========================================

  refreshPortfolio(): void {

    this.informationMessage =
      '';


    this.loadSummary();

    this.loadVehicles();

  }


  // ==========================================
  // NEXT PAGE
  // ==========================================

  nextPage(): void {

    if (
      !this.hasMore ||
      this.loadingVehicles
    ) {

      return;

    }


    this.currentPage++;

    this.loadVehicles();

  }


  // ==========================================
  // PREVIOUS PAGE
  // ==========================================

  previousPage(): void {

    if (
      this.currentPage <= 1 ||
      this.loadingVehicles
    ) {

      return;

    }


    this.currentPage--;

    this.loadVehicles();

  }


  // ==========================================
// VIEW DETAILS
// ==========================================

viewDetails(
  vehicleId: number,
  importId: number
): void {

if (importId === null || importId === undefined) {
    return;
  }

  this.router.navigate(
    [
      '/vehicle-details',
      vehicleId
    ],
    {
      queryParams: {
        import_id: importId
      }
    }
  );
}
}