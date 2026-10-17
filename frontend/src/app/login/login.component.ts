import {
  Component,
  ChangeDetectorRef
} from '@angular/core';

import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { finalize } from 'rxjs/operators';

import {
  ArvfApiService
} from '../services/arvf-api.service';
import { AUTH_REQUEST_TIMEOUT_MS } from '../services/arvf-api.service';


@Component({
  selector: 'app-login',
  standalone: true,

  imports: [
    CommonModule,
    FormsModule,
    RouterLink
  ],

  templateUrl: './login.component.html',
  styleUrl: './login.component.css'
})
export class LoginComponent {

  email = '';
  password = '';

  loading = false;
  errorMessage = '';


  constructor(
    private api: ArvfApiService,
    private router: Router,
    private cdr: ChangeDetectorRef
  ) {}


  login(): void {

    this.errorMessage = '';


    // ---------------------------------------------
    // 1. Required fields
    // ---------------------------------------------

    if (
      !this.email.trim() ||
      !this.password
    ) {

      this.errorMessage =
        'Please enter your email and password.';

      this.cdr.detectChanges();

      return;
    }


    // ---------------------------------------------
    // 2. Validate email format
    // ---------------------------------------------

    const emailPattern =
      /^[^\s@]+@[^\s@]+\.[^\s@]+$/;


    if (
      !emailPattern.test(
        this.email.trim()
      )
    ) {

      this.errorMessage =
        'Please enter a valid email address.';

      this.cdr.detectChanges();

      return;
    }


    // ---------------------------------------------
    // 3. Begin request
    // ---------------------------------------------

    this.loading = true;

    this.cdr.detectChanges();


    this.api.login(

      this.email
        .trim(),

      this.password

    )
    .pipe(

      finalize(() => {

        this.loading = false;

        this.cdr.detectChanges();

      })

    )
    .subscribe({

      next: () => {

        this.cdr.detectChanges();

        this.router.navigate([
          '/portfolio'
        ]);

      },


      error: (error) => {

        console.error(
          'Login request failed:',
          error
        );


        if (error?.name === 'TimeoutError') {

          this.errorMessage =
            `The sign-in request timed out after ${AUTH_REQUEST_TIMEOUT_MS / 1000} seconds. The server may be busy or unable to reach the database. Please try again shortly.`;

          this.cdr.detectChanges();

          return;

        }


        if (error.status === 401) {

          this.errorMessage =
            'Invalid email or password.';

        }

        else if (error.status === 403) {

          this.errorMessage =
            error?.error?.detail ||
            'This account is currently disabled.';

        }

        else if (error.status === 423) {

          this.errorMessage =
            error?.error?.detail ||
            'Too many failed login attempts. Please try again later.';

        }

        else if (error.status === 0) {

          this.errorMessage =
            'Unable to connect to the server. Please try again.';

        }

        else {

          this.errorMessage =
            error?.error?.detail ||
            'Login failed. Please try again.';

        }


        this.cdr.detectChanges();

      }

    });
  }
}