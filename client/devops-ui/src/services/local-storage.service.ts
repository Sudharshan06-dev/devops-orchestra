import {Injectable} from "@angular/core";

@Injectable({
    providedIn: 'root'
})

export class LocalStorageHelper {

    constructor() { }

    public storeItem(key : string, value: any) {
        localStorage.setItem(key, JSON.stringify(value));
    }

    public getItem(key : string) {
        const item = localStorage.getItem(key);
        return item ? JSON.parse(item) : null;
    }
}
