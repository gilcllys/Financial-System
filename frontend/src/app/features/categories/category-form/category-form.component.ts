import { Component, OnInit, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router, ActivatedRoute, RouterLink } from '@angular/router';
import { CategoryService } from '../../../core/services/category.service';

@Component({
  selector: 'app-category-form',
  standalone: true,
  imports: [ReactiveFormsModule, RouterLink],
  templateUrl: './category-form.component.html',
  styleUrls: ['./category-form.component.scss'],
})
export class CategoryFormComponent implements OnInit {
  private fb = inject(FormBuilder);
  private categoryService = inject(CategoryService);
  private router = inject(Router);
  private route = inject(ActivatedRoute);

  saving = signal(false);
  loading = signal(false);
  errorMessage = signal('');
  isEdit = signal(false);
  editId = signal<number | null>(null);
  isSystem = signal(false);

  form = this.fb.group({
    name: ['', [Validators.required, Validators.minLength(2)]],
    description: [''],
  });

  ngOnInit(): void {
    const id = this.route.snapshot.paramMap.get('id');
    if (id) {
      this.isEdit.set(true);
      this.editId.set(+id);
      this.loading.set(true);
      this.categoryService.get(+id).subscribe({
        next: cat => {
          this.form.patchValue(cat);
          // Categorias do sistema sao globais: aparecem para todos os tenants e
          // nao pertencem a ninguem. O backend rejeita o PUT com 403; aqui o
          // acesso direto pela URL e bloqueado antes do usuario digitar.
          if (cat.tenant_id === 'system') {
            this.isSystem.set(true);
            this.form.disable();
            this.errorMessage.set('Categorias do sistema não podem ser editadas.');
          }
          this.loading.set(false);
        },
        error: () => { this.errorMessage.set('Erro ao carregar categoria.'); this.loading.set(false); },
      });
    }
  }

  submit(): void {
    if (this.isSystem()) return;
    if (this.form.invalid) { this.form.markAllAsTouched(); return; }
    this.saving.set(true);
    const payload = this.form.getRawValue() as { name: string; description: string };

    const req$ = this.isEdit()
      ? this.categoryService.update(this.editId()!, payload)
      : this.categoryService.create(payload);

    req$.subscribe({
      next: () => this.router.navigate(['/categories']),
      error: err => {
        this.saving.set(false);
        this.errorMessage.set(err?.error?.detail ?? 'Erro ao salvar categoria.');
      },
    });
  }

  hasError(field: string): boolean {
    const c = this.form.get(field);
    return !!(c?.invalid && c?.touched);
  }
}
