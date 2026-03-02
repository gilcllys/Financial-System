# Guia Visual: Temas Dark & Light

## 🎨 Paleta de Cores Comparativa

### Backgrounds
| Variável | Dark Theme | Light Theme | Uso |
|----------|------------|-------------|-----|
| `--bg-body` | `#000000` (Black) | `#f8fafc` (Slate-50) | Background principal da aplicação |
| `--bg-primary` | `#0f172a` (Slate-900) | `#ffffff` (White) | Cards, headers, containers principais |
| `--bg-secondary` | `#1e293b` (Slate-800) | `#f8fafc` (Slate-50) | Sidebar, tabelas, áreas secundárias |
| `--bg-tertiary` | `#334155` (Slate-700) | `#f1f5f9` (Slate-100) | Hovers, elementos interativos |
| `--bg-card` | `#1e293b` (Slate-800) | `#ffffff` (White) | Cards, panels |
| `--bg-hover` | `#334155` (Slate-700) | `#f1f5f9` (Slate-100) | Estados hover |

### Textos
| Variável | Dark Theme | Light Theme | Uso |
|----------|------------|-------------|-----|
| `--text-primary` | `#f1f5f9` (Slate-100) | `#0f172a` (Slate-900) | Títulos, texto principal |
| `--text-secondary` | `#e2e8f0` (Slate-200) | `#1e293b` (Slate-800) | Texto padrão, labels |
| `--text-muted` | `#94a3b8` (Slate-400) | `#475569` (Slate-600) | Texto secundário, hints |
| `--text-disabled` | `#64748b` (Slate-500) | `#94a3b8` (Slate-400) | Texto desabilitado, placeholders |

### Bordas
| Variável | Dark Theme | Light Theme | Uso |
|----------|------------|-------------|-----|
| `--border-primary` | `#334155` (Slate-700) | `#e2e8f0` (Slate-200) | Bordas principais |
| `--border-secondary` | `#475569` (Slate-600) | `#cbd5e1` (Slate-300) | Bordas em hover |
| `--border-tertiary` | `#334155` (Slate-700) | `#cbd5e1` (Slate-300) | Bordas sutis |

### Cores de Destaque (Accent)
| Variável | Ambos os Temas | Uso |
|----------|----------------|-----|
| `--accent-primary` | `#0ea5e9` (Sky-500) | Botões principais, links, elementos ativos |
| `--accent-hover` | `#0284c7` (Sky-600) | Hover em botões accent |
| `--accent-light` | `rgba(14, 165, 233, 0.1)` | Background sutil para elementos accent |
| `--accent-strong` | Dark: `0.2` / Light: `0.15` | Background mais forte para ranges |

### Cores de Status (Ambos os Temas)
| Cor | Valor | Background | Uso |
|-----|-------|-----------|-----|
| Success | `#10b981` (Green-500) | `rgba(16, 185, 129, 0.1)` | Valores positivos, sucesso |
| Error | `#ef4444` (Red-500) | `rgba(239, 68, 68, 0.1)` | Valores negativos, erros |
| Warning | `#f59e0b` (Amber-500) | `rgba(245, 158, 11, 0.1)` | Avisos |
| Info | `#3b82f6` (Blue-500) | `rgba(59, 130, 246, 0.1)` | Informações, edição |

### Sombras
| Variável | Dark Theme | Light Theme |
|----------|------------|-------------|
| `--shadow-sm` | `0 1px 2px rgba(0,0,0,0.5)` | `0 1px 2px rgba(0,0,0,0.05)` |
| `--shadow-md` | `0 4px 6px rgba(0,0,0,0.5)` | `0 4px 6px rgba(0,0,0,0.07)` |
| `--shadow-lg` | `0 10px 15px rgba(0,0,0,0.5)` | `0 10px 15px rgba(0,0,0,0.1)` |
| `--shadow-xl` | `0 20px 25px rgba(0,0,0,0.5)` | `0 20px 25px rgba(0,0,0,0.15)` |

## 📱 Componentes por Tema

### Sidebar / Navegação

**Dark Theme:**
```
Background: #1e293b (Slate-800)
Border: #334155 (Slate-700)
Menu Item Normal: #94a3b8 (Slate-400)
Menu Item Active: #10b981 (Emerald-500)
```

**Light Theme:**
```
Background: #f8fafc (Slate-50)
Border: #e2e8f0 (Slate-200)
Menu Item Normal: #475569 (Slate-600)
Menu Item Active: #10b981 (Emerald-500)
```

