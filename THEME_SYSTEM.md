# Sistema de Temas Dark/Light - Financial System

Este documento explica como o sistema de temas foi implementado e como usá-lo no projeto.

## 📋 Visão Geral

O sistema de temas permite alternar entre modo **Dark** (padrão) e **Light** de forma dinâmica, com todas as cores definidas através de **CSS Variables** para fácil manutenção.

## 🎨 Cores do Tema

### Dark Theme (Padrão)
- **Backgrounds:** `#0f172a`, `#1e293b`, `#334155`
- **Textos:** `#f1f5f9`, `#e2e8f0`, `#94a3b8`, `#64748b`
- **Bordas:** `#334155`, `#475569`
- **Accent:** `#0ea5e9` (Sky Blue)
- **Status:** Verde (`#10b981`), Vermelho (`#ef4444`), Amarelo (`#f59e0b`), Azul (`#3b82f6`)

### Light Theme
- **Backgrounds:** `#ffffff`, `#f8fafc`, `#f1f5f9`
- **Textos:** `#0f172a`, `#1e293b`, `#475569`, `#94a3b8`
- **Bordas:** `#e2e8f0`, `#cbd5e1`
- **Accent:** `#0ea5e9` (mantém mesmo do dark)
- **Status:** Mesmas cores do dark theme

## 🔧 Arquitetura

### 1. Theme Service (`theme.service.ts`)
Serviço responsável por gerenciar o estado do tema:

```typescript
import { ThemeService } from '@app/services/theme.service';

// Injetar o serviço
themeService = inject(ThemeService);

// Alternar tema
themeService.toggleTheme();

// Definir tema específico
themeService.setTheme('dark');
themeService.setTheme('light');

// Verificar tema atual
const isDark = themeService.isDarkTheme();
const isLight = themeService.isLightTheme();

// Acessar tema como signal
const theme = themeService.currentTheme(); // 'dark' | 'light'
```

**Funcionalidades:**
- ✅ Salva preferência no `localStorage`
- ✅ Detecta preferência do sistema operacional
- ✅ Usa Angular Signals para reatividade
- ✅ SSR-safe (verifica `isPlatformBrowser`)

### 2. CSS Variables (`styles.scss`)
Todas as cores são definidas como CSS variables:

**Disponíveis:**
```css
/* Backgrounds */
--bg-primary
--bg-secondary
--bg-tertiary
--bg-elevated
--bg-card
--bg-hover
--bg-body

/* Texts */
--text-primary
--text-secondary
--text-muted
--text-disabled

/* Borders */
--border-primary
--border-secondary
--border-tertiary
--border-light

/* Accent */
--accent-primary
--accent-hover
--accent-light
--accent-strong

/* Status */
--color-success / --color-success-bg
--color-error / --color-error-bg
--color-warning / --color-warning-bg
--color-info / --color-info-bg

/* Shadows */
--shadow-sm / --shadow-md / --shadow-lg / --shadow-xl

/* Scrollbar */
--scrollbar-track
--scrollbar-thumb
--scrollbar-thumb-hover

/* Overlay */
--overlay-bg
```

### 3. Helper Classes (`theme-helpers.css`)
Classes utilitárias para aplicar rapidamente:

```html
<!-- Backgrounds -->
<div class="bg-primary">...</div>
<div class="bg-secondary">...</div>
<div class="bg-card">...</div>

<!-- Textos -->
<p class="text-primary">Texto principal</p>
<p class="text-muted">Texto esmaecido</p>

<!-- Bordas -->
<div class="border-primary">...</div>

<!-- Status -->
<span class="text-success">Sucesso</span>
<span class="text-error">Erro</span>
<div class="bg-warning">Aviso</div>
```

## 💡 Como Usar

### 1. Usar CSS Variables diretamente
```css
.meu-componente {
  background-color: var(--bg-primary);
  color: var(--text-primary);
  border: 1px solid var(--border-primary);
}

.meu-botao:hover {
  background-color: var(--accent-hover);
}
```

### 2. Usar Helper Classes
```html
<div class="bg-card text-primary border-primary">
  <h1 class="text-primary">Título</h1>
  <p class="text-muted">Descrição</p>
</div>
```

### 3. Adicionar Botão de Alternância
Já implementado no `layout.component.html`:

```html
<button (click)="toggleTheme()">
  <mat-icon>{{ getThemeIcon() }}</mat-icon>
</button>
```

## 🎯 Boas Práticas

### ✅ FAZER
- Usar CSS variables para todas as cores
- Usar helpers classes quando possível
- Testar em ambos os temas
- Usar cores semânticas (`--text-muted` ao invés de `--text-disabled`)

### ❌ NÃO FAZER
- Hardcodar cores hex (`#1e293b`)
- Usar `!important` desnecessariamente
- Ignorar acessibilidade (contraste)
- Misturar classe Tailwind coloridas com variáveis CSS

## 📱 Componentes Atualizados

Os seguintes componentes já estão usando o sistema de temas:

- ✅ `layout.component` - Sidebar, footer, navegação
- ✅ `dashboard.component` - Dashboard
- ✅ `transactions.component` - Tabela, filtros, date picker
- ✅ `reports.component` - Relatórios

## 🛠️ Personalização

### Adicionar Nova Cor
1. Adicione a variável em ambos os temas no `styles.scss`:
```scss
:root.dark-theme {
  --minha-cor: #valor-dark;
}

:root.light-theme {
  --minha-cor: #valor-light;
}
```

2. (Opcional) Adicione helper class em `theme-helpers.css`:
```css
.minha-classe {
  color: var(--minha-cor);
}
```

### Modificar Cores Existentes
Basta editar os valores no `styles.scss` nas seções `:root.dark-theme` e `:root.light-theme`.

## 🔍 Debugging

### Verificar Tema Atual
```typescript
// No componente
console.log('Tema atual:', this.themeService.currentTheme());

// No navegador (DevTools Console)
console.log(document.documentElement.className); // "dark-theme" ou "light-theme"
console.log(document.documentElement.getAttribute('data-theme')); // "dark" ou "light"
```

### Inspecionar CSS Variables
No DevTools, vá para Elements → :root → Computed → Filter: `--`

## 📦 Arquivos Modificados

- `src/app/services/theme.service.ts` - Novo serviço
- `src/styles.scss` - Variables e estilos base
- `src/app/styles/theme-helpers.css` - Classes helper
- `src/app/layouts/layout.component.*` - Botão de alternância
- `src/app/screens/*/` - Componentes atualizados

## 🚀 Melhorias Futuras

- [ ] Theme switcher com preview
- [ ] Temas personalizados (além de dark/light)
- [ ] Sincronização com preferência do sistema em tempo real
- [ ] Animações de transição mais suaves
- [ ] Tema automático baseado em horário

---

**Desenvolvido por:** Gilcllys Costa  
**Data:** Março 2026
