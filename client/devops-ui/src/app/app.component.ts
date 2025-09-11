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

  public readonly spinnerTemplate = `
  <div style="display: flex; align-items: center; justify-content: center; width: 120px; height: 120px;">
    <svg viewBox="0 0 100 100" width="120" height="120">
      <style>
        @keyframes rotate {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
        @keyframes pulse-line {
          0%, 100% { opacity: 0.3; stroke-width: 1; }
          50% { opacity: 1; stroke-width: 1.5; }
        }
        @keyframes float {
          0%, 100% { transform: translateY(0px); }
          50% { transform: translateY(-3px); }
        }
        
        .logo-circle {
          transform-origin: 50% 50%;
          animation: rotate 3s linear infinite;
        }
        .lightning {
          animation: float 2s ease-in-out infinite;
          transform-origin: 50% 50%;
        }
        .line-1 { animation: pulse-line 2s ease-in-out infinite; }
        .line-2 { animation: pulse-line 2s ease-in-out infinite 0.5s; }
        .line-3 { animation: pulse-line 2s ease-in-out infinite 1s; }
        .line-4 { animation: pulse-line 2s ease-in-out infinite 1.5s; }
      </style>
      
      <!-- Outer rotating circle with gradient -->
      <defs>
        <linearGradient id="circleGradient" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" style="stop-color:#ff7b2c;stop-opacity:1" />
          <stop offset="25%" style="stop-color:#4dabf7;stop-opacity:1" />
          <stop offset="50%" style="stop-color:#9c88ff;stop-opacity:1" />
          <stop offset="75%" style="stop-color:#51cf66;stop-opacity:1" />
          <stop offset="100%" style="stop-color:#ff7b2c;stop-opacity:1" />
        </linearGradient>
        
        <linearGradient id="lineGradient" x1="0%" y1="0%" x2="100%" y2="0%">
          <stop offset="0%" style="stop-color:transparent;stop-opacity:0" />
          <stop offset="50%" style="stop-color:#4dabf7;stop-opacity:1" />
          <stop offset="100%" style="stop-color:transparent;stop-opacity:0" />
        </linearGradient>
        
        <linearGradient id="verticalLineGradient" x1="0%" y1="0%" x2="0%" y2="100%">
          <stop offset="0%" style="stop-color:transparent;stop-opacity:0" />
          <stop offset="50%" style="stop-color:#4dabf7;stop-opacity:1" />
          <stop offset="100%" style="stop-color:transparent;stop-opacity:0" />
        </linearGradient>
      </defs>
      
      <!-- Outer circle with gradient border -->
      <circle class="logo-circle" cx="50" cy="50" r="35" 
              fill="none" 
              stroke="url(#circleGradient)" 
              stroke-width="2"/>
      
      <!-- Inner dark circle background -->
      <circle cx="50" cy="50" r="30" fill="#1a1b1e"/>
      
      <!-- Connection lines -->
      <g class="connection-lines">
        <!-- Horizontal line 1 -->
        <line class="line-1" x1="35" y1="35" x2="65" y2="35" 
              stroke="url(#lineGradient)" stroke-width="1"/>
        
        <!-- Vertical line -->
        <line class="line-2" x1="50" y1="30" x2="50" y2="55" 
              stroke="url(#verticalLineGradient)" stroke-width="1"/>
        
        <!-- Horizontal line 2 -->
        <line class="line-3" x1="35" y1="65" x2="65" y2="65" 
              stroke="url(#lineGradient)" stroke-width="1"/>
        
        <!-- Diagonal line -->
        <line class="line-4" x1="65" y1="40" x2="65" y2="60" 
              stroke="url(#verticalLineGradient)" stroke-width="1"/>
      </g>
      
      <!-- Lightning bolt icon in center -->
      <g class="lightning">
        <path d="M52 40 L46 50 L50 50 L48 60 L54 50 L50 50 Z" 
              fill="#ff7b2c" 
              stroke="#ff922b" 
              stroke-width="0.5"/>
      </g>
    </svg>
  </div>
`;

  constructor(private localStorage: LocalStorageHelper) {
  }

  get userAuthenticated() {
    return !!this.localStorage.getItem('access_token')
  }

}