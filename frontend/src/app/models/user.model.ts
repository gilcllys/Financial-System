/**
 * Modelo de Usuário baseado no Django User Model
 */
export class User {
  id: number;
  username: string;
  email: string;
  firstName?: string;
  lastName?: string;
  isActive?: boolean;
  isStaff?: boolean;
  dateJoined?: Date;

  constructor(data: Partial<User> = {}) {
    this.id = data.id || 0;
    this.username = data.username || '';
    this.email = data.email || '';
    this.firstName = data.firstName;
    this.lastName = data.lastName;
    this.isActive = data.isActive ?? true;
    this.isStaff = data.isStaff ?? false;
    this.dateJoined = data.dateJoined ? new Date(data.dateJoined) : undefined;
  }

  /**
   * Retorna o nome completo do usuário
   */
  getFullName(): string {
    if (this.firstName && this.lastName) {
      return `${this.firstName} ${this.lastName}`;
    }
    return this.username;
  }

  /**
   * Cria uma instância de User a partir de um objeto JSON
   */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  static fromJson(json: any): User {
    return new User({
      id: json.id,
      username: json.username,
      email: json.email,
      firstName: json.first_name,
      lastName: json.last_name,
      isActive: json.is_active,
      isStaff: json.is_staff,
      dateJoined: json.date_joined,
    });
  }

  /**
   * Converte o modelo para JSON
   */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  toJson(): any {
    return {
      id: this.id,
      username: this.username,
      email: this.email,
      first_name: this.firstName,
      last_name: this.lastName,
      is_active: this.isActive,
      is_staff: this.isStaff,
      date_joined: this.dateJoined?.toISOString(),
    };
  }
}
