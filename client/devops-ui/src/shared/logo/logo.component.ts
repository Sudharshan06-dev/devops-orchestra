import { Component, Input } from '@angular/core';
import {APP_NAME} from "../../environment";
import { CommonModule } from '@angular/common';

@Component({
  selector: 'app-logo',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './logo.component.html',
  styleUrl: './logo.component.css'
})
export class LogoComponent {

  readonly appName = APP_NAME;

  @Input() public showAppName : boolean = false

  constructor() {

  }

}
