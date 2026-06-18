// ─── TypeScript Models ────────────────────────────────────────────────────────

export interface ExpenseCategory {
  id: number;
  tenant_id: string;
  name: string;
  description: string;
}

export type PaymentMethod = 'dinheiro' | 'cartao';

export interface Expense {
  id: number;
  tenant_id: string;
  category_id: number;
  category?: ExpenseCategory;
  payment_method: PaymentMethod;
  credit_card_id: number | null;
  description: string;
  quantity: number;
  amount: number;
  date: string;           // ISO date string YYYY-MM-DD
  created_at: string;
  updated_at: string;
}

export interface CreateExpensePayload {
  category_id: number;
  description: string;
  amount: number;
  date: string;
  quantity: number;
  payment_method: PaymentMethod;
  credit_card_id: number | null;
  is_installment: boolean;
  installments: number;
  need_pay_vitoria: boolean;
}

export interface CreditCard {
  id: number;
  name: string;
  due_date: number;          // day 1-31
  best_purchase_date: number; // day 1-31
  last_four_digits: string;
}

export interface CreateCreditCardPayload {
  name: string;
  due_date: number;
  best_purchase_date: number;
  last_four_digits: string;
}

export interface MonthlyReport {
  month: number;
  year: number;
  totalIncome: number;
  totalExpenses: number;
  balance: number;
  byCategory: CategoryBreakdown[];
}

export interface CategoryBreakdown {
  category: ExpenseCategory;
  total: number;
  count: number;
}

export interface ExpenseFilters {
  month?: number;
  year?: number;
  category_id?: number;
  payment_method?: PaymentMethod;
  credit_card_id?: number;
}

export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

// ─── Supermarket Models ────────────────────────────────────────────────────────

export interface SupermarketExpenseItem {
  id: number;
  tenant_id: string;
  supermarket_expense: number;
  description: string;
  quantity: number;
  unit_price: number; // normalizado para number (parseFloat)
}

export interface SupermarketExpense {
  id: number;
  tenant_id: string;
  store_name: string;
  date: string; // ISO date YYYY-MM-DD
  address?: string;
  total: number;
  items: SupermarketExpenseItem[];
}

export interface CreateSupermarketExpensePayload {
  store_name: string;
  date: string;
  address?: string;
}

export interface CreateSupermarketItemPayload {
  supermarket_expense: number;
  description: string;
  quantity: number;
  unit_price: number;
}
