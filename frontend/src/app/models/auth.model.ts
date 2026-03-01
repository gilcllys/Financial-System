import { User } from './user.model';

/**
 * Modelo de Registro de Usuário
 * Baseado em RegisterCustomSerializer
 */
export class UserRegister {
  email: string;
  username: string;
  password: string;

  constructor(data: Partial<UserRegister> = {}) {
    this.email = data.email || '';
    this.username = data.username || '';
    this.password = data.password || '';
  }

  /**
   * Valida se os dados estão completos
   */
  isValid(): boolean {
    return !!(this.email && this.username && this.password);
  }

  /**
   * Converte para JSON para envio à API
   */
  toJson(): any {
    return {
      email: this.email,
      username: this.username,
      password: this.password,
    };
  }

  /**
   * Cria uma instância a partir de dados do formulário
   */
  static fromFormData(
    name: string,
    email: string,
    password: string,
  ): UserRegister {
    return new UserRegister({
      username: name,
      email,
      password,
    });
  }
}

/**
 * Modelo de Login
 * Baseado em LoginCustomSerializer
 */
export class UserLogin {
  username: string;
  password: string;

  constructor(data: Partial<UserLogin> = {}) {
    this.username = data.username || '';
    this.password = data.password || '';
  }

  /**
   * Valida se os dados estão completos
   */
  isValid(): boolean {
    return !!(this.username && this.password);
  }

  /**
   * Converte para JSON para envio à API
   */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  toJson(): any {
    return {
      username: this.username,
      password: this.password,
    };
  }

  /**
   * Cria uma instância para login com email
   * (o backend aceita username, mas podemos usar email)
   */
  static fromEmail(email: string, password: string): UserLogin {
    return new UserLogin({
      username: email,
      password,
    });
  }
}

/**
 * Modelo de Resposta de Login
 */
export class LoginResponse {
  access: string;
  refresh: string;
  user?: User;

  constructor(data: Partial<LoginResponse> = {}) {
    this.access = data.access || '';
    this.refresh = data.refresh || '';
    this.user = data.user;
  }

  /**
   * Cria uma instância a partir de JSON da API
   */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  static fromJson(json: any): LoginResponse {
    return new LoginResponse({
      access: json.access,
      refresh: json.refresh,
      user: json.user ? User.fromJson(json.user) : undefined,
    });
  }

  /**
   * Verifica se a resposta é válida
   */
  isValid(): boolean {
    return !!(this.access && this.refresh);
  }
}

/**
 * Modelo de Logout
 * Baseado em LogoutCustomSerializer
 */
export class UserLogout {
  userId: number;
  refresh: string;

  constructor(data: Partial<UserLogout> = {}) {
    this.userId = data.userId || 0;
    this.refresh = data.refresh || '';
  }

  /**
   * Converte para JSON para envio à API
   */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  toJson(): any {
    return {
      user_id: this.userId,
      refresh: this.refresh,
    };
  }
}

/**
 * Modelo de Resposta de Registro
 */
export class RegisterResponse {
  id: number;
  email: string;
  username: string;

  constructor(data: Partial<RegisterResponse> = {}) {
    this.id = data.id || 0;
    this.email = data.email || '';
    this.username = data.username || '';
  }

  /**
   * Cria uma instância a partir de JSON da API
   */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  static fromJson(json: any): RegisterResponse {
    return new RegisterResponse({
      id: json.id,
      email: json.email,
      username: json.username,
    });
  }

  /**
   * Converte para User básico
   */
  toUser(): User {
    return new User({
      id: this.id,
      email: this.email,
      username: this.username,
    });
  }
}
