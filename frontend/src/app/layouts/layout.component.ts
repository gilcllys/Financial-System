import { CommonModule, isPlatformBrowser } from '@angular/common';
import type { OnInit } from '@angular/core';
import {
    Component,
    HostListener,
    inject,
    PLATFORM_ID,
    signal,
} from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';
import { NavigationEnd, Router, RouterOutlet } from '@angular/router';
import { filter } from 'rxjs';
import { ThemeService } from '../services/theme.service';

@Component({
  selector: 'app-layout',
  standalone: true,
  imports: [
    CommonModule,
    MatIconModule,
    MatButtonModule,
    MatTooltipModule,
    RouterOutlet,
  ],
  templateUrl: './layout.component.html',
  styleUrl: './layout.component.css',
})
export class LayoutComponent implements OnInit {
  private router = inject(Router);
  private platformId = inject(PLATFORM_ID);
  public themeService = inject(ThemeService);
  isSidenavOpen = signal(true);
  currentRoute = signal<string>('');
  isMobile = signal(false);

  ngOnInit() {
    if (isPlatformBrowser(this.platformId)) {
      this.checkScreenSize();
    }
    this.router.events
      .pipe(filter((event) => event instanceof NavigationEnd))
      .subscribe((event: NavigationEnd) => {
        this.currentRoute.set(event.url);
      });
  }

  @HostListener('window:resize', ['$event'])
  onResize(event: Event) {
    if (isPlatformBrowser(this.platformId)) {
      this.checkScreenSize();
    }
  }

  private checkScreenSize() {
    if (isPlatformBrowser(this.platformId)) {
      this.isMobile.set(window.innerWidth < 768);
      // Fechar sidenav em mobile, abrir em desktop
      if (this.isMobile()) {
        this.isSidenavOpen.set(false);
      } else {
        this.isSidenavOpen.set(true);
      }
    }
  }

  toggleSidenav() {
    this.isSidenavOpen.update((value) => !value);
  }

  closeSidenav() {
    if (this.isMobile()) {
      this.isSidenavOpen.set(false);
    }
  }

  navigateTo(route: string) {
    this.router.navigate([route]);
    this.closeSidenav();
  }

  isActive(route: string): boolean {
    return this.currentRoute().includes(route);
  }

  toggleTheme() {
    this.themeService.toggleTheme();
  }

  getThemeIcon(): string {
    return this.themeService.isDarkTheme() ? 'light_mode' : 'dark_mode';
  }

  getThemeLabel(): string {
    return this.themeService.isDarkTheme() ? 'Tema Claro' : 'Tema Escuro';
  }

  menuItems = [
    { label: 'Dashboard', icon: 'dashboard', route: '/dashboard' },
    { label: 'Transações', icon: 'swap_horiz', route: '/transactions' },
    { label: 'Orçamentos', icon: 'trending_up', route: '/budgets' },
    { label: 'Relatórios', icon: 'assessment', route: '/reports' },
  ];
}
