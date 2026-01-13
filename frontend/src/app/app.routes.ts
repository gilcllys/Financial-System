import type { Routes } from '@angular/router';
import { LoginComponent } from './screens/login/login.component';
import { RegisterComponent } from './screens/register/register.component';
import { LayoutComponent } from './layouts/layout.component';
import { DashboardComponent } from './screens/dashboard/dashboard.component';
import { TransactionsComponent } from './screens/transactions/transactions.component';
import { BudgetsComponent } from './screens/budgets/budgets.component';
import { ReportsComponent } from './screens/reports/reports.component';

export const routes: Routes = [
  {
    path: '',
    component: LoginComponent,
  },
  {
    path: 'register',
    component: RegisterComponent,
  },
  {
    path: '',
    component: LayoutComponent,
    children: [
      {
        path: 'dashboard',
        component: DashboardComponent,
      },
      {
        path: 'transactions',
        component: TransactionsComponent,
      },
      {
        path: 'budgets',
        component: BudgetsComponent,
      },
      {
        path: 'reports',
        component: ReportsComponent,
      },
    ],
  },
];
