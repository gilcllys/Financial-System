import { Injectable } from '@angular/core';
import Keycloak from 'keycloak-js';
import { environment } from '../../../environments/environment';

@Injectable({ providedIn: 'root' })
export class AuthService {
  private keycloak: Keycloak;
  private _initialized = false;

  constructor() {
    this.keycloak = new Keycloak({
      url: environment.keycloak.url,
      realm: environment.keycloak.realm,
      clientId: environment.keycloak.clientId,
    });
  }

  async init(): Promise<boolean> {
    try {
      const authenticated = await this.keycloak.init({
        // check-sso: verifica silenciosamente se há sessão SSO ativa no Keycloak.
        // Se houver → loga automaticamente sem redirect.
        // Se não houver → retorna false sem forçar login (o guard redireciona).
        onLoad: 'check-sso',
        pkceMethod: 'S256',
        checkLoginIframe: false,
        silentCheckSsoRedirectUri: window.location.origin + '/silent-check-sso.html',
        redirectUri: window.location.origin,
      });
      this._initialized = true;

      if (authenticated) {
        this.scheduleTokenRefresh();
      } else {
        // Sessão não encontrada — redireciona para login
        await this.keycloak.login({ redirectUri: window.location.origin });
      }

      return authenticated;
    } catch (err) {
      console.error('[AuthService] Keycloak init failed', err);
      return false;
    }
  }

  private scheduleTokenRefresh(): void {
    setInterval(async () => {
      try {
        await this.keycloak.updateToken(60);
      } catch {
        console.warn('[AuthService] Token refresh failed, redirecting to login');
        this.keycloak.login();
      }
    }, 30_000);
  }

  get token(): string | undefined {
    return this.keycloak.token;
  }

  get isAuthenticated(): boolean {
    return !!this.keycloak.authenticated;
  }

  get userProfile(): { name?: string; email?: string; sub?: string } {
    const parsed = this.keycloak.tokenParsed;
    return {
      name: parsed?.['name'] ?? parsed?.['preferred_username'],
      email: parsed?.['email'],
      sub: parsed?.['sub'],
    };
  }

  logout(): void {
    this.keycloak.logout({ redirectUri: window.location.origin });
  }
}
