import type { OnInit } from '@angular/core';
import {
  Component,
  signal,
  inject,
  HostListener,
  PLATFORM_ID,
} from '@angular/core';
import { isPlatformBrowser } from '@angular/common';
import { CommonModule } from '@angular/common';
import { Router, NavigationEnd } from '@angular/router';
import { RouterOutlet } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { filter } from 'rxjs';

@Component({
  selector: 'app-layout',
  standalone: true,
  imports: [CommonModule, MatIconModule, MatButtonModule, RouterOutlet],
  templateUrl: './layout.component.html',
  styleUrl: './layout.component.css',
})
export class LayoutComponent implements OnInit {
  private router = inject(Router);
  private platformId = inject(PLATFORM_ID);
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

  menuItems = [
    { label: 'Dashboard', icon: 'dashboard', route: '/dashboard' },
    { label: 'Transações', icon: 'swap_horiz', route: '/transactions' },
    { label: 'Orçamentos', icon: 'trending_up', route: '/budgets' },
    { label: 'Relatórios', icon: 'assessment', route: '/reports' },
  ];
}
