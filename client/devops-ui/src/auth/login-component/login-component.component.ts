import { CommonModule } from '@angular/common';
import { Component, OnInit } from '@angular/core';
import { FormBuilder, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router } from '@angular/router';
import {
  APP_NAME,
  AUTH_ROUTE,
  AUTH_SSO_PATH
} from "../../environment";
import { SKIP_AUTH_TRUE } from '../../interceptors/auth.interceptor';
import { RequestService } from '../../services/request.service';
import { ToasterHelper } from '../../services/toast.service';
import { LocalStorageHelper } from '../../services/local-storage.service';

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
    private request: RequestService,
    private localStorage: LocalStorageHelper,
    private toastService: ToasterHelper
  ) { }

  ngOnInit(): void {
    this.initializeForm();
  }

  private initializeForm(): void {

    this.loginForm = this.fb.group({
      email: ['', [Validators.required, Validators.email]],
      password: ['', [Validators.required, Validators.minLength(6)]],
    });

    this.signupForm = this.fb.group({
      firstName: [null, [Validators.required, Validators.pattern('[a-zA-Z]+'), Validators.maxLength(35)]],
      lastName: [null, [Validators.required, Validators.pattern('[a-zA-Z]+'), Validators.maxLength(35)]],
      email: [null, [Validators.required, Validators.email]],
      password: [null, [Validators.required, Validators.minLength(8), Validators.maxLength(15)]]
    });

  }

  public onSignup() {

    console.log(this.signupForm.getRawValue())
    return

    this.request.post(AUTH_ROUTE + '/register-user', this.signupForm.getRawValue(), [SKIP_AUTH_TRUE]).subscribe({
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

    this.request.post(AUTH_ROUTE + '/login', this.loginForm.getRawValue(), [SKIP_AUTH_TRUE]).subscribe({
      next: (data: any) => {

        //Route to single sign on if google id is found
        if (data?.google_id) {
          this.redirectToGoogleAuth('login');
          return;
        }

        // Handle successful response here
        this.localStorage.storeItem('access_token', data?.access_token)
        this.localStorage.storeItem('user_details', data?.user_details)
        this.router.navigate(['/main-dashboard']);
      },

      error: (err: any) => {
        // Handle error response here
        this.toastService.error(err?.error);
      }
    });
  }

  public redirectToGoogleAuth(type: string) {
    window.location.href = AUTH_SSO_PATH + '/redirect?type=' + type;
  }

  toggleMode(): void {
    this.isLoginMode = !this.isLoginMode;
  }

  togglePassword(): void {
    this.showPassword = !this.showPassword;
  }

  get firstName() {
    return this.signupForm.get('firstName')
  }

  get lastName() {
    return this.signupForm.get('lastName')
  }

  get email() {
    return this.signupForm.get('email')
  }

  get password() {
    return this.signupForm.get('password');
  }
}
