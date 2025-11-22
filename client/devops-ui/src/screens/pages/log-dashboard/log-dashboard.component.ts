import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { interval, Subject } from 'rxjs';
import { takeUntil } from 'rxjs/operators';
import { NgChartsModule } from 'ng2-charts';
import { ChartOptions } from 'chart.js';
import { RequestService } from '../../../services/request.service';
import { ToasterHelper } from '../../../services/toast.service';
import { LocalStorageHelper } from '../../../services/local-storage.service';
import { DEPLOYMENTS_API_ROUTE } from '../../../environment';
import { FormsModule, ReactiveFormsModule } from '@angular/forms';

interface Deployment {
  deployment_id: string;
  app_name: string;
  app_url: string;
  alb_dns?: string;
  ecs_cluster_name?: string;
  ecs_service_name?: string;
  ecr_image_uri?: string;
  log_group_name?: string;
  status: 'live' | 'deploying' | 'failed';
  health_status: 'healthy' | 'degraded' | 'unhealthy' | 'unknown';
  created_at: string;
  updated_at?: string;
  metrics: {
    total_requests?: number;
    success_count?: number;
    error_count?: number;
    success_rate: number;
    error_rate: number;
    avg_response_time_ms: number;
    p95_response_time_ms?: number;
    p99_response_time_ms?: number;
    requests_per_minute: number;
    status_code_distribution: Record<string, number>;
    top_errors?: Array<{ error: string; count: number }>;
    health_status: string,
    ecs_health: {
      running_count: number;
      desired_count: number;
      status?: string;
      deployment_status: string;
    };
    metric_timestamp?: string;
  };
}

interface LogEntry {
  timestamp: string;
  message: string;
  duration_ms?: number;
  client_ip?: string;
  status_code?: number;
  level?: 'info' | 'warn' | 'error' | 'debug';
}

interface MetricsHistoryPoint {
  timestamp: Date;
  requests_per_minute: number;
  avg_response_time_ms: number;
  error_rate: number;
  status_code_distribution: Record<string, number>;
}

@Component({
  selector: 'app-log-dashboard',
  standalone: true,
  imports: [CommonModule, FormsModule, ReactiveFormsModule, NgChartsModule],
  templateUrl: './log-dashboard.component.html',
  styleUrl: './log-dashboard.component.css'
})
export class LogDashboardComponent implements OnInit, OnDestroy {
  activeTab: 'overview' | 'metrics' | 'logs' | 'health' = 'overview';
  logFilter: 'all' | 'error' | 'warn' | 'info' = 'all';
  deployments: Deployment[] = [];
  selectedDeployment: Deployment | null = null;
  userId: string = '';
  logsStream: LogEntry[] = [];

  // ✅ Store historical metrics for chart accuracy
  metricsHistory: MetricsHistoryPoint[] = [];

  // Chart data
  requestRateChartData: any = { labels: [], datasets: [] };
  responseTimeChartData: any = { labels: [], datasets: [] };
  errorRateChartData: any = { labels: [], datasets: [] };
  statusCodeChartData: any = { labels: [], datasets: [] };

