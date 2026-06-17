import { Routes } from '@angular/router';
import { LayoutComponent } from './layout/layout.component';
import { authGuard } from './core/auth/auth.guard';

export const routes: Routes = [
  {
    path: '',
    component: LayoutComponent,
    canActivate: [authGuard],
    children: [
      { path: '', redirectTo: 'expenses', pathMatch: 'full' },

      // Expenses
      {
        path: 'expenses',
        loadComponent: () =>
          import('./features/expenses/expense-list/expense-list.component').then(m => m.ExpenseListComponent),
      },
      {
        path: 'expenses/new',
        loadComponent: () =>
          import('./features/expenses/expense-form/expense-form.component').then(m => m.ExpenseFormComponent),
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

      // Histórico (todos os gastos, sem filtro de mês padrão)
      {
        path: 'history',
        loadComponent: () =>
          import('./features/expenses/expense-list/expense-list.component').then(m => m.ExpenseListComponent),
        data: { historyMode: true },
      },

      // Analytics
      {
        path: 'analytics',
        loadComponent: () =>
          import('./features/analytics/analytics.component').then(m => m.AnalyticsComponent),
      },

      // Vitória Debts
      {
        path: 'vitoria',
        loadComponent: () =>
          import('./features/vitoria/vitoria.component').then(m => m.VitoriaComponent),
      },

    ],
  },

  // Wildcard
  { path: '**', redirectTo: '' },
];
