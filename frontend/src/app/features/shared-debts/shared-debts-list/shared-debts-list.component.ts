import { Component, OnInit, inject, signal, computed } from '@angular/core';
import { RouterLink } from '@angular/router';
import { ReactiveFormsModule, FormBuilder, Validators } from '@angular/forms';
import { forkJoin, of } from 'rxjs';
import { catchError, map } from 'rxjs/operators';
import { AuthService } from '../../../core/auth/auth.service';
import {
  SharedDebtService,
  SharedDebtGroup,
  BalancesResponse,
  PersonalSummary,
} from '../../../core/services/shared-debt.service';

interface CounterpartSummary {
  name: string;
  net: number; // positive = they owe me, negative = I owe them
}

@Component({
  selector: 'app-shared-debts-list',
  standalone: true,
  imports: [RouterLink, ReactiveFormsModule],
  templateUrl: './shared-debts-list.component.html',
  styleUrls: ['./shared-debts-list.component.scss'],
})
export class SharedDebtsListComponent implements OnInit {
  private svc = inject(SharedDebtService);
  private auth = inject(AuthService);
  private fb = inject(FormBuilder);

  private myTenantId = this.auth.userProfile.sub ?? null;

  groups = signal<SharedDebtGroup[]>([]);
  balancesByGroup = signal<Map<number, BalancesResponse>>(new Map());
  personal = signal<PersonalSummary | null>(null);
  personalError = signal(false);
  loading = signal(true);
  showForm = signal(false);
  creating = signal(false);
  errorMessage = signal('');

  form = this.fb.group({
    name: ['', [Validators.required, Validators.minLength(2)]],
    memberNames: [''],
  });

  /** Net-per-counterpart aggregate across all my groups. */
  consolidated = computed<CounterpartSummary[]>(() => {
    const net = new Map<string, number>();
    const bmap = this.balancesByGroup();
    for (const group of this.groups()) {
      const balances = bmap.get(group.id);
      if (!balances) continue;
      const myId = this.myMemberId(group, balances);
      if (myId == null) continue;
      for (const line of balances.settlement) {
        if (line.from_member_id === myId) {
          // I pay someone → I owe them
          net.set(line.to_name, (net.get(line.to_name) ?? 0) - line.amount);
        } else if (line.to_member_id === myId) {
          // someone pays me → they owe me
          net.set(line.from_name, (net.get(line.from_name) ?? 0) + line.amount);
        }
      }
    }
    return [...net.entries()]
      .map(([name, value]) => ({ name, net: +value.toFixed(2) }))
      .filter(c => Math.abs(c.net) >= 0.01)
      .sort((a, b) => a.name.localeCompare(b.name));
  });

  /** Short balance hint for a group card (my net in that group). */
  groupHint(group: SharedDebtGroup): number | null {
    const balances = this.balancesByGroup().get(group.id);
    if (!balances) return null;
    const myId = this.myMemberId(group, balances);
    if (myId == null) return null;
    return balances.members.find(m => m.member_id === myId)?.balance ?? null;
  }

  private myMemberId(group: SharedDebtGroup, balances: BalancesResponse): number | null {
    const byTenant = this.myTenantId
      ? balances.members.find(m => m.tenant_id && m.tenant_id === this.myTenantId)
      : undefined;
    if (byTenant) return byTenant.member_id;
    // Fallback: the owner-created member.
    const owner = balances.members.find(m => m.tenant_id === group.owner_tenant_id);
    return owner?.member_id ?? null;
  }

  ngOnInit(): void {
    this.load();
    this.loadPersonal();
  }

  private loadPersonal(): void {
    this.personalError.set(false);
    this.svc.personalSummary().subscribe({
      next: p => this.personal.set(p),
      error: () => { this.personal.set(null); this.personalError.set(true); },
    });
  }

  private load(): void {
    this.loading.set(true);
    this.svc.listGroups().subscribe({
      next: groups => {
        this.groups.set(groups);
        if (groups.length === 0) {
          this.loading.set(false);
          return;
        }
        forkJoin(
          groups.map(g =>
            this.svc.balances(g.id).pipe(
              map(b => [g.id, b] as const),
              catchError(() => of([g.id, null] as const)),
            ),
          ),
        ).subscribe({
          next: results => {
            const map = new Map<number, BalancesResponse>();
            for (const [id, b] of results) if (b) map.set(id, b);
            this.balancesByGroup.set(map);
            this.loading.set(false);
          },
          error: () => this.loading.set(false),
        });
      },
      error: () => this.loading.set(false),
    });
  }

  toggleForm(): void {
    this.showForm.set(!this.showForm());
    this.errorMessage.set('');
  }

  create(): void {
    if (this.form.invalid) { this.form.markAllAsTouched(); return; }
    this.creating.set(true);
    this.errorMessage.set('');
    const names = (this.form.value.memberNames ?? '')
      .split(',')
      .map(n => n.trim())
      .filter(Boolean);
    this.svc.createGroup({
      name: this.form.value.name!,
      member_names: names.length ? names : undefined,
    }).subscribe({
      next: () => {
        this.creating.set(false);
        this.showForm.set(false);
        this.form.reset({ name: '', memberNames: '' });
        this.load();
      },
      error: err => {
        this.creating.set(false);
        this.errorMessage.set(err?.error?.detail ?? 'Erro ao criar grupo. Tente novamente.');
      },
    });
  }

  formatCurrency(v: number): string {
    return new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(Math.abs(v));
  }

  hasError(field: string): boolean {
    const c = this.form.get(field);
    return !!(c?.invalid && c?.touched);
  }
}
