// @ts-check

const eslint = require('@eslint/js');
const tseslint = require('typescript-eslint');
const angular = require('angular-eslint');
const prettierConfig = require('eslint-plugin-prettier/recommended');

module.exports = tseslint.config(
  {
    ignores: [
      '**/node_modules/**',
      '**/dist/**',
      '**/tmp/**',
      '**/*.spec.ts',
      '**/*.d.ts',
      'src/environments/*',
      '.git/',
    ],
  },
  {
    files: ['**/*.ts'],
    extends: [
      eslint.configs.recommended,
      ...tseslint.configs.recommended,
      ...tseslint.configs.stylistic,
      ...angular.configs.tsRecommended,
      prettierConfig,
    ],
    processor: angular.processInlineTemplates,
    languageOptions: {
      parserOptions: {
        project: ['./tsconfig.json', './e2e/tsconfig.json'],
        tsconfigRootDir: __dirname,
        createDefaultProgram: true,
      },
    },
    rules: {
      'no-unused-vars': 'off',
      '@typescript-eslint/no-unused-vars': [
        'warn',
        { argsIgnorePattern: '^_' },
      ],
      'no-debugger': 'error',
      eqeqeq: ['error', 'always'],
      'no-var': 'error',
      'prefer-const': 'warn',
      curly: 'error',
      '@typescript-eslint/explicit-member-accessibility': [
        'error',
        { accessibility: 'no-public' },
      ],
      '@typescript-eslint/consistent-type-imports': 'error',

      '@angular-eslint/directive-selector': [
        'error',
        {
          type: 'attribute',
          prefix: 'app',
          style: 'camelCase',
        },
      ],
      '@angular-eslint/component-selector': [
        'error',
        {
          type: 'element',
          prefix: 'app',
          style: 'kebab-case',
        },
      ],
      '@angular-eslint/no-empty-lifecycle-method': 'warn',
      '@angular-eslint/prefer-output-readonly': 'warn',
      '@angular-eslint/no-input-rename': 'error',
      '@angular-eslint/no-output-rename': 'error',
      '@angular-eslint/use-pipe-transform-interface': 'error',
      '@angular-eslint/contextual-lifecycle': 'error',
      '@angular-eslint/no-attribute-decorator': 'error',
      '@angular-eslint/no-output-on-prefix': 'error',
    },
  },
  {
    files: ['**/*.html'],
    extends: [
      ...angular.configs.templateRecommended,
      ...angular.configs.templateAccessibility,
      prettierConfig, // Mantemos para ativar a regra prettier/prettier
    ],
    rules: {
      '@angular-eslint/template/no-negated-async': 'error',
      '@angular-eslint/template/no-call-expression': 'error',
      '@angular-eslint/template/conditional-complexity': [
        'warn',
        { maxComplexity: 3 },
      ],
      // ADIÇÃO CRÍTICA AQUI: Informar ao prettier para usar o parser HTML
      'prettier/prettier': ['error', { parser: 'html' }],
    },
  },
);
