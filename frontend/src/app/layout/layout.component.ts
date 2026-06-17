import { Component, inject, HostListener, signal } from '@angular/core';
import { Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { AuthService } from '../core/auth/auth.service';

@Component({
  selector: 'app-layout',
  standalone: true,
  imports: [RouterLink, RouterLinkActive, RouterOutlet],
  template: `
    <!-- ── Top Navbar ── -->
    <header class="navbar" role="banner">
      <div class="navbar__inner container">
        <a routerLink="/expenses" class="navbar__brand" aria-label="Financial System home">
          <span class="navbar__logo">₿</span>
          <span class="navbar__name">FinanceApp</span>
        </a>

        <!-- Desktop nav -->
        <nav class="navbar__nav" aria-label="Main navigation">
          <a routerLink="/expenses" routerLinkActive="active" class="navbar__link">Gastos</a>
          <a routerLink="/history" routerLinkActive="active" class="navbar__link">Histórico</a>
          <a routerLink="/cards" routerLinkActive="active" class="navbar__link">Cartões</a>
          <a routerLink="/installments" routerLinkActive="active" class="navbar__link">Parcelamentos</a>
          <a routerLink="/supermarket" routerLinkActive="active" class="navbar__link">Supermercado</a>
          <a routerLink="/reports" routerLinkActive="active" class="navbar__link">Relatórios</a>
          <a routerLink="/analytics" routerLinkActive="active" class="navbar__link">Análises</a>
          <a routerLink="/vitoria" routerLinkActive="active" class="navbar__link">💑 Casal</a>
          <a routerLink="/categories" routerLinkActive="active" class="navbar__link">Categorias</a>
        </nav>

        <!-- User section -->
        <div class="navbar__user">
          <span class="navbar__username" [title]="userEmail()">{{ userName() }}</span>
          <button class="btn btn--secondary btn--sm" (click)="logout()" aria-label="Sair da conta">
            Sair
          </button>
          <!-- Hamburger -->
          <button
            class="navbar__hamburger"
            (click)="toggleMobileMenu()"
            [attr.aria-expanded]="mobileMenuOpen()"
            aria-controls="mobile-menu"
            aria-label="Menu de navegação"
          >
            <span class="hamburger-bar"></span>
            <span class="hamburger-bar"></span>
            <span class="hamburger-bar"></span>
          </button>
        </div>
      </div>

      <!-- Mobile dropdown menu -->
      @if (mobileMenuOpen()) {
        <nav id="mobile-menu" class="navbar__mobile-menu" aria-label="Mobile navigation">
          <a routerLink="/expenses" routerLinkActive="active" class="navbar__mobile-link" (click)="closeMobileMenu()">
            <span class="nav-icon">💰</span> Gastos
          </a>
          <a routerLink="/cards" routerLinkActive="active" class="navbar__mobile-link" (click)="closeMobileMenu()">
            <span class="nav-icon">💳</span> Cartões
          </a>
          <a routerLink="/installments" routerLinkActive="active" class="navbar__mobile-link" (click)="closeMobileMenu()">
            <span class="nav-icon">📅</span> Parcelamentos
          </a>
          <a routerLink="/supermarket" routerLinkActive="active" class="navbar__mobile-link" (click)="closeMobileMenu()">
            <span class="nav-icon">🛒</span> Supermercado
          </a>
          <a routerLink="/reports" routerLinkActive="active" class="navbar__mobile-link" (click)="closeMobileMenu()">
            <span class="nav-icon">📊</span> Relatórios
          </a>
          <a routerLink="/categories" routerLinkActive="active" class="navbar__mobile-link" (click)="closeMobileMenu()">
            <span class="nav-icon">🏷️</span> Categorias
          </a>
          <hr class="divider" />
          <div class="navbar__mobile-user">
            <span class="navbar__username">{{ userName() }}</span>
            <button class="btn btn--danger btn--sm" (click)="logout()">Sair</button>
          </div>
        </nav>
      }
    </header>

    <!-- ── Main content ── -->
    <main class="page-content" id="main-content">
      <div class="container">
        <router-outlet />
      </div>
    </main>

    <!-- ── Bottom navigation (mobile) ── -->
    <nav class="bottom-nav" aria-label="Bottom navigation" role="navigation">
      <a routerLink="/expenses" routerLinkActive="bottom-nav__item--active" class="bottom-nav__item">
        <span class="bottom-nav__icon">💰</span>
        <span class="bottom-nav__label">Gastos</span>
      </a>
      <a routerLink="/cards" routerLinkActive="bottom-nav__item--active" class="bottom-nav__item">
        <span class="bottom-nav__icon">💳</span>
        <span class="bottom-nav__label">Cartões</span>
      </a>
      <a routerLink="/supermarket" routerLinkActive="bottom-nav__item--active" class="bottom-nav__item">
        <span class="bottom-nav__icon">🛒</span>
        <span class="bottom-nav__label">Mercado</span>
      </a>
      <a routerLink="/analytics" routerLinkActive="bottom-nav__item--active" class="bottom-nav__item">
        <span class="bottom-nav__icon">📈</span>
        <span class="bottom-nav__label">Análises</span>
      </a>
      <a routerLink="/vitoria" routerLinkActive="bottom-nav__item--active" class="bottom-nav__item">
        <span class="bottom-nav__icon">💑</span>
        <span class="bottom-nav__label">Casal</span>
      </a>
    </nav>

    <!-- ── FAB ── -->
    <button class="fab" (click)="goToNewExpense()" aria-label="Novo gasto">+</button>
  `,
  styleUrls: ['./layout.component.scss'],
})
export class LayoutComponent {
  private auth = inject(AuthService);
  private router = inject(Router);

  mobileMenuOpen = signal(false);

  userName(): string {
    return this.auth.userProfile.name ?? 'Usuário';
  }

  userEmail(): string {
    return this.auth.userProfile.email ?? '';
  }

  toggleMobileMenu(): void {
    this.mobileMenuOpen.update(v => !v);
  }

  closeMobileMenu(): void {
    this.mobileMenuOpen.set(false);
  }

  logout(): void {
    this.auth.logout();
  }

  goToNewExpense(): void {
    this.router.navigate(['/expenses/new']);
  }

  @HostListener('document:keydown.escape')
  onEscape(): void {
    this.closeMobileMenu();
  }
}
