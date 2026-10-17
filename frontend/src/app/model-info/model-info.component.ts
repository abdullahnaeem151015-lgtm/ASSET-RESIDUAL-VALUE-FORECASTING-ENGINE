import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { finalize } from 'rxjs';
import { ArvfApiService } from '../services/arvf-api.service';

@Component({
  selector: 'app-model-info',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './model-info.component.html',
  styleUrl: './model-info.component.css'
})
export class ModelInfoComponent implements OnInit {
  modelInfo: any = null;
  loading = true;
  error = '';

  readonly reportedMetrics = {
    mae: 827.4,
    rmse: 1231.6,
    r_squared: 0.992
  };

  get hasRegisteredMetrics(): boolean {
    const metrics = this.modelInfo?.metrics;

    return [metrics?.mae, metrics?.rmse, metrics?.r_squared]
      .every((value) => typeof value === 'number' && Number.isFinite(value));
  }

  get performanceMetrics(): { mae: number; rmse: number; r_squared: number } {
    return this.hasRegisteredMetrics
      ? this.modelInfo.metrics
      : this.reportedMetrics;
  }

  constructor(private api: ArvfApiService) {}

  ngOnInit(): void {
    this.api.getModelInfo()
      .pipe(finalize(() => this.loading = false))
      .subscribe({
        next: (modelInfo) => this.modelInfo = modelInfo,
        error: () => this.error = 'Unable to load model information.'
      });
  }
}