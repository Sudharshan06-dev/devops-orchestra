import { Routes } from '@angular/router';
import { LoginComponentComponent } from '../auth/login-component/login-component.component';
import { ChatInterfaceComponent } from '../screens/pages/chat-interface/chat-interface.component';
import { DashboardComponent } from '../screens/dashboard/dashboard.component';
import { ProfileComponent } from '../shared/profile/profile.component';
import { LogDashboardComponent } from '../screens/pages/log-dashboard/log-dashboard.component';

export const routes: Routes = [
    {path: '', component: LoginComponentComponent},
  {path: 'login', component: LoginComponentComponent},
  {
  path: 'dashboard',
  component: DashboardComponent, // wrapper layout
  children: [
    { path: 'chat', component: ChatInterfaceComponent },
    { path: 'log-dashboard', component: LogDashboardComponent },
    { path: 'profile', component: ProfileComponent },
    { path: '', redirectTo: 'chat', pathMatch: 'full' }
  ]
}
];
