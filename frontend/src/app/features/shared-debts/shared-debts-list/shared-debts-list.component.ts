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
} from '../../../core/services/shared-debt.service';

interface Settlement { iOwe: boolean; name: string; amount: number; }

@Component({
  selector: 'app-shared-debts-list',
  standalone: true,
  imports: [RouterLink, ReactiveFormsModule],
  templateUrl: './shared-debts-list.component.html',
  styleUrls: ['./shared-debts-list.component.scss'],
})
export class SharedDebtsListComponent implements OnInit {
  private svc  = inject(SharedDebtService);
  private auth = inject(AuthService);
  private fb   = inject(FormBuilder);

  private myTenantId = this.auth.userProfile.sub ?? null;

  groups           = signal<SharedDebtGroup[]>([]);
  balancesByGroup  = signal<Map<number, BalancesResponse>>(new Map());
  entryCounts      = signal<Record<number, number>>({});
  loading          = signal(true);
  showForm         = signal(false);
  creating         = signal(false);
  errorMessage     = signal('');

  form = this.fb.group({
    name: ['', [Validators.required, Validators.minLength(2)]],
    memberNames: [''],
  });

  totalToReceive = computed(() =>
    this.groups().reduce((s, g) => { const h = this.groupHint(g); return h && h > 0 ? s + h : s; }, 0)
  );
  totalToPay = computed(() =>
    this.groups().reduce((s, g) => { const h = this.groupHint(g); return h && h < 0 ? s + Math.abs(h) : s; }, 0)
  );
  netBalance = computed(() => this.totalToReceive() - this.totalToPay());

  ngOnInit(): void { this.load(); }

  private load(): void {
    this.loading.set(true);
    this.svc.listGroups().subscribe({
      next: groups => {
        this.groups.set(groups);
        if (!groups.length) { this.loading.set(false); return; }
        forkJoin(
          groups.map(g =>
            this.svc.balances(g.id).pipe(
              map(b => [g.id, b] as const),
              catchError(() => of([g.id, null] as const)),
            )
          )
        ).subscribe({
          next: results => {
            const bmap = new Map<number, BalancesResponse>();
            const counts: Record<number, number> = {};
            for (const [id, b] of results) {
              if (b) bmap.set(id, b);
            }
            this.balancesByGroup.set(bmap);
            // Load entry counts per group
            groups.forEach(g => {
              this.svc.listEntries({ shared_debt: g.id, page_size: 200 }).subscribe({
                next: res => this.entryCounts.update(c => ({ ...c, [g.id]: res.count })),
                error: () => {},
              });
            });
            this.loading.set(false);
          },
          error: () => this.loading.set(false),
        });
      },
      error: () => this.loading.set(false),
    });
  }

  groupBalances(groupId: number): BalancesResponse | null {
    return this.balancesByGroup().get(groupId) ?? null;
  }

  myMemberIdFor(group: SharedDebtGroup): number | null {
    const b = this.balancesByGroup().get(group.id);
    if (!b) return null;
    return this.myMemberId(group, b);
  }

  private myMemberId(group: SharedDebtGroup, b: BalancesResponse): number | null {
    const byTenant = this.myTenantId
      ? b.members.find(m => m.tenant_id === this.myTenantId)
      : undefined;
    if (byTenant) return byTenant.member_id;
    return b.members.find(m => m.tenant_id === group.owner_tenant_id)?.member_id ?? null;
  }

  groupHint(group: SharedDebtGroup): number | null {
    const b = this.balancesByGroup().get(group.id);
    if (!b) return null;
    const myId = this.myMemberId(group, b);
    if (myId == null) return null;
    return b.members.find(m => m.member_id === myId)?.balance ?? null;
  }

  /** Returns the most relevant settlement line involving me, or null. */
  mySettlement(group: SharedDebtGroup, b: BalancesResponse): Settlement | null {
    const myId = this.myMemberId(group, b);
    if (myId == null) return null;
    // I owe someone
    const iOwe = b.settlement.find(s => s.from_member_id === myId);
    if (iOwe) return { iOwe: true, name: iOwe.to_name, amount: iOwe.amount };
    // Someone owes me
    const owesMe = b.settlement.find(s => s.to_member_id === myId);
    if (owesMe) return { iOwe: false, name: owesMe.from_name, amount: owesMe.amount };
    return null;
  }

  copyInvite(groupId: number): void {
    this.svc.createInvite(groupId).subscribe({
      next: inv => {
        const url = window.location.origin + inv.join_path;
        navigator.clipboard.writeText(url).then(() => alert('Link copiado!'));
      },
    });
  }

  toggleForm(): void { this.showForm.set(!this.showForm()); this.errorMessage.set(''); }

  create(): void {
    if (this.form.invalid) { this.form.markAllAsTouched(); return; }
    this.creating.set(true);
    this.errorMessage.set('');
    const names = (this.form.value.memberNames ?? '').split(',').map(n => n.trim()).filter(Boolean);
    this.svc.createGroup({
      name: this.form.value.name!,
      member_names: names.length ? names : undefined,
    }).subscribe({
      next: () => { this.creating.set(false); this.showForm.set(false); this.form.reset(); this.load(); },
      error: err => { this.creating.set(false); this.errorMessage.set(err?.error?.detail ?? 'Erro ao criar grupo.'); },
    });
  }

  initials(name: string): string {
    return name.split(' ').map(p => p[0]).slice(0, 2).join('').toUpperCase();
  }

  formatCurrency(v: number): string {
    return new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(Math.abs(v ?? 0));
  }

  hasError(field: string): boolean {
    const c = this.form.get(field);
    return !!(c?.invalid && c?.touched);
  }
}