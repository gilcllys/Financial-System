import {
  Component, OnInit, OnDestroy, inject, signal, computed,
  AfterViewInit, ElementRef, ViewChild
} from '@angular/core';
import { RouterLink } from '@angular/router';
import { DecimalPipe, CurrencyPipe, DatePipe } from '@angular/common';
import { Subject, takeUntil } from 'rxjs';
import { Chart, registerables } from 'chart.js';

import { HomeService, HomeSummary } from '../../core/services/home.service';
import { OpenInvoice, Expense } from '../../core/models';
import { MonthlyAnalytics, CategoryAnalytics } from '../../core/services/analytics.service';
import { SharedDebtGroup } from '../../core/services/shared-debt.service';

Chart.register(...registerables);

const MONTH_NAMES = [
  'Janeiro','Fevereiro','Março','Abril','Maio','Junho',
  'Julho','Agosto','Setembro','Outubro','Novembro','Dezembro'
];

@Component({
  selector: 'app-home',
  standalone: true,
  imports: [RouterLink, DecimalPipe, CurrencyPipe, DatePipe],
  templateUrl: './home.component.html',
  styleUrls: ['./home.component.scss'],
})
export class HomeComponent implements OnInit, OnDestroy, AfterViewInit {
  @ViewChild('evolutionChart') chartCanvas!: ElementRef<HTMLCanvasElement>;

  private homeService = inject(HomeService);
  private destroy$ = new Subject<void>();

  loading = signal(true);
  summary = signal<HomeSummary['summary']>({ income: 0, expenses: 0, balance: 0, count: 0 });
  evolution = signal<MonthlyAnalytics[]>([]);
  openInvoices = signal<OpenInvoice[]>([]);
  sharedDebts = signal<SharedDebtGroup[]>([]);
  byCategory = signal<CategoryAnalytics[]>([]);
  recentExpenses = signal<Expense[]>([]);

  readonly currentMonth = new Date().getMonth() + 1;
  readonly currentYear = new Date().getFullYear();
  readonly currentMonthName = MONTH_NAMES[new Date().getMonth()];
  readonly Math = Math;

  private chart: Chart | null = null;
  private pendingChartData: MonthlyAnalytics[] | null = null;

  totalInvoices = computed(() =>
    this.openInvoices().reduce((s, i) => s + i.total, 0)
  );

  maxCategory = computed(() =>
    Math.max(...this.byCategory().map(c => c.total), 1)
  );

  ngOnInit(): void {
    this.homeService.load(this.currentMonth, this.currentYear)
      .pipe(takeUntil(this.destroy$))
      .subscribe({
        next: data => {
          this.summary.set(data.summary);
          this.evolution.set(data.evolution);
          this.openInvoices.set(data.openInvoices);
          this.sharedDebts.set(data.sharedDebts);
          this.byCategory.set(data.byCategory);
          this.recentExpenses.set(data.recentExpenses);
          this.loading.set(false);
          if (this.chart) {
            this.updateChart(data.evolution);
          } else {
            this.pendingChartData = data.evolution;
          }
        },
        error: () => this.loading.set(false),
      });
  }

  ngAfterViewInit(): void {
    this.initChart([]);
    if (this.pendingChartData) {
      this.updateChart(this.pendingChartData);
      this.pendingChartData = null;
    }
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
    this.chart?.destroy();
  }

  private initChart(data: MonthlyAnalytics[]): void {
    const ctx = this.chartCanvas?.nativeElement?.getContext('2d');
    if (!ctx) return;
    const labels = data.map(d => d.month_name.substring(0, 3));
    this.chart = new Chart(ctx, {
      type: 'line',
      data: {
        labels,
        datasets: [
          {
            label: 'Receitas',
            data: data.map(d => d.income),
            borderColor: '#10b981',
            backgroundColor: 'rgba(16,185,129,0.08)',
            tension: 0.4,
            fill: true,
            pointRadius: 4,
            pointBackgroundColor: '#10b981',
            borderWidth: 2.5,
          },
          {
            label: 'Despesas',
            data: data.map(d => Math.abs(d.expenses)),
            borderColor: '#ef4444',
            backgroundColor: 'rgba(239,68,68,0.06)',
            tension: 0.4,
            fill: true,
            pointRadius: 4,
            pointBackgroundColor: '#ef4444',
            borderWidth: 2.5,
          },
          {
            label: 'Saldo',
            data: data.map(d => d.balance),
            borderColor: '#2563eb',
            backgroundColor: 'rgba(37,99,235,0.06)',
            tension: 0.4,
            fill: false,
            pointRadius: 4,
            pointBackgroundColor: '#2563eb',
            borderWidth: 2.5,
            borderDash: [5, 3],
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: ctx => ' R$ ' + (ctx.raw as number).toLocaleString('pt-BR', { minimumFractionDigits: 2 }),
            },
          },
        },
        scales: {
          y: {
            grid: { color: '#f3f4f6' },
            ticks: {
              callback: (v) => `R$ ${(+v / 1000).toFixed(0)}k`,
              font: { size: 11 },
            },
            border: { display: false },
          },
          x: {
            grid: { display: false },
            ticks: { font: { size: 11 } },
            border: { display: false },
          },
        },
      },
    });
  }

  private updateChart(data: MonthlyAnalytics[]): void {
    if (!this.chart) { this.initChart(data); return; }
    this.chart.data.labels = data.map(d => d.month_name.substring(0, 3));
    this.chart.data.datasets[0].data = data.map(d => d.income);
    this.chart.data.datasets[1].data = data.map(d => Math.abs(d.expenses));
    this.chart.data.datasets[2].data = data.map(d => d.balance);
    this.chart.update();
  }

  formatCurrency(value: number): string {
    return new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(value);
  }

  daysLabel(days: number): string {
    if (days < 0) return 'Fechada';
    if (days === 0) return 'Fecha hoje';
    if (days === 1) return 'Fecha amanhã';
    return `Fecha em ${days} dias`;
  }

  daysClass(days: number): string {
    if (days <= 3) return 'badge--red';
    if (days <= 7) return 'badge--yellow';
    return 'badge--green';
  }

  amountClass(amount: number): string {
    return amount >= 0 ? 'value--up' : 'value--down';
  }

  amountPrefix(amount: number): string {
    return amount >= 0 ? '+' : '-';
  }

  categoryBarWidth(total: number): string {
    return `${Math.min((total / this.maxCategory()) * 100, 100)}%`;
  }
}
