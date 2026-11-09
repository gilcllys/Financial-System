import { ApplicationConfig, APP_INITIALIZER } from '@angular/core';
import { provideRouter, withPreloading, PreloadAllModules } from '@angular/router';
import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { routes } from './app.routes';
import { authInterceptor } from './core/auth/auth.interceptor';
import { AuthService } from './core/auth/auth.service';
import { RouteLoadingService } from './core/services/route-loading.service';

function initializeKeycloak(
  auth: AuthService,
  _routeLoading: RouteLoadingService
): () => Promise<boolean> {
  return () => auth.init();
}

export const appConfig: ApplicationConfig = {
  providers: [
    provideRouter(routes, withPreloading(PreloadAllModules)),
    provideHttpClient(withInterceptors([authInterceptor])),
    {
      provide: APP_INITIALIZER,
      useFactory: initializeKeycloak,
      deps: [AuthService, RouteLoadingService],
      multi: true,
    },
  ],
};
