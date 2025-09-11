import { CommonModule } from '@angular/common';
import { Component, OnInit } from '@angular/core';
import { FormBuilder, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';

import {
  APP_NAME,
  API_ROUTE
} from "../../environment";
import { SKIP_AUTH_TRUE } from '../../interceptors/auth.interceptor';
import { RequestService } from '../../services/request.service';
import { ToasterHelper } from '../../services/toast.service';
import { LocalStorageHelper } from '../../services/local-storage.service';
import { jwtDecode } from 'jwt-decode';

@Component({
  selector: 'app-login-component',
  standalone: true,
  imports: [ReactiveFormsModule, CommonModule],
  templateUrl: './login-component.component.html',
  styleUrl: './login-component.component.css'
})
export class LoginComponentComponent implements OnInit {

  readonly appName = APP_NAME;
  loginForm !: FormGroup;
  signupForm !: FormGroup;
  isLoading = false;
  showPassword = false;
  isLoginMode: boolean = true;

  constructor(
    private fb: FormBuilder,
    private router: Router,
    private route: ActivatedRoute,
    private request: RequestService,
    private localStorage: LocalStorageHelper,
    private toastService: ToasterHelper
  ) { }

  ngOnInit(): void {

    this.route.queryParams.subscribe(params => {

      if (params['token']) {

        const decoded: any = jwtDecode(params['token']);
        const userDetails = {
          email: decoded.sub,
          firstname: decoded.firstname,
          lastname: decoded.lastname
        };
        this.localStorage.storeItem('access_token', params['token'])
        this.localStorage.storeItem('user_details', userDetails)
        this.router.navigate(['/dashboard']);
      }

    });

    this.initializeForm();
  }

  private initializeForm(): void {

    this.loginForm = this.fb.group({
      email: ['', [Validators.required, Validators.email]],
      password: ['', [Validators.required, Validators.minLength(6)]],
    });

    this.signupForm = this.fb.group({
      firstname: [null, [Validators.required, Validators.pattern('[a-zA-Z]+'), Validators.maxLength(35)]],
      lastname: [null, [Validators.required, Validators.pattern('[a-zA-Z]+'), Validators.maxLength(35)]],
      email: [null, [Validators.required, Validators.email]],
      password: [null, [Validators.required, Validators.minLength(8), Validators.maxLength(15)]]
    });

  }

  public onSignup() {

    this.request.post(API_ROUTE + '/register-user', this.signupForm.getRawValue(), [SKIP_AUTH_TRUE]).subscribe({
      next: (data: any) => {
        // Handle successful response here
        this.toastService.success(data);
        this.toggleMode();
      },

      error: (err: any) => {
        // Handle error response here
        this.toastService.error(err?.error);
      }
    });
  }

  public onLogin() {

    this.request.post(API_ROUTE + '/token', this.loginForm.getRawValue(), [SKIP_AUTH_TRUE]).subscribe({
      next: (data: any) => {

        // Handle successful response here
        this.localStorage.storeItem('access_token', data?.access_token)
        this.localStorage.storeItem('user_details', data?.user_details)
        this.router.navigate(['/dashboard']);
      },

      error: (err: any) => {
        // Handle error response here
        this.toastService.error(err?.error);
      }
    });
  }

  public redirectToGoogleAuth() {
    window.location.href = API_ROUTE + '/auth/google/login';
  }

  toggleMode(): void {
    this.isLoginMode = !this.isLoginMode;
  }

  togglePassword(): void {
    this.showPassword = !this.showPassword;
  }

  get firstname() {
    return this.signupForm.get('firstname')
  }

  get lastname() {
    return this.signupForm.get('lastname')
  }

  get email() {
    return this.signupForm.get('email')
  }

  get password() {
    return this.signupForm.get('password');
  }
}
