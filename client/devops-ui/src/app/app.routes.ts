import { Routes } from '@angular/router';
import { LoginComponentComponent } from '../auth/login-component/login-component.component';

export const routes: Routes = [
    {path: '', redirectTo: 'login', pathMatch:'full'},
    {path: 'login', component: LoginComponentComponent}
];
