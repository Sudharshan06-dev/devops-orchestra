import { Routes } from '@angular/router';
import { LoginComponentComponent } from '../auth/login-component/login-component.component';
import { ApplicationDashboardComponent } from '../screens/application-dashboard/application-dashboard.component';

export const routes: Routes = [
    {path: '', component: LoginComponentComponent},
  {path: 'login', component: LoginComponentComponent},
  {path: 'dashboard', component: ApplicationDashboardComponent}
];
