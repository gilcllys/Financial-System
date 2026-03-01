import type { Routes } from '@angular/router';
import { LayoutComponent } from './layouts/layout.component';
import { DashboardComponent } from './screens/dashboard/dashboard.component';
import { LoginComponent } from './screens/login/login.component';
import { NewTransactionComponent } from './screens/new-transaction/new-transaction.component';
import { RegisterComponent } from './screens/register/register.component';
import { ReportsComponent } from './screens/reports/reports.component';
import { TransactionsComponent } from './screens/transactions/transactions.component';

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
        children: [
          {
            path: 'new',
            component: NewTransactionComponent,
          },
        ],
      },
      {
        path: 'reports',
        component: ReportsComponent,
      },
    ],
  },
];
