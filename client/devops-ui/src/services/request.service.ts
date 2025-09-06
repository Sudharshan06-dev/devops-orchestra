import { Injectable } from '@angular/core';
import {HttpClient, HttpContext, HttpContextToken} from "@angular/common/http";
import { LocalStorageHelper } from './local-storage.service';

@Injectable({
  providedIn: 'root'
})
export class RequestService {

  constructor(private http: HttpClient, private localStorageService: LocalStorageHelper) { }

  get authToken() {
    return this.localStorageService.getItem('access_token');
  }

  get userDetails() {
    return this.localStorageService.getItem('user_details');
  }

  mergeContexts(...contexts: {context: HttpContextToken<any>, value: any}[]) {

    const httpContext = new HttpContext();

    contexts.forEach(({context, value}) => {
      httpContext.set(context, value);
    });
    return httpContext;
  }

  public post(apiPath: string, requestData: object, config ?: any) {

    const context = config ? this.mergeContexts(...config) : new HttpContext();

    return this.http.post(apiPath, requestData, {
      headers: {'Content-Type': 'application/json'},
      context: context
    });

  }

  public get(apiPath: string, config ?: any) {

    const context = config ? this.mergeContexts(...config) : new HttpContext();

    return this.http.get(apiPath, {
      headers: {'Content-Type': 'application/json'},
      context: context
    });

  }

}
