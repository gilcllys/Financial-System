import { Component, OnInit, inject, HostListener, signal } from '@angular/core';
import { Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { AuthService } from '../core/auth/auth.service';
import { ExpenseService } from '../core/services/expense.service';

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

  /** Controls the mobile drawer (sidebar slide-in) */
  drawerOpen = signal(false);

  /** Count of uncategorized expenses (category_id = 11) for the badge */
  uncategorizedCount = signal(0);

  ngOnInit(): void {
    this.loadUncategorizedCount();
  }

  private loadUncategorizedCount(): void {
    this.expenseService
      .list({ category_id: 11, page: 1, page_size: 1 })
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

  toggleDrawer(): void {
    this.drawerOpen.update(v => !v);
  }

  closeDrawer(): void {
    this.drawerOpen.set(false);
  }

  logout(): void {
    this.auth.logout();
  }

  goToNewExpense(): void {
    this.router.navigate(['/expenses/new']);
  }

  @HostListener('document:keydown.escape')
  onEscape(): void {
    this.closeDrawer();
  }
}

