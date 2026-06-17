import { CanActivateFn, Router } from '@angular/router';
import { inject } from '@angular/core';
import { AuthService } from './auth.service';

export const authGuard: CanActivateFn = () => {
  const auth = inject(AuthService);
  const router = inject(Router);

  if (auth.isAuthenticated) {
    return true;
  }

  // Keycloak init with onLoad: 'login-required' already handles redirect,
  // but as a safety net we redirect to root which triggers Keycloak again.
  return router.createUrlTree(['/']);
};
