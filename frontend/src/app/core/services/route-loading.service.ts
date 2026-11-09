import { Injectable, signal } from '@angular/core';
import {
  NavigationCancel,
  NavigationEnd,
  NavigationError,
  NavigationStart,
  Router,
} from '@angular/router';
import { filter } from 'rxjs/operators';

/** Shows a shared page loader while a route and its initial API requests resolve. */
@Injectable({ providedIn: 'root' })
export class RouteLoadingService {
  readonly isLoading = signal(false);

  private activeNavigationId: number | null = null;
  private pendingRequests = 0;
  private navigationResolved = false;
  private showTimer: ReturnType<typeof setTimeout> | null = null;
  private readonly showDelayMs = 140;

  constructor(router: Router) {
    router.events
      .pipe(
        filter(
          event =>
            event instanceof NavigationStart ||
            event instanceof NavigationEnd ||
            event instanceof NavigationCancel ||
            event instanceof NavigationError
        )
      )
      .subscribe(event => {
        if (event instanceof NavigationStart) {
          this.startNavigation(event.id);
        } else if (event instanceof NavigationEnd) {
          this.finishNavigation(event.id);
        } else {
          this.cancelNavigation(event.id);
        }
      });
  }

  /** Returns an id only for API requests that belong to the active navigation. */
  requestStarted(): number | null {
    if (this.activeNavigationId === null) return null;
    this.pendingRequests += 1;
    return this.activeNavigationId;
  }

  requestFinished(navigationId: number | null): void {
    if (navigationId === null || navigationId !== this.activeNavigationId) return;
    this.pendingRequests = Math.max(0, this.pendingRequests - 1);
    this.hideWhenSettled();
  }

  private startNavigation(id: number): void {
    this.clearShowTimer();
    this.isLoading.set(false);
    this.activeNavigationId = id;
    this.pendingRequests = 0;
    this.navigationResolved = false;
    this.showTimer = setTimeout(() => {
      this.showTimer = null;
      if (this.activeNavigationId === id) this.isLoading.set(true);
    }, this.showDelayMs);
  }

  private finishNavigation(id: number): void {
    if (id !== this.activeNavigationId) return;
    this.navigationResolved = true;
    this.hideWhenSettled();
  }

  private cancelNavigation(id: number): void {
    if (id !== this.activeNavigationId) return;
    this.activeNavigationId = null;
    this.pendingRequests = 0;
    this.navigationResolved = false;
    this.clearShowTimer();
    this.isLoading.set(false);
  }

  private hideWhenSettled(): void {
    if (!this.navigationResolved || this.pendingRequests !== 0) return;
    this.clearShowTimer();
    this.isLoading.set(false);
    this.activeNavigationId = null;
    this.navigationResolved = false;
  }

  private clearShowTimer(): void {
    if (this.showTimer !== null) {
      clearTimeout(this.showTimer);
      this.showTimer = null;
    }
  }
}
