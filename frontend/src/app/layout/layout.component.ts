import { Component, OnInit, inject, HostListener, signal } from '@angular/core';
import { Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { AuthService } from '../core/auth/auth.service';
import { ExpenseService } from '../core/services/expense.service';
import { SupermarketService } from '../core/services/supermarket.service';
import { SavingsService } from '../core/services/savings.service';
import { forkJoin, of } from 'rxjs';
import { catchError } from 'rxjs/operators';

@Component({
  selector: 'app-layout',
  standalone: true,
  imports: [RouterLink, RouterLinkActive, RouterOutlet],
  templateUrl: './layout.component.html',
  styleUrls: ['./layout.component.scss'],
})
export class LayoutComponent implements OnInit {
  private auth = inject(AuthService);
  private router = inject(Router);
  private expenseService = inject(ExpenseService);
  private supermarketService = inject(SupermarketService);
  private savingsService = inject(SavingsService);

  /** Controls the mobile drawer (sidebar slide-in) */
  drawerOpen = signal(false);

  /** Count of expenses assigned to the stable uncategorized category. */
  uncategorizedCount = signal(0);
  hasMarketData = signal(false);
  hasInvestmentData = signal(false);

  ngOnInit(): void {
    this.loadUncategorizedCount();
    forkJoin({
      market: this.supermarketService.list().pipe(catchError(() => of([]))),
      goals: this.savingsService.listGoals().pipe(catchError(() => of([]))),
    }).subscribe(({ market, goals }) => {
      this.hasMarketData.set(market.length > 0);
      this.hasInvestmentData.set(goals.length > 0);
    });
  }

  private loadUncategorizedCount(): void {
    this.expenseService
      .list({ category_key: 'uncategorized', page: 1, page_size: 1 })
      .subscribe({ next: res => this.uncategorizedCount.set(res.count), error: () => {} });
  }

  userName(): string {
    return this.auth.userProfile.name ?? 'Usuário';
  }

  userEmail(): string {
    return this.auth.userProfile.email ?? '';
  }

  userInitials(): string {
    return this.userName()
      .split(' ')
      .map(p => p[0] ?? '')
      .slice(0, 2)
      .join('')
      .toUpperCase();
  }

  currentPageLabel(): string {
    const routeLabels: Record<string, string> = {
      '/home': 'Início',
      '/history': 'Histórico',
      '/cards': 'Cartões',
      '/installments': 'Parcelamentos',
      '/recurring-expenses': 'Gastos fixos',
      '/analytics': 'Análises',
      '/shared-debts': 'Grupos compartilhados',
      '/categories': 'Categorias',
      '/uncategorized': 'Sem categoria',
      '/supermarket': 'Supermercado',
      '/savings': 'Investimentos',
      '/expenses/new': 'Novo lançamento',
    };
    const path = this.router.url.split('?')[0].replace(/\/$/, '') || '/home';
    const matchedRoute = Object.keys(routeLabels)
      .sort((first, second) => second.length - first.length)
      .find(route => path === route || path.startsWith(`${route}/`));
    return matchedRoute ? routeLabels[matchedRoute] : 'Financeiro';
  }

  toggleDrawer(): void {
    this.drawerOpen.update(v => !v);
  }

  closeDrawer(): void {
    this.drawerOpen.set(false);
  }

  logout(): void {
    this.auth.logout();
  }


  @HostListener('document:keydown.escape')
  onEscape(): void {
    this.closeDrawer();
  }
}

