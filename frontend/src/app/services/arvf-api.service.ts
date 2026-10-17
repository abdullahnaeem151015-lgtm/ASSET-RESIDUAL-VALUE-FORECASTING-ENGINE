import { Injectable } from '@angular/core';

import {
  HttpClient,
  HttpHeaders
} from '@angular/common/http';

import {
  Observable
} from 'rxjs';

import {
  Router
} from '@angular/router';

import {
  tap,
  timeout
} from 'rxjs/operators';


// ==========================================
// AUTH REQUEST / RESPONSE TYPES
// ==========================================

interface RegisterRequest {

  full_name: string;
  email: string;
  password: string;
  confirm_password: string;
}


interface LoginResponse {

  access_token: string;

  user: {

    user_id?: number;
    full_name?: string;
    email?: string;

    [key: string]: any;
  };
}

export const AUTH_REQUEST_TIMEOUT_MS = 15000;


@Injectable({
  providedIn: 'root'
})
export class ArvfApiService {

  private apiUrl =
    'http://127.0.0.1:8001';

  private accessToken: string | null = null;

  private accessTokenExpiresAt = 0;


  constructor(
    private http: HttpClient,
    private router: Router
  ) {
    localStorage.removeItem('arvf_access_token');
    localStorage.removeItem('arvf_user');
  }


  // ==========================================
  // PORTFOLIO IMPORTS
  // ==========================================

  getPortfolioImports(includeArchived = false):
    Observable<any[]> {

    return this.http.get<any[]>(
      `${this.apiUrl}/portfolio/imports`,
      {
        params: { include_archived: includeArchived },
        headers: this.authHeaders()
      }
    );
  }

  archivePortfolioImport(importId: number): Observable<any> {
    return this.http.post(
      `${this.apiUrl}/portfolio/imports/${importId}/archive`,
      {},
      { headers: this.authHeaders() }
    );
  }

  restorePortfolioImport(importId: number): Observable<any> {
    return this.http.post(
      `${this.apiUrl}/portfolio/imports/${importId}/restore`,
      {},
      { headers: this.authHeaders() }
    );
  }


  // ==========================================
  // PORTFOLIO SUMMARY
  // ==========================================

  getPortfolioSummary(
    importId: number | null = null
  ): Observable<any> {

    const params:
      Record<string, string | number> = {};


    if (importId !== null) {

      params['import_id'] =
        importId;
    }


    return this.http.get<any>(
      `${this.apiUrl}/portfolio/summary`,
      {
        params,
        headers: this.authHeaders()
      }
    );
  }


  // ==========================================
  // PORTFOLIO VEHICLES
  // ==========================================

  getPortfolioVehicles(

    importId: number | null,

    limit: number,

    page: number,

    search: string,

    status: string

  ): Observable<any> {

    const params:
      Record<string, string | number> = {

        limit,
        page,
        search,
        status
      };


    if (importId !== null) {

      params['import_id'] =
        importId;
    }


    return this.http.get<any>(

      `${this.apiUrl}/portfolio/vehicles`,

      {
        params,
        headers: this.authHeaders()
      }

    );
  }


  // ==========================================
  // VALIDATE PORTFOLIO IMPORT
  // ==========================================

  validatePortfolioImport(
    file: File
  ): Observable<any> {

    const formData =
      new FormData();


    formData.append(
      'file',
      file,
      file.name
    );


    return this.http.post<any>(

      `${this.apiUrl}/portfolio/import/validate`,

      formData,
      { headers: this.authHeaders() }

    );
  }


  // ==========================================
  // IMPORT PORTFOLIO
  // ==========================================

  importPortfolio(
    file: File
  ): Observable<any> {

    const formData =
      new FormData();


    formData.append(
      'file',
      file,
      file.name
    );


    return this.http.post<any>(

      `${this.apiUrl}/portfolio/import`,

      formData,
      { headers: this.authHeaders() }

    );
  }


  // ==========================================
  // DOWNLOAD PORTFOLIO TEMPLATE
  // ==========================================

  downloadPortfolioTemplate():
    Observable<Blob> {

    return this.http.get(

      `${this.apiUrl}/portfolio/import/template`,

      {
        responseType: 'blob',
        headers: this.authHeaders()
      }

    );
  }


  // ==========================================
  // SEARCH VEHICLES
  // ==========================================

