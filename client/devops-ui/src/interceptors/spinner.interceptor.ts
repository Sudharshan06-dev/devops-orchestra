import {HttpContextToken, HttpInterceptorFn} from '@angular/common/http';
import {inject} from "@angular/core";
import {NgxSpinnerService} from "ngx-spinner";
import {finalize} from "rxjs";

export const SKIP_SPINNER = new HttpContextToken(() => false);
export const SKIP_SPINNER_TRUE = {context: SKIP_SPINNER, value: true}

export const spinnerInterceptor: HttpInterceptorFn = (req, next) => {

    let ngxSpinner = inject(NgxSpinnerService);
    let totalRequests = 0;

    if (req.context.get(SKIP_SPINNER)) {
        return next(req);
    }

    ngxSpinner.show();
    totalRequests++

    return next(req).pipe(finalize(() => {
            totalRequests--;
            if (totalRequests === 0) {
                ngxSpinner.hide();
            }
        }
    ));
};
