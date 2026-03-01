import { isPlatformBrowser } from '@angular/common';
import type { HttpHeaders, HttpParams } from '@angular/common/http';
import { HttpClient } from '@angular/common/http';
import {
  Injectable,
  PLATFORM_ID,
  computed,
  inject,
  signal,
} from '@angular/core';
import type { Observable } from 'rxjs';
import { throwError } from 'rxjs';
import { catchError, map } from 'rxjs/operators';
import type { UserRegister } from '../models';
import { LoginResponse, RegisterResponse, UserLogin } from '../models';
import { API_BASE_URL } from '../utils/constants';

@Injectable({
  providedIn: 'root',
})
export class AuthService {
  protected httpOptions: {
    headers?: HttpHeaders;
    params?: HttpParams;
  } = {};

  private http = inject(HttpClient);
  private platformId = inject(PLATFORM_ID);
  private isBrowser = isPlatformBrowser(this.platformId);

  // O sinal armazena o estado de autenticação (privado para segurança)
  private _isAuthenticated = signal<boolean>(this.hasToken());

  // Exposição pública apenas para leitura
  isAuthenticated = computed(() => this._isAuthenticated());

  // Verifica se existe um token no localStorage ao iniciar
  private hasToken(): boolean {
    if (!this.isBrowser) {
      return false;
    }
    return !!localStorage.getItem('access_token');
  }

  /**
   * Realiza login do usuário
   * @param email - Email do usuário
   * @param password - Senha do usuário
   * @returns Observable com a resposta do login
   */
  loginUser(email: string, password: string): Observable<LoginResponse> {
    // Cria o objeto de login usando a classe UserLogin
    const loginData = UserLogin.fromEmail(email, password);

    return this.http
      .post<{
        access: string;
        refresh: string;
        user?: unknown;
      }>(`${API_BASE_URL}/api/login/`, loginData.toJson())
      .pipe(
        map((response) => {
          // Converte a resposta para classe LoginResponse
          const loginResponse = LoginResponse.fromJson(response);

          // Armazena os tokens (apenas no navegador)
          if (this.isBrowser) {
            localStorage.setItem('access_token', loginResponse.access);
            localStorage.setItem('refresh_token', loginResponse.refresh);
            if (loginResponse.user) {
              localStorage.setItem('user', JSON.stringify(loginResponse.user));
            }
          }
          this._isAuthenticated.set(true);

          return loginResponse;
        }),
        catchError((error) => {
          console.error('Erro no login:', error);
          return throwError(() => error);
        }),
      );
  }

  /**
   * Registra um novo usuário
   * @param userData - Dados do usuário para registro
   * @returns Observable com a resposta do registro
   */
  registerUser(userData: UserRegister): Observable<RegisterResponse> {
    return this.http
      .post<{
        id: number;
        email: string;
        username: string;
      }>(`${API_BASE_URL}/api/register/`, userData.toJson())
      .pipe(
        map((response) => {
          // Converte a resposta para classe RegisterResponse
          return RegisterResponse.fromJson(response);
        }),
        catchError((error) => {
          console.error('Erro no registro:', error);
          return throwError(() => error);
        }),
      );
  }

  /**
   * Método legado para compatibilidade
   */
  login(token: string) {
    if (this.isBrowser) {
      localStorage.setItem('access_token', token);
    }
    this._isAuthenticated.set(true);
  }

  /**
   * Método legado para compatibilidade
   */
  register(_userData: UserRegister): void {
    // Este método agora deve usar registerUser()
    console.warn('Use registerUser() ao invés de register()');
  }

  logout() {
    if (this.isBrowser) {
      localStorage.removeItem('access_token');
      localStorage.removeItem('refresh_token');
      localStorage.removeItem('user');
    }
    this._isAuthenticated.set(false);
  }

  /**
   * Obtém o token de acesso
   */
  getAccessToken(): string | null {
    if (!this.isBrowser) {
      return null;
    }
    return localStorage.getItem('access_token');
  }

  /**
   * Obtém o refresh token
   */
  getRefreshToken(): string | null {
    if (!this.isBrowser) {
      return null;
    }
    return localStorage.getItem('refresh_token');
  }

  /**
   * Obtém os dados do usuário
   */
  getUser(): { id: number; email: string; name: string } | null {
    if (!this.isBrowser) {
      return null;
    }
    const userStr = localStorage.getItem('user');
    return userStr ? JSON.parse(userStr) : null;
  }

  // Método usado pelo Guard que criamos antes
  isLoggedIn(): boolean {
    return this._isAuthenticated();
  }
}
