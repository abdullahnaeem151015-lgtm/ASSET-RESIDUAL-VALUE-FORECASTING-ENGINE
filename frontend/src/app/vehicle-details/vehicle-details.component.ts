import {
  Component,
  OnInit,
  ChangeDetectorRef
} from '@angular/core';

import {
  CommonModule
} from '@angular/common';

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

  selector: 'app-vehicle-details',

  standalone: true,

  imports: [
    CommonModule
  ],

  templateUrl:
    './vehicle-details.component.html',

  styleUrl:
    './vehicle-details.component.css'

})


export class VehicleDetailsComponent
implements OnInit {


  vehicleId:
    number | null = null;

  activeImportId:
   number | null = null;


  vehicle:
    any = null;


  loading:
    boolean = false;


  errorMessage:
    string = '';


  constructor(

    private route:
      ActivatedRoute,

    private router:
      Router,

    private api:
      ArvfApiService,

    private cdr:
      ChangeDetectorRef

  ) {}


  ngOnInit(): void {

    const id =
      this.route.snapshot
        .paramMap
        .get('id');


    if (!id) {

      this.errorMessage =
        'No vehicle was selected.';

      return;

    }


    this.vehicleId =
      Number(id);


    if (
      Number.isNaN(
        this.vehicleId
      )
    ) {

      this.errorMessage =
        'Invalid vehicle ID.';

      return;

    }

// ==========================================
// GET ACTIVE PORTFOLIO IMPORT ID
// ==========================================

const importIdParam =
  this.route.snapshot
    .queryParamMap
    .get('import_id');


if (importIdParam) {

  const parsedImportId =
    Number(importIdParam);

  if (
    Number.isFinite(parsedImportId) &&
    parsedImportId > 0
  ) {

    this.activeImportId =
      parsedImportId;

  }

}


// ==========================================
// FALLBACK TO LOCAL STORAGE
// ==========================================

if (this.activeImportId === null) {

  const savedImportId =
    localStorage.getItem(
      'activeImportId'
    );

  if (savedImportId) {

    const parsedSavedImportId =
      Number(savedImportId);

    if (
      Number.isFinite(parsedSavedImportId) &&
      parsedSavedImportId > 0
    ) {

      this.activeImportId =
        parsedSavedImportId;

    }

  }

}


    if (this.activeImportId === null) {

     this.errorMessage =
       'No active portfolio is selected.';

     return;

}
    
    this.loadVehicleDetails();

  }


  loadVehicleDetails(): void {

    if (
      this.vehicleId === null ||
      this.activeImportId === null
    ) {

      return;

    }


    this.loading = true;

    this.errorMessage = '';


    this.api
      .getVehicleDetails(
        this.vehicleId,
        this.activeImportId
      )

      .pipe(

        finalize(() => {

          this.loading = false;

          this.cdr.detectChanges();

        })

      )

      .subscribe({

        next: (data) => {

          this.vehicle = data;

          this.cdr.detectChanges();

        },


        error: (error) => {

          console.error(
            'VEHICLE DETAILS ERROR:',
            error
          );


          if (
            error.status === 404
          ) {

            this.errorMessage =
              `Vehicle ${this.vehicleId} was not found.`;

          }

          else {

            this.errorMessage =
              'Unable to load vehicle details. Please try again.';

          }


          this.cdr.detectChanges();

        }

      });

  }


  backToPortfolio(): void {

    this.router.navigate(
      ['/portfolio']
    );

  }

  forecastVehicle(): void {
    if (
      this.vehicleId === null ||
      this.activeImportId === null
    ) {
      return;
    }

    this.router.navigate(
      ['/forecast'],
      {
        queryParams: {
          vehicle_id: this.vehicleId,
          import_id: this.activeImportId
        }
      }
    );
  }

}