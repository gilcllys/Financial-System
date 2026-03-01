import { CommonModule } from '@angular/common';
import type { OnInit } from '@angular/core';
import { Component, computed, inject, signal } from '@angular/core';
import type {
  AbstractControl,
  ValidationErrors,
  ValidatorFn,
} from '@angular/forms';
import {
  FormControl,
  FormGroup,
  ReactiveFormsModule,
  Validators,
} from '@angular/forms';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { Router, RouterLink } from '@angular/router';
import { ToastrService } from 'ngx-toastr';
import { UserRegister } from '../../models';
import { AuthService } from '../../services/auth.service';

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
    RouterLink,
  ],
  templateUrl: './register.component.html',
  styleUrl: './register.component.css',
})
export class RegisterComponent implements OnInit {
  private toastr = inject(ToastrService);
  private authService = inject(AuthService);
  private router = inject(Router);

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
        fullName: new FormControl('', [Validators.required]),
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
    if (this.registerForm.invalid) {
      this.toastr.error('Por favor, preencha os requisitos da senha.', 'Erro');
      return;
    }

    if (!this.passwordsMatch()) {
      this.toastr.error('As senhas não coincidem.', 'Erro');
      return;
    }

    this.isLoading.set(true);
    const { fullName, email, userPassword } = this.registerForm.value;

    // Cria uma instância da classe UserRegister
    const userData = UserRegister.fromFormData(fullName, email, userPassword);

    this.authService.registerUser(userData).subscribe({
      next: (_response) => {
        this.isLoading.set(false);
        this.toastr.success(
          'Conta criada com sucesso! Faça login para continuar.',
          'Sucesso',
        );
        // Redireciona para a página de login
        this.router.navigate(['/']);
      },
      error: (error) => {
        this.isLoading.set(false);
        const errorMessage =
          error.error?.detail ||
          error.error?.message ||
          error.error?.email?.[0] ||
          'Erro ao criar conta. Tente novamente.';
        this.toastr.error(errorMessage, 'Erro');
        console.error('Erro no registro:', error);
      },
    });
  }
}
