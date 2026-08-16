import * as d3 from 'd3';
import { Component, OnInit, inject, signal, computed, ElementRef, ViewChild } from '@angular/core';
import { RouterLink } from '@angular/router';
import { ReactiveFormsModule, FormBuilder, Validators } from '@angular/forms';
import { CurrencyPipe } from '@angular/common';
import {
  SavingsService, SavingsSummary, SavingsGoal, SavingsDeposit,
  CreateGoalPayload
} from '../../core/services/savings.service';

@Component({
  selector: 'app-savings',
  standalone: true,
  imports: [RouterLink, ReactiveFormsModule, CurrencyPipe],
  templateUrl: './savings.component.html',
  styleUrls: ['./savings.component.scss'],
})
export class SavingsComponent implements OnInit {
  private svc = inject(SavingsService);
  private fb = inject(FormBuilder);

  summary = signal<SavingsSummary | null>(null);
  loading = signal(true);
  selectedGoalId = signal<number | null>(null);

  showGoalForm = signal(false);
  savingGoal = signal(false);
  goalError = signal('');

  showDepositForm = signal(false);
  savingDeposit = signal(false);
  depositError = signal('');

  @ViewChild('chartEl') chartEl!: ElementRef<HTMLDivElement>;
  savTooltip = signal<{cx:number; cy:number; label:string; monthly:number; accumulated:number}|null>(null);

  goalForm = this.fb.group({
    name: ['', [Validators.required, Validators.minLength(2)]],
    target_amount: [null as number | null],
    color: ['#6366f1'],
    icon: ['🐷'],
  });

  depositForm = this.fb.group({
    goal_id: [null as number | null, Validators.required],
    amount: [null as number | null, [Validators.required]],
    date: [new Date().toISOString().split('T')[0], Validators.required],
    description: [''],
  });

  filteredDeposits = computed(() => {
    const s = this.summary();
    if (!s) return [];
    const gId = this.selectedGoalId();
    if (gId == null) return [];
    return [];  // loaded separately
  });

  goalProgress(goal: SavingsGoal): number {
    if (!goal.target_amount || goal.target_amount === 0) return 0;
    return Math.min(100, (Number(goal.total_deposited) / Number(goal.target_amount)) * 100);
  }

  ngOnInit(): void {
    this.loadSummary();
  }

  loadSummary(): void {
    this.loading.set(true);
    this.svc.getSummary().subscribe({
      next: s => {
        this.summary.set(s);
        this.loading.set(false);
        setTimeout(() => this.renderChart(), 0);
      },
      error: () => this.loading.set(false),
    });
  }

  saveGoal(): void {
    if (this.goalForm.invalid) { this.goalForm.markAllAsTouched(); return; }
    this.savingGoal.set(true);
    const v = this.goalForm.getRawValue();
    const payload: CreateGoalPayload = {
      name: v.name!,
      target_amount: v.target_amount ?? null,
      color: v.color ?? '#6366f1',
      icon: v.icon ?? '🐷',
    };
    this.svc.createGoal(payload).subscribe({
      next: () => {
        this.savingGoal.set(false);
        this.showGoalForm.set(false);
        this.goalForm.reset({ name: '', target_amount: null, color: '#6366f1', icon: '🐷' });
        this.loadSummary();
      },
      error: err => {
        this.savingGoal.set(false);
        this.goalError.set(err?.error?.detail ?? 'Erro ao salvar cofrinho.');
      },
    });
  }

  deleteGoal(id: number): void {
    if (!confirm('Excluir este cofrinho e todos os aportes?')) return;
    this.svc.deleteGoal(id).subscribe({ next: () => this.loadSummary() });
  }

  saveDeposit(): void {
    if (this.depositForm.invalid) { this.depositForm.markAllAsTouched(); return; }
    this.savingDeposit.set(true);
    const v = this.depositForm.getRawValue();
    this.svc.createDeposit({
      goal_id: v.goal_id!,
      amount: v.amount!,
      date: v.date!,
      description: v.description ?? '',
    }).subscribe({
      next: () => {
        this.savingDeposit.set(false);
        this.showDepositForm.set(false);
        this.depositForm.reset({ goal_id: null, amount: null, date: new Date().toISOString().split('T')[0], description: '' });
        this.loadSummary();
      },
      error: err => {
        this.savingDeposit.set(false);
        this.depositError.set(err?.error?.detail ?? 'Erro ao salvar aporte.');
      },
    });
  }