  searchVehicles(

    query: string,

    importId: number

  ): Observable<any> {

    return this.http.get(

      `${this.apiUrl}/vehicles/search`,

      {
        params: {

          q: query,

          import_id:
            importId
        },
        headers: this.authHeaders()
      }

    );
  }


  // ==========================================
  // VEHICLE DETAILS
  // ==========================================

  getVehicleDetails(

    vehicleId: number,

    importId: number

  ): Observable<any> {

    return this.http.get(

      `${this.apiUrl}/vehicles/${vehicleId}/details`,

      {
        params: {

          import_id:
            importId
        },
        headers: this.authHeaders()
      }

    );
  }


  // ==========================================
  // SAVE INSPECTION
  // ==========================================

  saveInspection(

    vehicleId: number,

    inspection: any,

    importId: number

  ): Observable<any> {

    return this.http.post(

      `${this.apiUrl}/vehicles/${vehicleId}/inspections`,

      inspection,

      {
        params: {

          import_id:
            importId
        },
        headers: this.authHeaders()
      }

    );
  }


  // ==========================================
  // GENERATE FORECAST
  // ==========================================

  generateForecast(

    vehicleId: number,

    data: any,

    importId: number

  ): Observable<any> {

    return this.http.post(

      `${this.apiUrl}/vehicles/${vehicleId}/forecast`,

      data,

      {
        params: {

          import_id:
            importId
        },
        headers: this.authHeaders()
      }

    );
  }


  // ==========================================
  // SAVE FORECAST
  // ==========================================

  saveForecast(
    forecastId: number
  ): Observable<any> {

    return this.http.post(

      `${this.apiUrl}/forecasts/${forecastId}/save`,

      {},
      { headers: this.authHeaders() }

    );
  }


  // ==========================================
  // MODEL INFORMATION
  // ==========================================

  getModelInfo():
    Observable<any> {

    return this.http.get(

      `${this.apiUrl}/model-info`,
      { headers: this.authHeaders() }

    );
  }


  // ==========================================
  // REGISTER
  // ==========================================

  register(
    data: RegisterRequest
  ): Observable<any> {

    const payload:
      RegisterRequest = {

      full_name:
        data.full_name.trim(),

      email:
        data.email
          .trim()
          .toLowerCase(),

      password:
        data.password,

      confirm_password:
        data.confirm_password
    };


    return this.http.post<any>(

      `${this.apiUrl}/auth/register`,

      payload

    )
    .pipe(

      timeout(AUTH_REQUEST_TIMEOUT_MS)

    );
  }


  // ==========================================
  // LOGIN
  // ==========================================

  login(
    email: string,
    password: string
  ): Observable<LoginResponse> {

    return this.http.post<LoginResponse>(

      `${this.apiUrl}/auth/login`,

      {

        email:
          email
            .trim(),

        password:
          password
      }

    )
    .pipe(

      timeout(AUTH_REQUEST_TIMEOUT_MS),

      tap(response => {
        this.accessToken = response.access_token;
        this.accessTokenExpiresAt = this.readTokenExpiry(response.access_token);
      })

    );
  }


  // ==========================================
  // LOGOUT
  // ==========================================

  logout(): void {
    this.accessToken = null;
    this.accessTokenExpiresAt = 0;

    this.router.navigate([
      '/login'
    ]);
  }


  // ==========================================
  // LOGIN STATE
  // ==========================================

  isLoggedIn(): boolean {
    if (!this.accessToken || Date.now() >= this.accessTokenExpiresAt) {
      this.accessToken = null;
      this.accessTokenExpiresAt = 0;
      return false;
    }

    return true;
  }


  // ==========================================
  // ACCESS TOKEN
  // ==========================================

  getToken():
    string | null {
    return this.isLoggedIn()
      ? this.accessToken
      : null;
  }

  private authHeaders(): HttpHeaders {
    const token = this.getToken();

    return token
      ? new HttpHeaders({ Authorization: `Bearer ${token}` })
      : new HttpHeaders();
  }

  private readTokenExpiry(token: string): number {
    try {
      const payload = token.split('.')[1]
        .replace(/-/g, '+')
        .replace(/_/g, '/');
      const claims = JSON.parse(atob(payload));
      const expiry = Number(claims.exp);

      return Number.isFinite(expiry)
        ? expiry * 1000
        : 0;
    } catch {
      return 0;
    }
  }
}