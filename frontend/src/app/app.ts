import { Component } from '@angular/core';
import {
  RouterOutlet,
  RouterLink,
  RouterLinkActive
} from '@angular/router';
import { ArvfApiService } from './services/arvf-api.service';

@Component({
  selector: 'app-root',
  standalone: true,

  imports: [
    RouterOutlet,
    RouterLink,
    RouterLinkActive
  ],

  templateUrl: './app.html',
  styleUrl: './app.css'
})
export class App {
  constructor(private api: ArvfApiService) {}

  logout(): void {
    this.api.logout();
  }
}