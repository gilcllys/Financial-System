import { Routes } from '@angular/router';
import { LayoutComponent } from './layout/layout.component';
import { authGuard } from './core/auth/auth.guard';

export const routes: Routes = [
  {
    path: '',
    component: LayoutComponent,
    canActivate: [authGuard],
    children: [
      { path: '', redirectTo: 'home', pathMatch: 'full' },

      {
        path: 'home',
        loadComponent: () =>
          import('./features/home/home.component').then(m => m.HomeComponent),
      },

            // Expenses
      { path: 'expenses', redirectTo: 'home', pathMatch: 'full' },
      {
        path: 'expenses/new',
        loadComponent: () =>
          import('./features/expenses/expense-form/expense-form.component').then(m => m.ExpenseFormComponent),
      },
      {
        path: 'expenses/batch',
        loadComponent: () =>
          import('./features/expenses/expense-batch/expense-batch.component').then(m => m.ExpenseBatchComponent),
      },
      {
        path: 'expenses/import',
        loadComponent: () =>
          import('./features/expenses/expense-import/expense-import.component').then(m => m.ExpenseImportComponent),
      },
      {
        path: 'expenses/:id/edit',
        loadComponent: () =>
          import('./features/expenses/expense-form/expense-form.component').then(m => m.ExpenseFormComponent),
      },

      // Cards
      {
        path: 'cards',
        loadComponent: () =>
          import('./features/cards/card-list/card-list.component').then(m => m.CardListComponent),
      },
      {
        path: 'cards/new',
        loadComponent: () =>
          import('./features/cards/card-form/card-form.component').then(m => m.CardFormComponent),
      },
      {
        path: 'cards/:id/edit',
        loadComponent: () =>
          import('./features/cards/card-form/card-form.component').then(m => m.CardFormComponent),
      },
      {
        path: 'cards/:id/expenses',
        loadComponent: () =>
          import('./features/cards/card-expenses/card-expenses.component').then(m => m.CardExpensesComponent),
      },

      // Categories
      {
        path: 'categories',
        loadComponent: () =>
          import('./features/categories/category-list/category-list.component').then(m => m.CategoryListComponent),
      },
      {
        path: 'categories/new',
        loadComponent: () =>
          import('./features/categories/category-form/category-form.component').then(m => m.CategoryFormComponent),
      },
      {
        path: 'categories/:id/edit',
        loadComponent: () =>
          import('./features/categories/category-form/category-form.component').then(m => m.CategoryFormComponent),
      },

      // Reports
      {
        path: 'reports',
        loadComponent: () =>
          import('./features/reports/reports.component').then(m => m.ReportsComponent),
      },

      // Installments
      {
        path: 'installments',
        loadComponent: () =>
          import('./features/installments/installments.component').then(m => m.InstallmentsComponent),
      },

      // Supermarket
      {
        path: 'supermarket',
        loadComponent: () =>
          import('./features/supermarket/supermarket-list/supermarket-list.component').then(m => m.SupermarketListComponent),
      },
      {
        path: 'supermarket/new',
        loadComponent: () =>
          import('./features/supermarket/supermarket-form/supermarket-form.component').then(m => m.SupermarketFormComponent),
      },
      {
        path: 'supermarket/:id/edit',
        loadComponent: () =>
          import('./features/supermarket/supermarket-form/supermarket-form.component').then(m => m.SupermarketFormComponent),
      },
      {
        path: 'supermarket/:id',
        loadComponent: () =>
          import('./features/supermarket/supermarket-detail/supermarket-detail.component').then(m => m.SupermarketDetailComponent),
      },

      // Histórico
      { path: 'history', redirectTo: 'home', pathMatch: 'full' },

      // Sem categoria
      { path: 'uncategorized', redirectTo: 'home', pathMatch: 'full' },

      // Analytics
      {
        path: 'analytics',
        loadComponent: () =>
          import('./features/analytics/analytics.component').then(m => m.AnalyticsComponent),
      },

      // Shared Debts (Dívida Compartilhada)
      {
        path: 'shared-debts',
        loadComponent: () =>
          import('./features/shared-debts/shared-debts-list/shared-debts-list.component').then(m => m.SharedDebtsListComponent),
      },
      {
        path: 'shared-debts/join/:token',
        loadComponent: () =>
          import('./features/shared-debts/shared-debt-join/shared-debt-join.component').then(m => m.SharedDebtJoinComponent),
      },
      {
        path: 'shared-debts/:id',
        loadComponent: () =>
          import('./features/shared-debts/shared-debt-detail/shared-debt-detail.component').then(m => m.SharedDebtDetailComponent),
      },
      { path: 'vitoria', redirectTo: 'shared-debts', pathMatch: 'full' },

    ],
  },

  // Wildcard
  { path: '**', redirectTo: '' },
];
