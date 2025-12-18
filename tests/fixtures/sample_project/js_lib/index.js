/**
 * Main entry point for the JS library.
 */

export function calculateTotal(items) {
    return items.reduce((sum, item) => sum + item.price, 0);
}

export class ShoppingCart {
    constructor() {
        this.items = [];
    }

    addItem(item) {
        this.items.push(item);
    }

    removeItem(itemId) {
        this.items = this.items.filter(item => item.id !== itemId);
    }

    getTotal() {
        return calculateTotal(this.items);
    }

    clear() {
        this.items = [];
    }
}
