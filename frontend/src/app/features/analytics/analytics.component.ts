import { Component, OnInit, OnDestroy, inject, signal, ElementRef, ViewChild, AfterViewInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { AnalyticsService, MonthlyAnalytics, CategoryAnalytics, CardAnalytics, DailyAnalytics } from '../../core/services/analytics.service';
import { Chart, registerables } from 'chart.js';

Chart.register(...registerables);

@Component({
  selector: 'app-analytics',
  standalone: true,
  imports: [FormsModule],
  templateUrl: './analytics.component.html',
  styleUrls: ['./analytics.component.scss'],
})
export class AnalyticsComponent implements OnInit, OnDestroy, AfterViewInit {
  private analyticsService = inject(AnalyticsService);

  @ViewChild('monthlyChart') monthlyChartRef!: ElementRef<HTMLCanvasElement>;
  @ViewChild('categoryChart') categoryChartRef!: ElementRef<HTMLCanvasElement>;
  @ViewChild('cardChart') cardChartRef!: ElementRef<HTMLCanvasElement>;
  @ViewChild('dailyChart') dailyChartRef!: ElementRef<HTMLCanvasElement>;

  private charts: Chart[] = [];

  selectedYear = signal(new Date().getFullYear());
  selectedMonth = signal(new Date().getMonth() + 1);
  loading = signal(true);

  monthlyData = signal<MonthlyAnalytics[]>([]);
  categoryData = signal<CategoryAnalytics[]>([]);
  cardData = signal<CardAnalytics[]>([]);
  dailyData = signal<DailyAnalytics[]>([]);

  years = Array.from({ length: 5 }, (_, i) => new Date().getFullYear() - 2 + i);
  months = [
    { value: 1, label: 'Janeiro' }, { value: 2, label: 'Fevereiro' },
    { value: 3, label: 'Março' }, { value: 4, label: 'Abril' },
    { value: 5, label: 'Maio' }, { value: 6, label: 'Junho' },
    { value: 7, label: 'Julho' }, { value: 8, label: 'Agosto' },
    { value: 9, label: 'Setembro' }, { value: 10, label: 'Outubro' },
    { value: 11, label: 'Novembro' }, { value: 12, label: 'Dezembro' },
  ];

  // KPIs calculados no TS (não no template — Arrow functions não são suportadas em templates Angular)
  avgDaily = () => {
    const data = this.dailyData();
    const active = data.filter(d => d.total > 0);
    if (!active.length) return 0;
    return active.reduce((s, d) => s + d.total, 0) / active.length;
  };
  maxDaily = () => Math.max(0, ...this.dailyData().map(d => d.total));
  daysWithExpense = () => this.dailyData().filter(d => d.total > 0).length;

  private viewReady = false;
  private dataReady = false;

  ngOnInit(): void { this.loadAll(); }

  ngAfterViewInit(): void {
    this.viewReady = true;
    if (this.dataReady) this.renderCharts();
  }

  ngOnDestroy(): void { this.charts.forEach(c => c.destroy()); }

  loadAll(): void {
    this.loading.set(true);
    this.dataReady = false;
    let pending = 4;
    const done = () => { if (--pending === 0) { this.dataReady = true; this.loading.set(false); if (this.viewReady) this.renderCharts(); } };

    this.analyticsService.monthly(this.selectedYear()).subscribe({ next: d => { this.monthlyData.set(d); done(); }, error: () => done() });
    this.analyticsService.byCategory(this.selectedMonth(), this.selectedYear()).subscribe({ next: d => { this.categoryData.set(d); done(); }, error: () => done() });
    this.analyticsService.byCard(this.selectedMonth(), this.selectedYear()).subscribe({ next: d => { this.cardData.set(d); done(); }, error: () => done() });
    this.analyticsService.daily(this.selectedMonth(), this.selectedYear()).subscribe({ next: d => { this.dailyData.set(d); done(); }, error: () => done() });
  }

  onFilterChange(): void {
    this.charts.forEach(c => c.destroy());
    this.charts = [];
    this.loadAll();
  }

  private renderCharts(): void {
    this.charts.forEach(c => c.destroy());
    this.charts = [];
    setTimeout(() => {
      this.renderMonthly();
      this.renderCategory();
      this.renderCard();
      this.renderDaily();
    }, 50);
  }

  private renderMonthly(): void {
    const ctx = this.monthlyChartRef?.nativeElement;
    if (!ctx) return;
    const data = this.monthlyData();
    this.charts.push(new Chart(ctx, {
      type: 'bar',
      data: {
        labels: data.map(d => d.month_name.substring(0, 3)),
        datasets: [
          { label: 'Receitas', data: data.map(d => d.income), backgroundColor: 'rgba(5,177,105,0.7)', borderColor: '#05b169', borderWidth: 1, borderRadius: 4 },
          { label: 'Despesas', data: data.map(d => d.expenses), backgroundColor: 'rgba(207,32,47,0.7)', borderColor: '#cf202f', borderWidth: 1, borderRadius: 4 },
        ],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { position: 'top' }, tooltip: { callbacks: { label: ctx => `R$ ${(ctx.parsed.y ?? 0).toFixed(2)}` } } },
        scales: { y: { ticks: { callback: v => `R$ ${v}` } } },
      },
    }));
  }

  private renderCategory(): void {
    const ctx = this.categoryChartRef?.nativeElement;
    if (!ctx) return;
    const data = this.categoryData();
    if (!data.length) return;
    const colors = ['#0052ff','#05b169','#cf202f','#f4b000','#7c828a','#16181c','#a8acb3','#dee1e6','#eef0f3','#5b616e'];
    this.charts.push(new Chart(ctx, {
      type: 'doughnut',
      data: {
        labels: data.map(d => d.category_name),
        datasets: [{ data: data.map(d => d.total), backgroundColor: colors.slice(0, data.length), borderWidth: 2, borderColor: '#fff' }],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: {
          legend: { position: 'right' },
          tooltip: { callbacks: { label: ctx => `${ctx.label}: R$ ${(ctx.parsed as number).toFixed(2)} (${data[ctx.dataIndex].percentage.toFixed(1)}%)` } },
        },
      },
    }));
  }

  private renderCard(): void {
    const ctx = this.cardChartRef?.nativeElement;
    if (!ctx) return;
    const data = this.cardData();
    if (!data.length) return;
    this.charts.push(new Chart(ctx, {
      type: 'bar',
      data: {
        labels: data.map(d => `${d.card_name} ****${d.last_four_digits}`),
        datasets: [{ label: 'Gasto no cartão', data: data.map(d => d.total), backgroundColor: 'rgba(0,82,255,0.7)', borderColor: '#0052ff', borderWidth: 1, borderRadius: 4 }],
      },
      options: {
        indexAxis: 'y', responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false }, tooltip: { callbacks: { label: ctx => `R$ ${(ctx.parsed.x ?? 0).toFixed(2)}` } } },
        scales: { x: { ticks: { callback: v => `R$ ${v}` } } },
      },
    }));
  }

  private renderDaily(): void {
    const ctx = this.dailyChartRef?.nativeElement;
    if (!ctx) return;
    const data = this.dailyData();
    this.charts.push(new Chart(ctx, {
      type: 'line',
      data: {
        labels: data.map(d => `Dia ${d.day}`),
        datasets: [{
          label: 'Gasto diário',
          data: data.map(d => d.total),
          borderColor: '#0052ff', backgroundColor: 'rgba(0,82,255,0.08)',
          borderWidth: 2, pointRadius: 3, fill: true, tension: 0.3,
        }],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false }, tooltip: { callbacks: { label: ctx => `R$ ${(ctx.parsed.y ?? 0).toFixed(2)}` } } },
        scales: { y: { ticks: { callback: v => `R$ ${v}` }, beginAtZero: true } },
      },
    }));
  }

  formatCurrency(v: number): string {
    return new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(v);
  }

  currentMonthName(): string {
    return this.months.find(m => m.value === this.selectedMonth())?.label ?? '';
  }
}
