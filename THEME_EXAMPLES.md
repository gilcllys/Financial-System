# Exemplos Práticos - Sistema de Temas

## 🚀 Uso Básico

### 1. Alternância de Tema no Component

```typescript
import { Component, inject } from '@angular/core';
import { ThemeService } from '@app/services/theme.service';

@Component({
  selector: 'app-my-component',
  template: `
    <button (click)="toggleTheme()">
      <mat-icon>{{ getThemeIcon() }}</mat-icon>
      {{ getThemeLabel() }}
    </button>
  `
})
export class MyComponent {
  themeService = inject(ThemeService);

  toggleTheme() {
    this.themeService.toggleTheme();
  }

  getThemeIcon() {
    return this.themeService.isDarkTheme() ? 'light_mode' : 'dark_mode';
  }

  getThemeLabel() {
    return this.themeService.isDarkTheme() ? 'Tema Claro' : 'Tema Escuro';
  }
}
```

### 2. Definir Tema Programaticamente

```typescript
// Ao carregar a aplicação ou com base em preferência do usuário
ngOnInit() {
  const userPreference = this.getUserThemePreference();
  this.themeService.setTheme(userPreference);
}

// Forçar tema específico
setDarkMode() {
  this.themeService.setTheme('dark');
}

setLightMode() {
  this.themeService.setTheme('light');
}
```

### 3. Reagir a Mudanças de Tema

```typescript
import { effect } from '@angular/core';

constructor() {
  // Executar código quando o tema mudar
  effect(() => {
    const currentTheme = this.themeService.currentTheme();
    console.log('Tema alterado para:', currentTheme);
    
    // Executar lógica específica
    if (currentTheme === 'dark') {
      this.loadDarkModeAssets();
    } else {
      this.loadLightModeAssets();
    }
  });
}
```

## 🎨 Uso de CSS Variables

### 1. Componente CSS

```css
/* my-component.css */

.card {
  background-color: var(--bg-card);
  border: 1px solid var(--border-primary);
  color: var(--text-primary);
  box-shadow: var(--shadow-md);
}

.card-header {
  background-color: var(--bg-secondary);
  color: var(--text-primary);
  border-bottom: 1px solid var(--border-primary);
}

.card-title {
  color: var(--text-primary);
}

.card-description {
  color: var(--text-muted);
}

.action-button {
  background-color: var(--accent-primary);
  color: white;
}

.action-button:hover {
  background-color: var(--accent-hover);
}

.success-message {
  color: var(--color-success);
  background-color: var(--color-success-bg);
}

.error-message {
  color: var(--color-error);
  background-color: var(--color-error-bg);
}
```

### 2. Usando Helper Classes no HTML

```html
<!-- Card com classes helper -->
<div class="bg-card border-primary p-4 rounded-lg">
  <h2 class="text-primary font-bold">Título</h2>
  <p class="text-secondary">Conteúdo principal</p>
  <p class="text-muted text-sm">Informação adicional</p>
  
  <div class="bg-success text-success p-2 rounded">
    ✓ Operação realizada com sucesso
  </div>
</div>

<!-- Botões -->
<button class="bg-accent text-white px-4 py-2">
  Ação Principal
</button>

<button class="bg-secondary text-primary px-4 py-2">
  Ação Secundária
</button>
```

### 3. Classes Customizadas com Variáveis

```css
.custom-panel {
  background: var(--bg-elevated);
  border-left: 4px solid var(--accent-primary);
  padding: 1rem;
}

.custom-panel:hover {
  background: var(--bg-hover);
}

.status-badge {
  padding: 0.25rem 0.5rem;
  border-radius: 0.375rem;
  font-size: 0.75rem;
  font-weight: 600;
}

.status-badge.success {
  color: var(--color-success);
  background: var(--color-success-bg);
}

.status-badge.error {
  color: var(--color-error);
  background: var(--color-error-bg);
}

.status-badge.warning {
  color: var(--color-warning);
  background: var(--color-warning-bg);
}

.status-badge.info {
  color: var(--color-info);
  background: var(--color-info-bg);
}
```

