import { Component } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { LocalStorageHelper } from '../services/local-storage.service';
import { CommonModule } from '@angular/common';
import { NgxSpinnerComponent } from 'ngx-spinner';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [RouterOutlet, CommonModule, NgxSpinnerComponent],
  templateUrl: './app.component.html',
  styleUrl: './app.component.css'
})
export class AppComponent {
  public readonly title = 'devops-ui';

   public readonly spinnerTemplate = `<svg viewBox="0 0 24 24" width="120" height="120">
    <style>
      @keyframes float {
        0% { transform: translateY(0px); opacity: 0.3; }
        50% { transform: translateY(-2px); opacity: 1; }
        100% { transform: translateY(0px); opacity: 0.3; }
      }
      .layer1 { animation: float 2s infinite ease-in-out; }
      .layer2 { animation: float 2s infinite ease-in-out 0.4s; }
      .layer3 { animation: float 2s infinite ease-in-out 0.8s; }
    </style>
    <path class="layer1" fill="#6c5ce7" d="M12 2L2 7l10 5 10-5-10-5z"/>
    <path class="layer2" fill="#6c5ce7" d="M2 12l10 5 10-5"/>
    <path class="layer3" fill="#6c5ce7" d="M2 17l10 5 10-5"/>
  </svg>`;

    constructor(private localStorage: LocalStorageHelper) {
    }

    get userAuthenticated() {
        return !!this.localStorage.getItem('access_token')
    }

}