### Tabela de Transações

**Dark Theme:**
```
Container: #1e293b (Slate-800)
Header: #0f172a (Slate-900)
Row Hover: #334155 (Slate-700)
Border: #334155 (Slate-700)
Texto: #e2e8f0 (Slate-200)
```

**Light Theme:**
```
Container: #ffffff (White)
Header: #f8fafc (Slate-50)
Row Hover: #f1f5f9 (Slate-100)
Border: #e2e8f0 (Slate-200)
Texto: #1e293b (Slate-800)
```

### Botões

**Botão Principal (Accent):**
- Background: `#0ea5e9` (Sky-500) - AMBOS
- Hover: `#0284c7` (Sky-600) - AMBOS
- Texto: `#ffffff` (White) - AMBOS

**Botão Editar:**
- Cor: `#3b82f6` (Blue-500) - AMBOS
- Hover BG: `rgba(59, 130, 246, 0.1)` - AMBOS

**Botão Deletar:**
- Cor: `#ef4444` (Red-500) - AMBOS
- Hover BG: `rgba(239, 68, 68, 0.1)` - AMBOS

### Date Picker / Calendário

**Dark Theme:**
```
Container: #1e293b (Slate-800)
Header: #0f172a (Slate-900)
Texto dias: #e2e8f0 (Slate-200)
Hoje (border): #0ea5e9 (Sky-500)
Selecionado: #0ea5e9 (Sky-500)
Range: rgba(14, 165, 233, 0.2)
```

**Light Theme:**
```
Container: #ffffff (White)
Header: #f8fafc (Slate-50)
Texto dias: #1e293b (Slate-800)
Hoje (border): #0ea5e9 (Sky-500)
Selecionado: #0ea5e9 (Sky-500)
Range: rgba(14, 165, 233, 0.15)
```

## 🎯 Contraste e Acessibilidade

### Ratios de Contraste (WCAG AA: min 4.5:1)

**Dark Theme:**
- Texto Principal (`#f1f5f9`) sobre Background (`#0f172a`): **14.7:1** ✅
- Texto Muted (`#94a3b8`) sobre Background (`#1e293b`): **6.2:1** ✅
- Accent (`#0ea5e9`) sobre Background (`#1e293b`): **4.8:1** ✅

**Light Theme:**
- Texto Principal (`#0f172a`) sobre Background (`#ffffff`): **15.8:1** ✅
- Texto Muted (`#475569`) sobre Background (`#f8fafc`): **7.1:1** ✅
- Accent (`#0ea5e9`) sobre Background (`#ffffff`): **3.1:1** ⚠️ (OK para elementos não-texto)

## 🔄 Transições

Todas as transições de cor acontecem suavemente:
```css
transition: background-color 0.3s ease, color 0.3s ease;
```

## 💡 Dicas de Design

### Quando usar cada cor:

1. **text-primary**: Títulos, texto importante
2. **text-secondary**: Corpo de texto, conteúdo principal
3. **text-muted**: Labels, descrições, metadados
4. **text-disabled**: Elementos inativos, placeholders

5. **bg-primary**: Cards principais, modals
6. **bg-secondary**: Sidebars, tabelas, seções
7. **bg-tertiary**: Elementos interativos em hover

8. **accent-primary**: Call-to-action, elementos clicáveis
9. **border-primary**: Separadores principais
10. **shadow-md**: Elevação padrão de cards

## 🖼️ Preview das Cores

### Dark Theme Palette
```
████ #000000 (bg-body)       ████ #f1f5f9 (text-primary)
████ #0f172a (bg-primary)    ████ #e2e8f0 (text-secondary)
████ #1e293b (bg-secondary)  ████ #94a3b8 (text-muted)
████ #334155 (bg-tertiary)   ████ #64748b (text-disabled)
████ #0ea5e9 (accent)        ████ #10b981 (success)
```

### Light Theme Palette
```
████ #f8fafc (bg-body)       ████ #0f172a (text-primary)
████ #ffffff (bg-primary)    ████ #1e293b (text-secondary)
████ #f8fafc (bg-secondary)  ████ #475569 (text-muted)
████ #f1f5f9 (bg-tertiary)   ████ #94a3b8 (text-disabled)
████ #0ea5e9 (accent)        ████ #10b981 (success)
```

---

**Nota:** As cores accent e de status são mantidas consistentes entre temas para reconhecimento visual e branding.
