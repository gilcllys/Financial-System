import { isPlatformBrowser } from '@angular/common';
import { effect, Inject, Injectable, PLATFORM_ID, signal } from '@angular/core';

export type Theme = 'light' | 'dark';

@Injectable({
  providedIn: 'root',
})
export class ThemeService {
  // Signal para armazenar o tema atual
  currentTheme = signal<Theme>('dark');

  constructor(@Inject(PLATFORM_ID) private platformId: object) {
    // Carregar tema salvo apenas no browser
    if (isPlatformBrowser(this.platformId)) {
      const savedTheme = localStorage.getItem('theme') as Theme;
      if (savedTheme) {
        this.currentTheme.set(savedTheme);
      } else {
        // Detectar preferência do sistema
        const prefersDark = window.matchMedia(
          '(prefers-color-scheme: dark)',
        ).matches;
        this.currentTheme.set(prefersDark ? 'dark' : 'light');
      }

      // Aplicar tema inicial
      this.applyTheme(this.currentTheme());

      // Effect para aplicar tema quando mudar
      effect(() => {
        this.applyTheme(this.currentTheme());
      });
    }
  }

  /**
   * Alterna entre tema dark e light
   */
  toggleTheme(): void {
    const newTheme = this.currentTheme() === 'dark' ? 'light' : 'dark';
    this.setTheme(newTheme);
  }

  /**
   * Define um tema específico
   */
  setTheme(theme: Theme): void {
    this.currentTheme.set(theme);
    if (isPlatformBrowser(this.platformId)) {
      localStorage.setItem('theme', theme);
    }
  }

  /**
   * Aplica o tema ao documento
   */
  private applyTheme(theme: Theme): void {
    if (isPlatformBrowser(this.platformId)) {
      const root = document.documentElement;
      root.classList.remove('light-theme', 'dark-theme');
      root.classList.add(`${theme}-theme`);
      root.setAttribute('data-theme', theme);
    }
  }

  /**
   * Retorna true se o tema atual é dark
   */
  isDarkTheme(): boolean {
    return this.currentTheme() === 'dark';
  }

  /**
   * Retorna true se o tema atual é light
   */
  isLightTheme(): boolean {
    return this.currentTheme() === 'light';
  }
}
