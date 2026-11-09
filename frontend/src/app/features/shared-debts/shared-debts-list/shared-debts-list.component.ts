import { Component, OnInit, inject, signal } from '@angular/core';
import { ToastService } from '../../../core/services/toast.service';
import { RouterLink } from '@angular/router';
import { ReactiveFormsModule, FormBuilder, Validators } from '@angular/forms';
import {
  SharedDebtService,
  SharedDebtListSummary,
} from '../../../core/services/shared-debt.service';

@Component({
  selector: 'app-shared-debts-list',
  standalone: true,
  imports: [RouterLink, ReactiveFormsModule],
  templateUrl: './shared-debts-list.component.html',
  styleUrls: ['./shared-debts-list.component.scss'],
})
export class SharedDebtsListComponent implements OnInit {
  private toast = inject(ToastService);
  private svc  = inject(SharedDebtService);
  private fb   = inject(FormBuilder);

  groups           = signal<SharedDebtListSummary[]>([]);
  loading          = signal(true);
  showForm         = signal(false);
  creating         = signal(false);
  errorMessage     = signal('');

  form = this.fb.group({
    name: ['', [Validators.required, Validators.minLength(2)]],
    memberNames: [''],
  });

  ngOnInit(): void { this.load(); }

  private load(): void {
    this.loading.set(true);
    this.svc.listSummary().subscribe({
      next: groups => {
        this.groups.set(groups);
        this.loading.set(false);
      },
      error: () => this.loading.set(false),
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
      next: () => { this.toast.success('Grupo criado.'); this.creating.set(false); this.showForm.set(false); this.form.reset(); this.load(); },
      error: err => { this.creating.set(false); this.errorMessage.set(err?.error?.detail ?? 'Erro ao criar grupo.'); },
    });
  }

  initials(name: string): string {
    return name.split(' ').map(p => p[0]).slice(0, 2).join('').toUpperCase();
  }

  hasError(field: string): boolean {
    const c = this.form.get(field);
    return !!(c?.invalid && c?.touched);
  }
}
