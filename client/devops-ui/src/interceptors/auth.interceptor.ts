import {HttpContextToken, HttpInterceptorFn} from '@angular/common/http';
import {inject} from "@angular/core";
import { RequestService } from '../services/request.service';

export const SKIP_AUTH = new HttpContextToken(() => false);
export const SKIP_AUTH_TRUE = {context: SKIP_AUTH, value: true}

export const authInterceptor: HttpInterceptorFn = (req, next) => {

  const authToken = inject(RequestService).authToken;

  if (!authToken || req.context.get(SKIP_AUTH)) {
    return next(req);
  }

  req = req.clone({
    headers: req.headers.append('Authorization', `Bearer ${authToken}`)
  });

  return next(req);

};
