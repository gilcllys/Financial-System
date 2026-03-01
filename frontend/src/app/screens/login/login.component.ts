import { CommonModule } from '@angular/common';
import type { OnInit } from '@angular/core';
import { Component, inject } from '@angular/core';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { Router, RouterLink } from '@angular/router';
import { ToastrService } from 'ngx-toastr';
import { AuthService } from '../../services/auth.service';

import {
  FormControl,
  FormGroup,
  // O MÓDULO REACTIVE FORMS É IMPORTADO AQUI
  ReactiveFormsModule,
  Validators,
} from '@angular/forms';

@Component({
  selector: 'app-login',
  imports: [
    ReactiveFormsModule,
    CommonModule,
    MatFormFieldModule,
    MatInputModule,
    MatProgressSpinnerModule,
    RouterLink,
  ],
  templateUrl: './login.component.html',
  styleUrl: './login.component.css',
})
export class LoginComponent implements OnInit {
  loginForm!: FormGroup;
  isLoading = false;
  private toastr = inject(ToastrService);
  private authService = inject(AuthService);
  private router = inject(Router);

  ngOnInit(): void {
    this.loginForm = this.formGroupFields();
  }

  formGroupFields(): FormGroup {
    return new FormGroup({
      email: new FormControl(null, [Validators.required, Validators.email]),
      userPassword: new FormControl(null, [Validators.required]),
    });
  }

  onSubmit(): void {
    if (this.loginForm.invalid) {
      this.toastr.error(
        'Por favor, preencha todos os campos obrigatórios.',
        'Erro',
      );
      return;
    }

    this.isLoading = true;
    const { email, userPassword } = this.loginForm.value;

    this.authService.loginUser(email, userPassword).subscribe({
      next: (_response) => {
        this.isLoading = false;
        this.toastr.success('Login realizado com sucesso!', 'Sucesso');
        // Redireciona para o dashboard
        this.router.navigate(['/dashboard']);
      },
      error: (error) => {
        this.isLoading = false;
        const errorMessage =
          error.error?.detail ||
          error.error?.message ||
          'Erro ao fazer login. Verifique suas credenciais.';
        this.toastr.error(errorMessage, 'Erro');
        console.error('Erro no login:', error);
      },
    });
  }
}
