import { Component, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { ExpenseService } from '../../../core/services/expense.service';

interface RowError { row: number; error: string; }

@Component({
  selector: 'app-expense-import',
  standalone: true,
  imports: [RouterLink],
  templateUrl: './expense-import.component.html',
  styleUrls: ['./expense-import.component.scss'],
})
export class ExpenseImportComponent {
  private expenseService = inject(ExpenseService);

  file = signal<File | null>(null);
  importing = signal(false);
  successCount = signal<number | null>(null);
  errorMessage = signal('');
  rowErrors = signal<RowError[]>([]);

  onFileSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    this.file.set(input.files?.[0] ?? null);
    this.successCount.set(null);
    this.errorMessage.set('');
    this.rowErrors.set([]);
  }

  downloadTemplate(): void {
    this.expenseService.downloadTemplate().subscribe({
      next: blob => {
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'template_gastos.xlsx';
        a.click();
        URL.revokeObjectURL(url);
      },
      error: () => this.errorMessage.set('Erro ao baixar o template. Tente novamente.'),
    });
  }

  importFile(): void {
    const f = this.file();
    if (!f || this.importing()) { return; }
    this.importing.set(true);
    this.successCount.set(null);
    this.errorMessage.set('');
    this.rowErrors.set([]);

    this.expenseService.importExcel(f).subscribe({
      next: res => {
        this.importing.set(false);
        this.successCount.set(res?.created ?? 0);
      },
      error: err => {
        this.importing.set(false);
        const body = err?.error;
        if (body?.errors?.length) {
          this.rowErrors.set(body.errors);
        }
        this.errorMessage.set(body?.message ?? 'Erro ao importar a planilha. Verifique o arquivo e tente novamente.');
      },
    });
  }
}