  deleteDeposit(id: number): void {
    this.svc.deleteDeposit(id).subscribe({ next: () => this.loadSummary() });
  }

  formatCurrency(v: number): string {
    return new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(Number(v));
  }

  formatDate(d: string): string {
    return d ? `${d.slice(8,10)}/${d.slice(5,7)}/${d.slice(0,4)}` : '';
  }

  private renderChart(): void {
    const s = this.summary();
    if (!s || !this.chartEl || s.monthly_breakdown.length === 0) return;

    const el = this.chartEl.nativeElement;
    el.innerHTML = '';
    const data = s.monthly_breakdown;
    const margin = {top:20, right:20, bottom:30, left:65};
    const width = 540, height = 200;
    const innerW = width - margin.left - margin.right;
    const innerH = height - margin.top - margin.bottom;
    const labels = data.map(d => `${d.month_name.slice(0,3)}/${String(d.year).slice(2)}`);

    const svg = d3.select(el).append('svg')
      .attr('viewBox', `0 0 ${width} ${height}`)
      .style('width','100%').style('height',`${height}px`).style('overflow','visible');

    const g = svg.append('g').attr('transform',`translate(${margin.left},${margin.top})`);

    const x = d3.scalePoint().domain(labels).range([0, innerW]);
    const maxY = Math.max(...data.map(d => d.accumulated)) * 1.15 || 1;
    const y = d3.scaleLinear().domain([0, maxY]).range([innerH, 0]);

    g.append('g').call(d3.axisLeft(y).ticks(4).tickSize(-innerW).tickFormat(()=>''))
      .call(gg => gg.select('.domain').remove())
      .call(gg => gg.selectAll('line').attr('stroke','#f3f4f6'));

    g.append('g').attr('transform',`translate(0,${innerH})`)
      .call(d3.axisBottom(x).tickSize(0))
      .call(gg => gg.select('.domain').remove())
      .call(gg => gg.selectAll('text').attr('fill','#9ca3af').attr('font-size','9').attr('font-family','inherit'));

    g.append('g').call(d3.axisLeft(y).ticks(4).tickFormat((v: d3.NumberValue) => {
      const n = +v;
      return n >= 1000 ? `R$${(n/1000).toFixed(1)}k` : `R$${n.toFixed(0)}`;
    }))
      .call(gg => gg.select('.domain').remove())
      .call(gg => gg.selectAll('text').attr('fill','#9ca3af').attr('font-size','9').attr('font-family','inherit'));

    const areaFn = d3.area<typeof data[0]>()
      .x((_,i)=>x(labels[i])!).y0(innerH).y1(d=>y(d.accumulated))
      .curve(d3.curveMonotoneX);
    const lineFn = d3.line<typeof data[0]>()
      .x((_,i)=>x(labels[i])!).y(d=>y(d.accumulated))
      .curve(d3.curveMonotoneX);

    g.append('path').datum(data).attr('d', areaFn).attr('fill','#a5b4fc').attr('opacity','0.3');
    g.append('path').datum(data).attr('d', lineFn)
      .attr('fill','none').attr('stroke','#6366f1').attr('stroke-width','2.5')
      .attr('stroke-linejoin','round').attr('stroke-linecap','round');

    const tooltip = this.savTooltip;
    data.forEach((d, i) => {
      if (d.accumulated === 0) return;
      const cx = x(labels[i])!;
      const cy = y(d.accumulated);
      g.append('circle').attr('cx',cx).attr('cy',cy).attr('r',4)
        .attr('fill','#6366f1').attr('stroke','#fff').attr('stroke-width',1.5);
      g.append('circle').attr('cx',cx).attr('cy',cy).attr('r',14)
        .attr('fill','transparent').style('cursor','pointer')
        .on('mousemove', (event: MouseEvent) => {
          tooltip.set({ cx: event.clientX+14, cy: event.clientY-90, label: labels[i], monthly: d.total, accumulated: d.accumulated });
        })
        .on('mouseleave', () => tooltip.set(null));
    });
  }
}