  chartOptions: ChartOptions<'line'> = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        display: true,
        labels: { color: '#a8a8a8', font: { size: 12 } }
      }
    },
    scales: {
      x: {
        grid: { color: 'rgba(45, 46, 50, 0.5)' },
        ticks: { color: '#6c6c6c' }
      },
      y: {
        grid: { color: 'rgba(45, 46, 50, 0.5)' },
        ticks: { color: '#6c6c6c' }
      }
    }
  };

  pieChartOptions: ChartOptions<'doughnut'> = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        display: true,
        position: 'bottom',
        labels: {
          color: '#a8a8a8',
          font: { family: "'Inter', sans-serif", size: 12 },
          padding: 15,
          usePointStyle: true,
          generateLabels: (chart) => {
            const data = chart.data;
            return (
              data.labels?.map((label, index) => ({
                text: String(label),
                fillStyle: (data.datasets[0].backgroundColor as string[])?.[
                  index
                ] || '#ccc',
                strokeStyle: '#1a1b1e',
                lineWidth: 2,
                hidden: false,
                index
              })) || []
            );
          }
        }
      }
    }
  };

  private destroy$ = new Subject<void>();

  constructor(
    private requestService: RequestService,
    private toasterService: ToasterHelper,
    private localStorage: LocalStorageHelper
  ) {
    const userDetails = this.localStorage.getItem('user_details');
    this.userId = userDetails?.user_id || '';
  }

  ngOnInit() {
    this.loadDeployments();
    this.setupAutoSync();
  }

  loadDeployments() {
    this.requestService.get(`${DEPLOYMENTS_API_ROUTE}/${this.userId}`).subscribe({
      next: (data: any) => {
        this.deployments = data.deployments || [];
      },
      error: (err: any) => {
        console.error('[Dashboard] Error loading deployments:', err);
        this.toasterService.error(err?.error?.message || 'Failed to load deployments');
      }
    });
  }

  selectDeployment(deployment: Deployment) {
    this.selectedDeployment = deployment;
    this.activeTab = 'overview';
    this.logsStream = [];
    this.metricsHistory = []; 
    this.loadMetrics(deployment);
    this.loadLogs(deployment);
  }

  loadMetrics(deployment: Deployment) {
    this.requestService.get(
      `${DEPLOYMENTS_API_ROUTE}/${this.userId}/${deployment.deployment_id}/metrics`
    ).subscribe({
      next: (data: any) => {
        if (this.selectedDeployment?.deployment_id === deployment.deployment_id) {
          this.selectedDeployment.metrics = data.metrics;

          if (this.selectedDeployment.metrics && this.selectedDeployment.metrics?.ecs_health?.status ) {

            if(this.selectedDeployment.metrics?.health_status == 'healthy' && this.selectedDeployment.metrics?.ecs_health?.status == 'healthy') {
              this.selectedDeployment.health_status = 'healthy'
            }
            else if (this.selectedDeployment.metrics?.health_status == 'unhealthy' || this.selectedDeployment.metrics?.ecs_health?.status == 'unhealthy') {
              this.selectedDeployment.health_status = 'unhealthy'
            }
          }

          // ✅ Store in history with timestamp
          const historyPoint: MetricsHistoryPoint = {
            timestamp: new Date(data.metrics.metric_timestamp || new Date()),
            requests_per_minute: parseFloat(
              String(data.metrics.requests_per_minute || 0)
            ),
            avg_response_time_ms: parseFloat(
              String(data.metrics.avg_response_time_ms || 0)
            ),
            error_rate: parseFloat(String(data.metrics.error_rate || 0)),
            status_code_distribution: data.metrics.status_code_distribution || {}
          };

          this.metricsHistory.push(historyPoint);

          // Keep only last 12 data points
          if (this.metricsHistory.length > 12) {
            this.metricsHistory.shift();
          }

          this.updateCharts();
        }
      },
      error: (err: any) => {
        console.error('[Dashboard] Error loading metrics:', err);
        this.toasterService.error('Failed to load metrics');
      }
    });
  }

  loadLogs(deployment: Deployment) {
    this.requestService.get(
      `${DEPLOYMENTS_API_ROUTE}/${this.userId}/${deployment.deployment_id}/logs`
    ).subscribe({
      next: (data: any) => {
        this.logsStream = (data.logs || []).map((log: any) => ({
          timestamp: log['@timestamp'] ? log['@timestamp'] : 'N/A',
          message: log['@message'] ? log['@message'] : 'No message',
          client_ip: log['client_ip'] ? log['client_ip'] : 'Unknown',
          duration_ms: log['duration_ms'] ? log['duration_ms'] : 0,
          status_code: log?.status_code,
          level: this.extractLogLevel(log?.status_code)
        }));
      },
      error: (err: any) => {
        console.error('[Dashboard] Error loading logs:', err);
        this.toasterService.error('Failed to load logs');
      }
    });
  }

  // ✅ FIXED: Return just the level, not an object
  private extractLogLevel(statusCode?: number): 'info' | 'warn' | 'error' | 'debug' {
    if (!statusCode) return 'info';

    if (statusCode >= 500) {
      return 'error'; // Server errors
    } else if (statusCode >= 400) {
      return 'warn'; // Client errors
    } else if (statusCode >= 300 && statusCode < 400) {
      return 'debug'; // Redirects
    }
    return 'info'; // Success
  }

  // ✅ COMPLETELY REWRITTEN - Use real data from history
  updateCharts() {
    if (!this.selectedDeployment || this.metricsHistory.length === 0) {
      return;
    }


    // ✅ Use ACTUAL timestamps from history
    const labels = this.metricsHistory.map((m) =>
      new Date(m.timestamp).toLocaleTimeString('en-US', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
      })
    );

    const requestsData = this.metricsHistory.map((m) => m.requests_per_minute);
    const responseData = this.metricsHistory.map((m) => m.avg_response_time_ms);
    const errorData = this.metricsHistory.map((m) => m.error_rate);

    console.log('[Dashboard] Requests data:', requestsData);
    console.log('[Dashboard] Response data:', responseData);
    console.log('[Dashboard] Error data:', errorData);

    // Request Rate Chart - ✅ REAL DATA
    this.requestRateChartData = {
      labels,
      datasets: [
        {
          label: 'Requests/min',
          data: requestsData,
          borderColor: '#ff7b2c',
          backgroundColor: 'rgba(255, 123, 44, 0.1)',
          tension: 0.4,
          fill: true,
          pointRadius: 4,
          pointBackgroundColor: '#ff7b2c'
        }
      ]
    };

    this.responseTimeChartData = {
      labels,
      datasets: [
        {
          label: 'Response Time (ms)',
          data: responseData,
          borderColor: '#4dabf7',
          backgroundColor: 'rgba(77, 171, 247, 0.1)',
          tension: 0.4,
          fill: true,
          pointRadius: 4,
          pointBackgroundColor: '#4dabf7'
        }
      ]
    };

    this.errorRateChartData = {
      labels,
      datasets: [
        {
          label: 'Error Rate (%)',
          data: errorData,
          borderColor: '#ff6b6b',
          backgroundColor: 'rgba(255, 107, 107, 0.1)',
          tension: 0.4,
          fill: true,
          pointRadius: 4,
          pointBackgroundColor: '#ff6b6b'
        }
      ]
    };

    const latestMetrics = this.metricsHistory[this.metricsHistory.length - 1];
    const statusCodes = latestMetrics.status_code_distribution || {};
    const statusLabels = Object.keys(statusCodes);
    const statusData = Object.values(statusCodes);

    console.log('[Dashboard] Status codes:', statusLabels, statusData);

    this.statusCodeChartData = {
      labels: statusLabels.map((code) => {
        const count = statusCodes[code as keyof typeof statusCodes];
        return `${code} (${count})`;
      }),
      datasets: [
        {
          label: 'Count',
          data: statusData,
          backgroundColor: ['#51cf66', '#4dabf7', '#ffc107', '#ff6b6b'],
          borderColor: '#1a1b1e',
          borderWidth: 2
        }
      ]
    };
  }

  getFilteredLogs(): LogEntry[] {
    if (this.logFilter === 'all') return this.logsStream;
    return this.logsStream.filter((log) => log.level === this.logFilter);
  }

  refreshMetrics(deployment: Deployment) {
    this.loadMetrics(deployment);
    this.loadLogs(deployment);
  }

  visitApp(deployment: Deployment) {
    if (deployment.alb_dns) {
      const url = deployment.app_url || `http://${deployment.alb_dns}`;
      window.open(url, '_blank');
    }
  }

  private setupAutoSync() {
    interval(300000) // 300000ms = 5 minutes
      .pipe(takeUntil(this.destroy$))
      .subscribe(() => {
        if (this.selectedDeployment) {

          // STEP 1: Trigger backend to sync metrics from AWS
          this.requestService.post(
            `${DEPLOYMENTS_API_ROUTE}/${this.userId}/${this.selectedDeployment.deployment_id}/sync-metrics`,
            {}
          ).subscribe({
            next: (response) => {

              // STEP 2: Wait 2 seconds, then fetch fresh metrics
              setTimeout(() => {
                this.loadMetrics(this.selectedDeployment!);
              }, 2000);
            },
            error: (err) => {
              console.error('[Dashboard] Sync error:', err);
            }
          });
        }
      });
  }

  ngOnDestroy() {
    this.destroy$.next();
    this.destroy$.complete();
  }
}