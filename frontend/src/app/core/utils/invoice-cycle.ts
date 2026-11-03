export interface InvoiceMonthRef {
  year: number;
  month: number;
  displayDate: string;
  sort: number;
}

function nextMonth(year: number, month: number): { year: number; month: number } {
  return month === 12 ? { year: year + 1, month: 1 } : { year, month: month + 1 };
}

function daysInMonth(year: number, month: number): number {
  return new Date(year, month, 0).getDate();
}

export function effectiveClosingDate(year: number, month: number, closingDay: number): Date {
  const closing = new Date(year, month - 1, Math.min(closingDay, daysInMonth(year, month)));
  if (closing.getDay() === 6) return new Date(year, month - 1, closing.getDate() - 1);
  if (closing.getDay() === 0) return new Date(year, month - 1, closing.getDate() - 2);
  return closing;
}

export function invoiceFromClosing(year: number, month: number): InvoiceMonthRef {
  const invoice = nextMonth(year, month);
  return {
    year: invoice.year,
    month: invoice.month,
    displayDate: `${invoice.year}-${String(invoice.month).padStart(2, '0')}-01`,
    sort: invoice.year * 12 + invoice.month,
  };
}

export function invoiceForDate(dateStr: string, closingDay: number): InvoiceMonthRef {
  const [year, month, day] = dateStr.split('-').map(Number);
  const date = new Date(year, month - 1, day);
  let closingYear = year;
  let closingMonth = month;
  if (date > effectiveClosingDate(year, month, closingDay)) {
    const next = nextMonth(year, month);
    closingYear = next.year;
    closingMonth = next.month;
  }
  return invoiceFromClosing(closingYear, closingMonth);
}

export function currentInvoice(closingDay: number, today = new Date()): InvoiceMonthRef {
  const date = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  const year = date.getFullYear();
  const month = date.getMonth() + 1;
  if (date <= effectiveClosingDate(year, month, closingDay)) return invoiceFromClosing(year, month);
  const next = nextMonth(year, month);
  return invoiceFromClosing(next.year, next.month);
}

export function isInvoiceClosed(dateStr: string, closingDay: number, today = new Date()): boolean {
  return invoiceForDate(dateStr, closingDay).sort < currentInvoice(closingDay, today).sort;
}
