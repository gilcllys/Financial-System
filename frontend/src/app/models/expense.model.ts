/**
 * Modelo Base com campos comuns
 */
export abstract class BaseModel {
  id: number;
  createdAt?: Date;
  updatedAt?: Date;

  constructor(data: Partial<BaseModel> = {}) {
    this.id = data.id || 0;
    this.createdAt = data.createdAt ? new Date(data.createdAt) : undefined;
    this.updatedAt = data.updatedAt ? new Date(data.updatedAt) : undefined;
  }
}

/**
 * Categoria de Despesa
 * Baseado em ExpenseCategory model
 */
export class ExpenseCategory extends BaseModel {
  name: string;
  description?: string;

  constructor(data: Partial<ExpenseCategory> = {}) {
    super(data);
    this.name = data.name || '';
    this.description = data.description;
  }

  /**
   * Cria uma instância a partir de JSON da API
   */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  static fromJson(json: any): ExpenseCategory {
    return new ExpenseCategory({
      id: json.id,
      name: json.name,
      description: json.description,
      createdAt: json.created_at,
      updatedAt: json.updated_at,
    });
  }

  /**
   * Converte para JSON para envio à API
   */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  toJson(): any {
    return {
      id: this.id || undefined,
      name: this.name,
      description: this.description,
    };
  }
}

/**
 * Despesa
 * Baseado em Expense model
 */
export class Expense extends BaseModel {
  userId: number;
  categoryId: number;
  description: string;
  quantity: number;
  amount: number;
  date: Date;

  // Relações (opcional, carregadas quando necessário)
  category?: ExpenseCategory;

  constructor(data: Partial<Expense> = {}) {
    super(data);
    this.userId = data.userId || 0;
    this.categoryId = data.categoryId || 0;
    this.description = data.description || '';
    this.quantity = data.quantity || 1;
    this.amount = data.amount || 0;
    this.date = data.date ? new Date(data.date) : new Date();
    this.category = data.category;
  }

  /**
   * Cria uma instância a partir de JSON da API
   */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  static fromJson(json: any): Expense {
    return new Expense({
      id: json.id,
      userId: json.user_id,
      categoryId: json.category_id,
      description: json.description,
      quantity: json.quantity,
      amount: parseFloat(json.amount),
      date: json.date,
      createdAt: json.created_at,
      updatedAt: json.updated_at,
      category: json.category
        ? ExpenseCategory.fromJson(json.category)
        : undefined,
    });
  }

  /**
   * Converte para JSON para envio à API
   */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  toJson(): any {
    return {
      id: this.id || undefined,
      user_id: this.userId,
      category_id: this.categoryId,
      description: this.description,
      quantity: this.quantity,
      amount: this.amount,
      date: this.date.toISOString().split('T')[0], // Formato YYYY-MM-DD
    };
  }

  /**
   * Calcula o total da despesa
   */
  getTotal(): number {
    return this.quantity * this.amount;
  }

  /**
   * Formata o valor para exibição
   */
  getFormattedAmount(): string {
    return new Intl.NumberFormat('pt-BR', {
      style: 'currency',
      currency: 'BRL',
    }).format(this.amount);
  }

  /**
   * Formata o total para exibição
   */
  getFormattedTotal(): string {
    return new Intl.NumberFormat('pt-BR', {
      style: 'currency',
      currency: 'BRL',
    }).format(this.getTotal());
  }
}

/**
 * Despesa de Supermercado
 * Baseado em SupermachExpense model
 */
export class SupermarketExpense extends BaseModel {
  storeName: string;
  date: Date;
  address?: string;

  // Relação com itens
  items?: SupermarketExpenseItem[];

  constructor(data: Partial<SupermarketExpense> = {}) {
    super(data);
    this.storeName = data.storeName || '';
    this.date = data.date ? new Date(data.date) : new Date();
    this.address = data.address;
    this.items = data.items;
  }

  /**
   * Cria uma instância a partir de JSON da API
   */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  static fromJson(json: any): SupermarketExpense {
    return new SupermarketExpense({
      id: json.id,
      storeName: json.store_name,
      date: json.date,
      address: json.adress || json.address, // Backend tem typo
      createdAt: json.created_at,
      updatedAt: json.updated_at,
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      items: json.items?.map((item: any) =>
        SupermarketExpenseItem.fromJson(item),
      ),
    });
  }

  /**
   * Converte para JSON para envio à API
   */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  toJson(): any {
    return {
      id: this.id || undefined,
      store_name: this.storeName,
      date: this.date.toISOString().split('T')[0],
      adress: this.address, // Backend usa "adress"
    };
  }

  /**
   * Calcula o total de todos os itens
   */
  getTotal(): number {
    if (!this.items || this.items.length === 0) {
      return 0;
    }
    return this.items.reduce((total, item) => total + item.getTotal(), 0);
  }

  /**
   * Retorna o total formatado
   */
  getFormattedTotal(): string {
    return new Intl.NumberFormat('pt-BR', {
      style: 'currency',
      currency: 'BRL',
    }).format(this.getTotal());
  }
}

/**
 * Item de Despesa de Supermercado
 * Baseado em SupermachExpenseItem model
 */
export class SupermarketExpenseItem extends BaseModel {
  supermarketExpenseId: number;
  description: string;
  quantity: number;
  amount: number;

  constructor(data: Partial<SupermarketExpenseItem> = {}) {
    super(data);
    this.supermarketExpenseId = data.supermarketExpenseId || 0;
    this.description = data.description || '';
    this.quantity = data.quantity || 1;
    this.amount = data.amount || 0;
  }

  /**
   * Cria uma instância a partir de JSON da API
   */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  static fromJson(json: any): SupermarketExpenseItem {
    return new SupermarketExpenseItem({
      id: json.id,
      supermarketExpenseId: json.supermach_expense_id,
      description: json.description,
      quantity: json.quantity,
      amount: parseFloat(json.amount),
      createdAt: json.created_at,
      updatedAt: json.updated_at,
    });
  }

  /**
   * Converte para JSON para envio à API
   */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  toJson(): any {
    return {
      id: this.id || undefined,
      supermach_expense_id: this.supermarketExpenseId,
      description: this.description,
      quantity: this.quantity,
      amount: this.amount,
    };
  }

  /**
   * Calcula o total do item
   */
  getTotal(): number {
    return this.quantity * this.amount;
  }

  /**
   * Formata o valor unitário
   */
  getFormattedAmount(): string {
    return new Intl.NumberFormat('pt-BR', {
      style: 'currency',
      currency: 'BRL',
    }).format(this.amount);
  }

  /**
   * Formata o total
   */
  getFormattedTotal(): string {
    return new Intl.NumberFormat('pt-BR', {
      style: 'currency',
      currency: 'BRL',
    }).format(this.getTotal());
  }
}
