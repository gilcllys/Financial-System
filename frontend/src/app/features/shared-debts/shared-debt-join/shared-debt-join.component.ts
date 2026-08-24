import { Component, OnInit, inject, signal } from '@angular/core';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { ReactiveFormsModule, FormBuilder } from '@angular/forms';
import { SharedDebtService } from '../../../core/services/shared-debt.service';

@Component({
  selector: 'app-shared-debt-join',
  standalone: true,
  imports: [ReactiveFormsModule, RouterLink],
  templateUrl: './shared-debt-join.component.html',
  styleUrls: ['./shared-debt-join.component.scss'],
})
export class SharedDebtJoinComponent implements OnInit {
  private route = inject(ActivatedRoute);
  private router = inject(Router);
  private svc = inject(SharedDebtService);
  private fb = inject(FormBuilder);

  private token = '';
  joining = signal(false);
  errorMessage = signal('');

  form = this.fb.group({
    displayName: [''],
  });

  ngOnInit(): void {
    this.token = this.route.snapshot.paramMap.get('token') ?? '';
    if (!this.token) this.errorMessage.set('Convite inválido.');
  }

  join(): void {
    if (!this.token) { this.errorMessage.set('Convite inválido.'); return; }
    this.joining.set(true);
    this.errorMessage.set('');
    const name = (this.form.value.displayName ?? '').trim() || undefined;
    this.svc.join(this.token, name).subscribe({
      next: group => this.router.navigate(['/shared-debts', group.id]),
      error: err => {
        this.joining.set(false);
        if (err?.status === 404) {
          this.errorMessage.set('Convite inválido. Verifique o link e tente novamente.');
        } else if (err?.status === 400) {
          this.errorMessage.set('Este convite expirou. Peça um novo link.');
        } else {
          this.errorMessage.set(err?.error?.detail ?? 'Erro ao entrar no grupo. Tente novamente.');
        }
      },
    });
  }
}
