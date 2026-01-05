import type { OnInit } from '@angular/core';
import { inject } from '@angular/core';
import { Component } from '@angular/core';
import { MatInputModule } from '@angular/material/input';
import { MatFormFieldModule } from '@angular/material/form-field';
import { CommonModule } from '@angular/common';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { ToastrService } from 'ngx-toastr';

import {
  // O MÓDULO REACTIVE FORMS É IMPORTADO AQUI
  ReactiveFormsModule,
  FormGroup,
  FormControl,
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
  ],
  templateUrl: './login.component.html',
  styleUrl: './login.component.css',
})
export class LoginComponent implements OnInit {
  loginForm!: FormGroup;
  isLoading = false;
  private toastr = inject(ToastrService);

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
    this.isLoading = true;
    if (this.loginForm.valid) {
      const formData = this.loginForm.value;
      console.log('Form Data:', formData);
      this.isLoading = false;
      this.toastr.success('Login com sucesso!', 'Success');
    } else {
      console.log('Form is invalid');
      this.toastr.error(
        'Por favor, preencha todos os campos obrigatórios.',
        'Error',
      );
      this.isLoading = false;
    }
  }
}
