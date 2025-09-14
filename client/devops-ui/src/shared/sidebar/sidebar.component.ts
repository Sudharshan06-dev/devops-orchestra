import { Component } from '@angular/core';
import { LogoComponent } from '../logo/logo.component';
import { Route, Router, RouterModule } from '@angular/router';
import { RequestService } from '../../services/request.service';
import { AUTH_API_ROUTE } from '../../environment';
import { ToastrService } from 'ngx-toastr';
import { ToasterHelper } from '../../services/toast.service';

@Component({
  selector: 'app-sidebar',
  standalone: true,
  imports: [LogoComponent, RouterModule],
  templateUrl: './sidebar.component.html',
  styleUrl: './sidebar.component.css'
})
export class SidebarComponent {

  constructor(private requestService: RequestService, private toastService: ToasterHelper, private router: Router) {}

  logout() {
    this.requestService.get(AUTH_API_ROUTE + '/logout').subscribe({
      next: () => {
        localStorage.clear()
        this.router.navigate(['/login']);
      },
      error : (err: any) => {
        this.toastService.error(err?.error)
      }
    })
  }

}
