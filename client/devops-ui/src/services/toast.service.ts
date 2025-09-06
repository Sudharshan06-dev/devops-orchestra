import {ToastrService} from "ngx-toastr";
import {Injectable} from "@angular/core";

@Injectable({
    providedIn: 'root'
})

export class ToasterHelper {

    constructor(private toasterService: ToastrService) { }

    public success(data: any) {
        return this.toasterService.success(data.message, data.title);
    }

    public error(data: any) {
        return this.toasterService.error(data.message, data.title);
    }

    public warning(data: any) {
        return this.toasterService.warning(data.message, data.title);
    }
}
