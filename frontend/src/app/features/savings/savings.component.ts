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
  imports: [RouterLink, ReactiveFormsModule],
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
    const data = s.monthly_breakdown;
    const labels = data.map(d => `${d.month_name.slice(0,3)}/${String(d.year).slice(2)}`);
    const accumulated = data.map(d => d.accumulated);
    const monthly = data.map(d => d.total);
    const W = 540, H = 200, PL = 60, PR = 20, PT = 20, PB = 30;
    const maxV = Math.max(...accumulated) * 1.15 || 1;
    const n = labels.length;
    const totalW = W - PL - PR;
    const gap = n > 1 ? totalW / (n - 1) : totalW;
    const sx = (i: number) => PL + i * gap;
    const sy = (v: number) => PT + (1 - v / maxV) * (H - PT - PB);
    const fmt = (v: number) => `R$ ${v.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}`;

    let o = `<svg viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg" style="width:100%;height:${H}px;overflow:visible">`;
    for (let s2 = 0; s2 <= 4; s2++) {
      const gv = maxV * s2 / 4;
      const gy = sy(gv);
      o += `<line x1="${PL}" y1="${gy.toFixed(1)}" x2="${W-PR}" y2="${gy.toFixed(1)}" stroke="#f3f4f6" stroke-width="1"/>`;
      const lbl = gv >= 1000 ? `${(gv/1000).toFixed(1)}k` : gv.toFixed(0);
      o += `<text x="${PL-6}" y="${(gy+4).toFixed(1)}" text-anchor="end" font-size="9" fill="#9ca3af" font-family="inherit">R$${lbl}</text>`;
    }

    // Area fill
    const pts = accumulated.map((_, i) => `${sx(i).toFixed(1)},${sy(accumulated[i]).toFixed(1)}`).join(' ');
    const baseY = sy(0).toFixed(1);
    o += `<polygon points="${sx(0).toFixed(1)},${baseY} ${pts} ${sx(n-1).toFixed(1)},${baseY}" fill="#a5b4fc" opacity="0.3"/>`;
    o += `<polyline points="${pts}" fill="none" stroke="#6366f1" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round"/>`;

    accumulated.forEach((_, i) => {
      if (accumulated[i] === 0 && monthly[i] === 0) return;
      o += `<circle cx="${sx(i).toFixed(1)}" cy="${sy(accumulated[i]).toFixed(1)}" r="4" fill="#6366f1" stroke="#fff" stroke-width="1.5"/>`;
      o += `<circle class="chart-hit" cx="${sx(i).toFixed(1)}" cy="${sy(accumulated[i]).toFixed(1)}" r="12" fill="transparent" style="cursor:pointer" data-label="${labels[i]}" data-acc="${accumulated[i]}" data-monthly="${monthly[i]}"/>`;
    });

    labels.forEach((m, i) => {
      o += `<text x="${sx(i).toFixed(1)}" y="${H-6}" text-anchor="middle" font-size="9" fill="#9ca3af" font-family="inherit">${m}</text>`;
    });
    o += `</svg>`;
    this.chartEl.nativeElement.innerHTML = o;

    // Attach tooltip events
    const svg = this.chartEl.nativeElement.querySelector('svg');
    svg?.querySelectorAll('.chart-hit').forEach(el => {
      el.addEventListener('mouseenter', (e: Event) => {
        const me = e as MouseEvent;
        const rect = this.chartEl.nativeElement.getBoundingClientRect();
        const t = el as HTMLElement;
        const tip = this.chartEl.nativeElement.querySelector('.sav-tooltip') as HTMLElement;
        if (tip) {
          tip.style.left = `${me.clientX - rect.left + 12}px`;
          tip.style.top = `${me.clientY - rect.top - 50}px`;
          tip.innerHTML = `<strong>${t.dataset['label']}</strong><div>Aporte: ${this.formatCurrency(parseFloat(t.dataset['monthly']!))}</div><div>Acumulado: <b>${this.formatCurrency(parseFloat(t.dataset['acc']!))}</b></div>`;
          tip.style.display = 'block';
        }
      });
      el.addEventListener('mouseleave', () => {
        const tip = this.chartEl.nativeElement.querySelector('.sav-tooltip') as HTMLElement;
        if (tip) tip.style.display = 'none';
      });
    });
  }
}
