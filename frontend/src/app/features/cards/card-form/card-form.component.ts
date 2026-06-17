import { Component, OnInit, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router, ActivatedRoute, RouterLink } from '@angular/router';
import { CardService } from '../../../core/services/card.service';

@Component({
  selector: 'app-card-form',
  standalone: true,
  imports: [ReactiveFormsModule, RouterLink],
  templateUrl: './card-form.component.html',
  styleUrls: ['./card-form.component.scss'],
})
export class CardFormComponent implements OnInit {
  private fb = inject(FormBuilder);
  private cardService = inject(CardService);
  private router = inject(Router);
  private route = inject(ActivatedRoute);

  saving = signal(false);
  loading = signal(false);
  errorMessage = signal('');
  isEdit = signal(false);
  editId = signal<number | null>(null);

  form = this.fb.group({
    name: ['', [Validators.required, Validators.minLength(2)]],
    last_four_digits: ['', [Validators.required, Validators.minLength(4), Validators.maxLength(4), Validators.pattern(/^\d{4}$/)]],
    due_date: [null as number | null, [Validators.required, Validators.min(1), Validators.max(31)]],
    best_purchase_date: [null as number | null, [Validators.required, Validators.min(1), Validators.max(31)]],
  });

  ngOnInit(): void {
    const id = this.route.snapshot.paramMap.get('id');
    if (id) {
      this.isEdit.set(true);
      this.editId.set(+id);
      this.loadCard(+id);
    }
  }

  private loadCard(id: number): void {
    this.loading.set(true);
    this.cardService.get(id).subscribe({
      next: card => {
        this.form.patchValue(card);
        this.loading.set(false);
      },
      error: () => { this.errorMessage.set('Erro ao carregar cartão.'); this.loading.set(false); },
    });
  }

  submit(): void {
    if (this.form.invalid) { this.form.markAllAsTouched(); return; }
    this.saving.set(true);
    const payload = this.form.getRawValue() as any;

    const req$ = this.isEdit()
      ? this.cardService.update(this.editId()!, payload)
      : this.cardService.create(payload);

    req$.subscribe({
      next: () => this.router.navigate(['/cards']),
      error: err => {
        this.saving.set(false);
        this.errorMessage.set(err?.error?.detail ?? 'Erro ao salvar cartão.');
      },
    });
  }

  hasError(field: string): boolean {
    const c = this.form.get(field);
    return !!(c?.invalid && c?.touched);
  }
}
