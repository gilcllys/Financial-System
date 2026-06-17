import { Component, OnInit, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router, ActivatedRoute, RouterLink } from '@angular/router';
import { SupermarketService } from '../../../core/services/supermarket.service';

@Component({
  selector: 'app-supermarket-form',
  standalone: true,
  imports: [ReactiveFormsModule, RouterLink],
  templateUrl: './supermarket-form.component.html',
  styleUrls: ['./supermarket-form.component.scss'],
})
export class SupermarketFormComponent implements OnInit {
  private fb = inject(FormBuilder);
  private service = inject(SupermarketService);
  private router = inject(Router);
  private route = inject(ActivatedRoute);

  loading = signal(false);
  saving = signal(false);
  isEdit = signal(false);
  editId = signal<number | null>(null);
  errorMessage = signal('');

  form = this.fb.group({
    store_name: ['', [Validators.required, Validators.minLength(2)]],
    date: [this.todayStr(), Validators.required],
    address: [''],
  });

  ngOnInit(): void {
    const id = this.route.snapshot.paramMap.get('id');
    if (id) {
      this.isEdit.set(true);
      this.editId.set(+id);
      this.loadExpense(+id);
    }
  }

  private loadExpense(id: number): void {
    this.loading.set(true);
    this.service.get(id).subscribe({
      next: expense => {
        this.form.patchValue({
          store_name: expense.store_name,
          date: expense.date,
          address: expense.address ?? '',
        });
        this.loading.set(false);
      },
      error: () => {
        this.errorMessage.set('Erro ao carregar compra.');
        this.loading.set(false);
      },
    });
  }

  submit(): void {
    if (this.form.invalid) { this.form.markAllAsTouched(); return; }
    this.saving.set(true);
    this.errorMessage.set('');

    const v = this.form.getRawValue();
    const payload = {
      store_name: v.store_name!,
      date: v.date!,
      ...(v.address ? { address: v.address } : {}),
    };

    const req$ = this.isEdit()
      ? this.service.update(this.editId()!, payload)
      : this.service.create(payload);

    req$.subscribe({
      next: res => {
        if (this.isEdit()) {
          this.router.navigate(['/supermarket', this.editId()]);
        } else {
          this.router.navigate(['/supermarket', res.id]);
        }
      },
      error: err => {
        this.saving.set(false);
        this.errorMessage.set(err?.error?.detail ?? 'Erro ao salvar compra. Tente novamente.');
      },
    });
  }

  hasError(field: string): boolean {
    const c = this.form.get(field);
    return !!(c?.invalid && c?.touched);
  }

  private todayStr(): string {
    return new Date().toISOString().split('T')[0];
  }
}