## 📊 Exemplos de Componentes Comuns

### 1. Card de Estatística

```html
<div class="stats-card bg-card border-primary rounded-lg p-6 shadow-md">
  <div class="flex items-center justify-between">
    <div>
      <p class="text-muted text-sm uppercase">Receita Total</p>
      <h3 class="text-primary text-2xl font-bold">R$ 12.450,00</h3>
    </div>
    <div class="bg-accent-light text-accent p-3 rounded-full">
      <mat-icon>trending_up</mat-icon>
    </div>
  </div>
  <div class="mt-4">
    <span class="text-success text-sm">
      +12.5% desde o mês passado
    </span>
  </div>
</div>
```

```css
.stats-card {
  background-color: var(--bg-card);
  border: 1px solid var(--border-primary);
  transition: all 0.3s ease;
}

.stats-card:hover {
  box-shadow: var(--shadow-lg);
  transform: translateY(-2px);
}
```

### 2. Tabela Responsiva

```html
<div class="table-container bg-secondary rounded-lg">
  <table class="w-full">
    <thead class="bg-primary">
      <tr>
        <th class="text-muted text-left p-4">Descrição</th>
        <th class="text-muted text-right p-4">Valor</th>
        <th class="text-muted text-right p-4">Data</th>
      </tr>
    </thead>
    <tbody>
      <tr class="hover:bg-tertiary border-b border-primary">
        <td class="text-secondary p-4">Compra no supermercado</td>
        <td class="text-error text-right p-4">-R$ 250,00</td>
        <td class="text-muted text-right p-4">01/03/2026</td>
      </tr>
      <tr class="hover:bg-tertiary border-b border-primary">
        <td class="text-secondary p-4">Salário</td>
        <td class="text-success text-right p-4">+R$ 5.000,00</td>
        <td class="text-muted text-right p-4">01/03/2026</td>
      </tr>
    </tbody>
  </table>
</div>
```

```css
.table-container {
  background-color: var(--bg-secondary);
  overflow: hidden;
  box-shadow: var(--shadow-md);
}

thead {
  background-color: var(--bg-primary);
}

tbody tr:hover {
  background-color: var(--bg-tertiary);
}

tbody tr {
  border-bottom: 1px solid var(--border-primary);
}
```

### 3. Formulário

```html
<form class="bg-card border-primary rounded-lg p-6">
  <h2 class="text-primary text-xl font-bold mb-4">Nova Transação</h2>
  
  <div class="form-group mb-4">
    <label class="text-secondary text-sm font-medium mb-2 block">
      Descrição
    </label>
    <input 
      type="text"
      class="input-field"
      placeholder="Digite a descrição..."
    />
  </div>
  
  <div class="form-group mb-4">
    <label class="text-secondary text-sm font-medium mb-2 block">
      Valor
    </label>
    <input 
      type="number"
      class="input-field"
      placeholder="0,00"
    />
  </div>
  
  <div class="flex gap-3">
    <button type="submit" class="btn-primary">
      Salvar
    </button>
    <button type="button" class="btn-secondary">
      Cancelar
    </button>
  </div>
</form>
```

```css
.input-field {
  width: 100%;
  padding: 0.75rem;
  background-color: var(--bg-secondary);
  border: 1px solid var(--border-primary);
  border-radius: 0.5rem;
  color: var(--text-primary);
}

.input-field:focus {
  outline: none;
  border-color: var(--accent-primary);
  box-shadow: 0 0 0 3px var(--accent-light);
}

.input-field::placeholder {
  color: var(--text-disabled);
}

.btn-primary {
  padding: 0.75rem 1.5rem;
  background-color: var(--accent-primary);
  color: white;
  border-radius: 0.5rem;
  font-weight: 600;
}

.btn-primary:hover {
  background-color: var(--accent-hover);
}

.btn-secondary {
  padding: 0.75rem 1.5rem;
  background-color: var(--bg-tertiary);
  color: var(--text-primary);
  border-radius: 0.5rem;
}

.btn-secondary:hover {
  background-color: var(--bg-hover);
}
```

