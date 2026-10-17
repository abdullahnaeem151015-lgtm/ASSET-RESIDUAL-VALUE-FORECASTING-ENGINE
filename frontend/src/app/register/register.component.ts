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


@Component({
  selector: 'app-register',
  standalone: true,

  imports: [
    CommonModule,
    FormsModule,
    RouterLink
  ],

  templateUrl: './register.component.html',
  styleUrl: './register.component.css'
})
export class RegisterComponent {

  fullName = '';
  email = '';
  password = '';
  confirmPassword = '';

  showPassword = false;
  showConfirmPassword = false;

  loading = false;
  errorMessage = '';
  successMessage = '';


  constructor(
    private api: ArvfApiService,
    private router: Router,
    private cdr: ChangeDetectorRef
  ) {}


  get hasMinimumLength(): boolean {

    return this.password.length >= 8;
  }


  get hasUppercase(): boolean {

    return /[A-Z]/.test(
      this.password
    );
  }


  get hasLowercase(): boolean {

    return /[a-z]/.test(
      this.password
    );
  }


  get hasNumber(): boolean {

    return /\d/.test(
      this.password
    );
  }


  get hasSpecialCharacter(): boolean {

    return /[!@#$%^&*()_+\-=\[\]{};':"\\|,.<>/?]/.test(
      this.password
    );
  }


  get passwordsMatch(): boolean {

    return (
      this.confirmPassword.length > 0 &&
      this.password === this.confirmPassword
    );
  }


  get passwordIsValid(): boolean {

    return (
      this.hasMinimumLength &&
      this.hasUppercase &&
      this.hasLowercase &&
      this.hasNumber &&
      this.hasSpecialCharacter
    );
  }


  get emailMatchesFullName(): boolean {

    const fullName =
      this.fullName
        .trim()
        .toLowerCase();

    const email =
      this.email
        .trim()
        .toLowerCase();


    if (
      !fullName ||
      !email.includes('@')
    ) {

      return false;
    }


    const emailUsername =
      email.split('@')[0];


    const nameParts =
      fullName
        .split(/\s+/)
        .filter(
          part => part.length >= 3
        );


    return nameParts.some(
      part =>
        emailUsername.includes(part)
    );
  }


  register(): void {

    this.errorMessage = '';
    this.successMessage = '';


    // ---------------------------------------------
    // 1. Required fields
    // ---------------------------------------------

    if (
      !this.fullName.trim() ||
      !this.email.trim() ||
      !this.password ||
      !this.confirmPassword
    ) {

      this.errorMessage =
        'Please complete all required fields.';

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

      return;
    }


    // ---------------------------------------------
    // 3. Check email-name relationship
    // ---------------------------------------------

    if (!this.emailMatchesFullName) {

      this.errorMessage =
        'Your email should contain at least one part of your full name.';

      return;
    }


    // ---------------------------------------------
    // 4. Validate password security
    // ---------------------------------------------

    if (!this.passwordIsValid) {

      this.errorMessage =
        'Password does not meet the required security rules.';

      return;
    }


    // ---------------------------------------------
    // 5. Confirm passwords match
    // ---------------------------------------------

    if (!this.passwordsMatch) {

      this.errorMessage =
        'Passwords do not match.';

      return;
    }


    // ---------------------------------------------
    // 6. Start request
    // ---------------------------------------------

    this.loading = true;

    this.cdr.detectChanges();


    this.api.register({

      full_name:
        this.fullName.trim(),

      email:
        this.email
          .trim()
          .toLowerCase(),

      password:
        this.password,

      confirm_password:
        this.confirmPassword

    })
    .pipe(

      finalize(() => {

        this.loading = false;

        this.cdr.detectChanges();

      })

    )
    .subscribe({

      next: () => {

        this.successMessage =
          'Account created successfully. You can now sign in.';

        this.cdr.detectChanges();


        // Navigate immediately after successful registration
        this.router.navigate([
          '/login'
        ]);

      },


      error: (error) => {

        console.error(
          'Registration request failed:',
          error
        );


        const detail =
          error?.error?.detail;


        if (Array.isArray(detail)) {

          this.errorMessage =
            detail
              .map(
                (item: any) =>
                  item?.msg || item
              )
              .join(' ');

        } else {

          this.errorMessage =
            detail ||
            'Registration failed. Please try again.';

        }


        this.cdr.detectChanges();

      }

    });
  }
}