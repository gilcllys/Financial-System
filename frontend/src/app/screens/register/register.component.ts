import type { OnInit } from '@angular/core';
import { Component, signal, computed, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import type {
  AbstractControl,
  ValidationErrors,
  ValidatorFn,
} from '@angular/forms';
import {
  ReactiveFormsModule,
  FormGroup,
  FormControl,
  Validators,
} from '@angular/forms';
import { MatInputModule } from '@angular/material/input';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { ToastrService } from 'ngx-toastr';

/**
 * Validador customizado para comparar as senhas dentro do FormGroup
 */
export const passwordMatchValidator: ValidatorFn = (
  control: AbstractControl,
): ValidationErrors | null => {
  const password = control.get('userPassword');
  const confirmPassword = control.get('confirmPassword');

  if (password && confirmPassword && password.value !== confirmPassword.value) {
    confirmPassword.setErrors({ passwordMismatch: true });
    return { passwordMismatch: true };
  }
  return null;
};

@Component({
  selector: 'app-register',
  standalone: true,
  imports: [
    ReactiveFormsModule,
    CommonModule,
    MatFormFieldModule,
    MatProgressSpinnerModule,
    MatInputModule,
  ],
  templateUrl: './register.component.html',
  styleUrl: './register.component.css',
})
export class RegisterComponent implements OnInit {
  private toastr = inject(ToastrService);

  registerForm!: FormGroup;
  isLoading = signal(false);

  // Signals para monitorar os critérios da checklist em tempo real
  passwordValue = signal('');
  confirmPasswordValue = signal('');

  // Critérios computados para a Checklist
  hasMinLength = computed(() => this.passwordValue().length >= 8);
  hasUpper = computed(() => /[A-Z]/.test(this.passwordValue()));
  hasNumber = computed(() => /[0-9]/.test(this.passwordValue()));
  passwordsMatch = computed(
    () =>
      this.passwordValue() === this.confirmPasswordValue() &&
      this.passwordValue() !== '',
  );

  ngOnInit(): void {
    this.registerForm = new FormGroup(
      {
        email: new FormControl('', [Validators.required, Validators.email]),
        userPassword: new FormControl('', [Validators.required]),
        confirmPassword: new FormControl('', [Validators.required]),
      },
      { validators: passwordMatchValidator },
    );

    // Sincroniza os valores dos inputs com os Signals
    this.registerForm
      .get('userPassword')
      ?.valueChanges.subscribe((v) => this.passwordValue.set(v || ''));
    this.registerForm
      .get('confirmPassword')
      ?.valueChanges.subscribe((v) => this.confirmPasswordValue.set(v || ''));
  }

  onSubmit(): void {
    if (this.registerForm.valid) {
      this.isLoading.set(true);
      console.log('Formulário enviado:', this.registerForm.value);

      // Simulação de API
      setTimeout(() => {
        this.toastr.success('Conta criada com sucesso!', 'Sucesso');
        this.isLoading.set(false);
      }, 2000);
    } else {
      this.toastr.error('Por favor, preencha os requisitos da senha.', 'Erro');
    }
  }
}
