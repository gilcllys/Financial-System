import { Component, OnInit, inject, signal, computed } from '@angular/core';
import { RouterLink } from '@angular/router';
import { CategoryService } from '../../../core/services/category.service';
import { ExpenseCategory } from '../../../core/models';

@Component({
  selector: 'app-category-list',
  standalone: true,
  imports: [RouterLink],
  templateUrl: './category-list.component.html',
  styleUrls: ['./category-list.component.scss'],
})
export class CategoryListComponent implements OnInit {
  private categoryService = inject(CategoryService);

  categories = signal<ExpenseCategory[]>([]);
  loading = signal(true);
  deletingId = signal<number | null>(null);

  systemCategories = computed(() => this.categories().filter(c => c.tenant_id === 'system'));
  customCategories = computed(() => this.categories().filter(c => c.tenant_id !== 'system'));

  ngOnInit(): void {
    this.load();
  }

  private load(): void {
    this.categoryService.list().subscribe({
      next: data => { this.categories.set(data); this.loading.set(false); },
      error: () => this.loading.set(false),
    });
  }

  delete(cat: ExpenseCategory): void {
    if (cat.tenant_id === 'system') return;
    if (!confirm(`Excluir categoria "${cat.name}"?`)) return;
    this.deletingId.set(cat.id);
    this.categoryService.delete(cat.id).subscribe({
      next: () => { this.categories.update(list => list.filter(c => c.id !== cat.id)); this.deletingId.set(null); },
      error: () => this.deletingId.set(null),
    });
  }
}
