import { Routes } from '@angular/router';

import {
  PortfolioComponent
} from './portfolio/portfolio.component';

import {
  ForecastComponent
} from './forecast/forecast.component';

import {
  ModelInfoComponent
} from './model-info/model-info.component';

import {
  VehicleDetailsComponent
} from './vehicle-details/vehicle-details.component';

import {
  authGuard
} from './auth.guard';


export const routes: Routes = [

  {
    path: 'login',

    loadComponent: () =>
      import(
        './login/login.component'
      ).then(
        m => m.LoginComponent
      )
  },


  {
    path: 'register',

    loadComponent: () =>
      import(
        './register/register.component'
      ).then(
        m => m.RegisterComponent
      )
  },


  {
    path: 'portfolio',
    component: PortfolioComponent,
    canActivate: [authGuard]
  },


  {
    path: 'forecast',
    component: ForecastComponent,
    canActivate: [authGuard]
  },


  {
    path: 'model-info',
    component: ModelInfoComponent,
    canActivate: [authGuard]
  },


  {
    path: 'vehicle-details/:id',
    component: VehicleDetailsComponent,
    canActivate: [authGuard]
  },


  {
    path: '',
    redirectTo: 'login',
    pathMatch: 'full'
  },


  {
    path: '**',
    redirectTo: 'login'
  }

];