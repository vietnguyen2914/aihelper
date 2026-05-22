package com.example.payment;

import java.util.HashMap;
import java.util.Map;

public class PaymentService {
    private static final double MAX_AMOUNT = 10000.0;
    private Map<String, Double> transactions = new HashMap<>();

    public boolean processPayment(String orderId, double amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("Amount must be positive");
        }

        // BUG: Missing null check for orderId
        if (transactions.containsKey(orderId)) {
            throw new IllegalStateException("Order already processed");
        }

        // BUG: Race condition - no synchronization
        transactions.put(orderId, amount);
        return validateTransaction(orderId);
    }

    private boolean validateTransaction(String orderId) {
        Double amount = transactions.get(orderId);
        if (amount == null) {
            return false;
        }
        return amount > 0 && amount <= MAX_AMOUNT;
    }

    // BUG: Missing method referenced by diagnostics
    // public boolean validateAmount(double amount) { ... }

    public void rollback(String orderId) {
        transactions.remove(orderId);
    }
}
