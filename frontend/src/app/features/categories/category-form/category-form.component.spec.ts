import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, Router } from '@angular/router';
import { of } from 'rxjs';

import { CategoryFormComponent } from './category-form.component';
import { CategoryService } from '../../../core/services/category.service';

/**
 * Regra de negocio: categorias do sistema (tenant_id 'system') sao globais e
 * NAO podem ser editadas. Somente as categorias personalizadas do proprio
 * usuario. O backend rejeita o PUT com 403; estes testes garantem que o
 * formulario tambem barra antes do usuario digitar.
 */

function category(over: Partial<any> = {}): any {
  return { id: 1, tenant_id: 'tenant-1', name: 'Mercado', description: 'Compras', ...over };
}

describe('CategoryFormComponent', () => {
  let svc: any;

  function setup(opts: { id?: string | null; category?: any } = {}) {
    svc = {
      get: jasmine.createSpy('get').and.returnValue(of(opts.category ?? category())),
      create: jasmine.createSpy('create').and.returnValue(of(category())),
      update: jasmine.createSpy('update').and.returnValue(of(category())),
    };

    TestBed.configureTestingModule({
      imports: [CategoryFormComponent],
      providers: [
        {
          provide: ActivatedRoute,
          useValue: { snapshot: { paramMap: { get: () => opts.id ?? null } } },
        },
        { provide: CategoryService, useValue: svc },
        { provide: Router, useValue: { navigate: jasmine.createSpy('navigate') } },
      ],
    });

    const fixture = TestBed.createComponent(CategoryFormComponent);
    fixture.detectChanges();
    return fixture;
  }

  describe('categoria do sistema', () => {
    it('marca isSystem, desabilita o formulario e explica o motivo', () => {
      const f = setup({ id: '5', category: category({ id: 5, tenant_id: 'system' }) });
      const c = f.componentInstance;

      expect(c.isSystem()).toBeTrue();
      expect(c.form.disabled).toBeTrue();
      expect(c.errorMessage()).toContain('não podem ser editadas');
    });

    it('nao esconde os dados: os campos continuam preenchidos para leitura', () => {
      const f = setup({ id: '5', category: category({ id: 5, tenant_id: 'system', name: 'Lazer' }) });

      expect(f.componentInstance.form.getRawValue().name).toBe('Lazer');
    });

    it('submit nao chama o update mesmo se disparado na mao', () => {
      const f = setup({ id: '5', category: category({ id: 5, tenant_id: 'system' }) });

      f.componentInstance.submit();

      expect(svc.update).not.toHaveBeenCalled();
    });

    it('esconde o botao salvar', () => {
      const f = setup({ id: '5', category: category({ id: 5, tenant_id: 'system' }) });
      const submitBtn = f.nativeElement.querySelector('button[type="submit"]');

      expect(submitBtn).toBeNull();
    });
  });

  describe('categoria personalizada', () => {
    it('permanece editavel e salva normalmente', () => {
      const f = setup({ id: '5', category: category({ id: 5, tenant_id: 'tenant-1' }) });
      const c = f.componentInstance;

      expect(c.isSystem()).toBeFalse();
      expect(c.form.enabled).toBeTrue();

      c.submit();

      expect(svc.update).toHaveBeenCalled();
    });

    it('mantem o botao salvar visivel', () => {
      const f = setup({ id: '5', category: category({ id: 5, tenant_id: 'tenant-1' }) });

      expect(f.nativeElement.querySelector('button[type="submit"]')).not.toBeNull();
    });
  });

  describe('criacao', () => {
    it('sem id na rota nao consulta o backend nem bloqueia o form', () => {
      const f = setup({ id: null });
      const c = f.componentInstance;

      expect(svc.get).not.toHaveBeenCalled();
      expect(c.isEdit()).toBeFalse();
      expect(c.isSystem()).toBeFalse();
      expect(c.form.enabled).toBeTrue();
    });
  });
});