### 4. Modal/Dialog

```html
<div class="modal-overlay">
  <div class="modal-content bg-elevated rounded-lg p-6">
    <div class="modal-header flex items-center justify-between mb-4">
      <h2 class="text-primary text-xl font-bold">Confirmar Exclusão</h2>
      <button class="text-muted hover:text-primary">
        <mat-icon>close</mat-icon>
      </button>
    </div>
    
    <div class="modal-body">
      <p class="text-secondary">
        Tem certeza que deseja excluir esta transação?
        Esta ação não pode ser desfeita.
      </p>
    </div>
    
    <div class="modal-footer flex gap-3 mt-6 justify-end">
      <button class="btn-cancel">Cancelar</button>
      <button class="btn-danger">Excluir</button>
    </div>
  </div>
</div>
```

```css
.modal-overlay {
  position: fixed;
  inset: 0;
  background: var(--overlay-bg);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal-content {
  background-color: var(--bg-elevated);
  box-shadow: var(--shadow-xl);
  max-width: 500px;
  width: 90%;
}

.modal-header {
  border-bottom: 1px solid var(--border-primary);
  padding-bottom: 1rem;
}

.btn-cancel {
  padding: 0.5rem 1rem;
  background-color: var(--bg-tertiary);
  color: var(--text-primary);
  border-radius: 0.375rem;
}

.btn-danger {
  padding: 0.5rem 1rem;
  background-color: var(--color-error);
  color: white;
  border-radius: 0.375rem;
}

.btn-danger:hover {
  background-color: #dc2626; /* red-600 */
}
```

## 🎭 Casos de Uso Avançados

### 1. Tema Baseado em Rota

```typescript
// app.component.ts
export class AppComponent implements OnInit {
  themeService = inject(ThemeService);
  router = inject(Router);

  ngOnInit() {
    this.router.events
      .pipe(filter(event => event instanceof NavigationEnd))
      .subscribe((event: NavigationEnd) => {
        // Mudar tema baseado na rota
        if (event.url.includes('/admin')) {
          this.themeService.setTheme('light');
        } else {
          this.themeService.setTheme('dark');
        }
      });
  }
}
```

### 2. Sincronizar com Preferência do Sistema

```typescript
// Detectar mudanças na preferência do sistema
ngOnInit() {
  if (isPlatformBrowser(this.platformId)) {
    const darkModeQuery = window.matchMedia('(prefers-color-scheme: dark)');
    
    darkModeQuery.addEventListener('change', (e) => {
      const newTheme = e.matches ? 'dark' : 'light';
      this.themeService.setTheme(newTheme);
    });
  }
}
```

### 3. Preview de Tema

```typescript
// Visualizar tema temporariamente sem salvar
previewTheme(theme: Theme) {
  // Salvar tema atual
  const currentTheme = this.themeService.currentTheme();
  
  // Aplicar preview
  this.themeService.setTheme(theme);
  
  // Resetar após 3 segundos
  setTimeout(() => {
    this.themeService.setTheme(currentTheme);
  }, 3000);
}
```

## ✨ Dicas Finais

1. **Sempre use variáveis CSS** ao invés de cores hardcoded
2. **Teste em ambos os temas** antes de fazer commit
3. **Mantenha contraste adequado** (mínimo 4.5:1 para texto)
4. **Use cores semânticas** (success, error, warning, info)
5. **Evite `!important`** sempre que possível
6. **Aproveite as helper classes** para desenvolvimento rápido

---

**Documentação completa em:** [THEME_SYSTEM.md](./THEME_SYSTEM.md)
