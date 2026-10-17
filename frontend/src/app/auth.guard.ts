import { inject } from '@angular/core';

import {
  CanActivateFn,
  Router
} from '@angular/router';

import {
  ArvfApiService
} from './services/arvf-api.service';


export const authGuard: CanActivateFn = () => {

  const api =
    inject(ArvfApiService);

  const router =
    inject(Router);


  if (api.isLoggedIn()) {
    return true;
  }


  return router.createUrlTree([
    '/login'
  ]);
};