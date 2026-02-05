import { Injectable } from '@angular/core';
import type { UserRegister } from '../interfaces/userRegister';

@Injectable({
  providedIn: 'root',
})
export class AuthService {
  protected httpOptions: {
    headers?: HttpHeaders;
    params?: HttpParams;
    responseType?: 'json' | 'blob';
  } = {};

  private http = inject(HttpClient);
  // O sinal armazena o estado de autenticação (privado para segurança)
  private _isAuthenticated = signal<boolean>(this.hasToken());

  // Exposição pública apenas para leitura
  isAuthenticated = computed(() => this._isAuthenticated());

  // Verifica se existe um token no localStorage ao iniciar
  private hasToken(): boolean {
    return !!localStorage.getItem('auth_token');
  }

  login(token: string) {
    localStorage.setItem('auth_token', token);
    this._isAuthenticated.set(true);
  }

  register(userData: UserRegister): void {
    // Lógica de registro pode ser adicionada aqui
    // Por enquanto, apenas simula o login após o registro ) }{
  }

  logout() {
    localStorage.removeItem('auth_token');
    this._isAuthenticated.set(false);
  }

  // Método usado pelo Guard que criamos antes
  isLoggedIn(): boolean {
    return this._isAuthenticated();
  }
}
