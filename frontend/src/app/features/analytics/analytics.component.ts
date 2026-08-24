import { Component, OnInit, inject, signal, ElementRef, ViewChild, AfterViewInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { AnalyticsService, MonthlyAnalytics, CategoryAnalytics, CardAnalytics, DailyAnalytics } from '../../core/services/analytics.service';
import { D3ChartService, DonutData, BarData, GroupedBarData, AreaData } from '../../core/services/d3-chart.service';

const CAT_COLORS = ['#0052ff','#05b169','#cf202f','#f4b000','#7c828a','#16181c','#a8acb3','#30b0c7','#ff6b35','#af52de'];

@Component({
  selector: 'app-analytics',
  standalone: true,
  imports: [FormsModule],
  templateUrl: './analytics.component.html',
  styleUrls: ['./analytics.component.scss'],
})
export class AnalyticsComponent implements OnInit, AfterViewInit {
  private analyticsService = inject(AnalyticsService);
  private d3 = inject(D3ChartService);

  @ViewChild('monthlyChart') monthlyRef!: ElementRef<HTMLDivElement>;
  @ViewChild('categoryChart') categoryRef!: ElementRef<HTMLDivElement>;
  @ViewChild('cardChart') cardRef!: ElementRef<HTMLDivElement>;
  @ViewChild('cashCategoryChart') cashCategoryRef!: ElementRef<HTMLDivElement>;
  @ViewChild('dailyChart') dailyRef!: ElementRef<HTMLDivElement>;

  selectedYear = signal(new Date().getFullYear());
  selectedMonth = signal(new Date().getMonth() + 1);
  loading = signal(true);

  monthlyData = signal<MonthlyAnalytics[]>([]);
  categoryData = signal<CategoryAnalytics[]>([]);
  cardData = signal<CardAnalytics[]>([]);
  cashCategoryData = signal<CategoryAnalytics[]>([]);
  dailyData = signal<DailyAnalytics[]>([]);

  years = Array.from({ length: 5 }, (_, i) => new Date().getFullYear() - 2 + i);
  months = [
    { value: 1, label: 'Janeiro' }, { value: 2, label: 'Fevereiro' },
    { value: 3, label: 'Marco' }, { value: 4, label: 'Abril' },
    { value: 5, label: 'Maio' }, { value: 6, label: 'Junho' },
    { value: 7, label: 'Julho' }, { value: 8, label: 'Agosto' },
    { value: 9, label: 'Setembro' }, { value: 10, label: 'Outubro' },
    { value: 11, label: 'Novembro' }, { value: 12, label: 'Dezembro' },
  ];

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
  ngAfterViewInit(): void { this.viewReady = true; if (this.dataReady) this.renderCharts(); }

  loadAll(): void {
    this.loading.set(true);
    this.dataReady = false;
    let pending = 5;
    const done = () => { if (--pending === 0) { this.dataReady = true; this.loading.set(false); if (this.viewReady) this.renderCharts(); } };
    this.analyticsService.monthly(this.selectedYear()).subscribe({ next: d => { this.monthlyData.set(d); done(); }, error: () => done() });
    this.analyticsService.byCategory(this.selectedMonth(), this.selectedYear()).subscribe({ next: d => { this.categoryData.set(d); done(); }, error: () => done() });
    this.analyticsService.byCard(this.selectedMonth(), this.selectedYear()).subscribe({ next: d => { this.cardData.set(d); done(); }, error: () => done() });
    this.analyticsService.byCategory(this.selectedMonth(), this.selectedYear(), 'dinheiro').subscribe({ next: d => { this.cashCategoryData.set(d); done(); }, error: () => done() });
    this.analyticsService.daily(this.selectedMonth(), this.selectedYear()).subscribe({ next: d => { this.dailyData.set(d); done(); }, error: () => done() });
  }

  onFilterChange(): void { this.loadAll(); }

  private renderCharts(): void {
    setTimeout(() => {
      this.renderMonthly();
      this.renderCategory();
      this.renderCard();
      this.renderCashCategory();
      this.renderDaily();
    }, 80);
  }

  private renderMonthly(): void {
    const el = this.monthlyRef?.nativeElement;
    if (!el) return;
    const data: GroupedBarData[] = this.monthlyData().map(d => ({
      label: d.month_name.substring(0, 3),
      income: d.income,
      expenses: d.expenses,
    }));
    this.d3.renderGroupedBar(el, data);
  }

  private renderCategory(): void {
    const el = this.categoryRef?.nativeElement;
    if (!el) return;
    const data: DonutData[] = this.categoryData().map((d, i) => ({
      label: d.category_name, value: d.total, color: CAT_COLORS[i % CAT_COLORS.length],
    }));
    this.d3.renderTreemap(el, data);
  }

  private renderCard(): void {
    const el = this.cardRef?.nativeElement;
    if (!el) return;
    const data: BarData[] = this.cardData().map(d => ({
      label: `${d.card_name} ****${d.last_four_digits}`, value: d.total,
    }));
    this.d3.renderHorizontalBar(el, data);
  }

  private renderCashCategory(): void {
    const el = this.cashCategoryRef?.nativeElement;
    if (!el) return;
    const total = this.cashCategoryData().reduce((s, d) => s + d.total, 0);
    const data: DonutData[] = this.cashCategoryData().map((d, i) => ({
      label: d.category_name, value: d.total, color: CAT_COLORS[i % CAT_COLORS.length],
    }));
    this.d3.renderDonut(el, data, new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL', maximumFractionDigits: 0 }).format(total));
  }

  private renderDaily(): void {
    const el = this.dailyRef?.nativeElement;
    if (!el) return;
    const data: AreaData[] = this.dailyData().map(d => ({ day: d.day, value: d.total }));
    this.d3.renderArea(el, data);
  }

  formatCurrency(v: number): string {
    return new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(v);
  }

  currentMonthName(): string {
    return this.months.find(m => m.value === this.selectedMonth())?.label ?? '';
  }
}