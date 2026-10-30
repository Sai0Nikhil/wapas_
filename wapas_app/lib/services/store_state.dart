import 'package:flutter/foundation.dart';
import '../models/app_models.dart';

class StoreState extends ChangeNotifier {
  // Store details
  String storeName = "Sharma Kirana (Main)";
  String merchantName = "Sharma Electronics & Kirana";
  bool isSoundboxLive = true;

  // POS Inventory & Cart
  List<ProductItem> inventory = [
    ProductItem(id: "1", name: "Aashirvaad Shudh Chakki Atta", weight: "5kg", price: 245.0, stock: 34, category: "Grains"),
    ProductItem(id: "2", name: "Tata Salt Vacuum Evaporated", weight: "1kg", price: 28.0, stock: 120, category: "Spices"),
    ProductItem(id: "3", name: "Fortune Sunlite Sunflower Oil", weight: "1L", price: 142.0, stock: 45, category: "Edible Oil"),
    ProductItem(id: "4", name: "Amul Butter Pasteurised", weight: "500g", price: 275.0, stock: 18, category: "Dairy"),
    ProductItem(id: "5", name: "Maggi 2-Minute Masala Noodles", weight: "70g", price: 14.0, stock: 85, category: "Instant Food"),
    ProductItem(id: "6", name: "Surf Excel Easy Wash Detergent", weight: "1kg", price: 135.0, stock: 22, category: "Household"),
    ProductItem(id: "7", name: "Parle-G Glucose Biscuits", weight: "250g", price: 25.0, stock: 95, category: "Bakery"),
  ];

  // Recovery Control Tower Cases
  List<RecoveryCase> recoveryCases = [
    RecoveryCase(
      id: "REC-1092",
      customerName: "Ramesh Verma",
      customerPhone: "+91 98450 12345",
      language: "Hindi (हिंदी)",
      amount: 1420.0,
      bank: "SBI (Core Banking Server Timeout)",
      failureReason: "Bank network timeout during UPI PIN entry",
      confidence: 0.94,
      plannedAction: "Sent 1-click Paytm Recovery Link in Hindi with 15m hold",
      policyVerdict: "ALLOW",
      status: "RECOVERED",
      timeAgo: "2m ago",
    ),
    RecoveryCase(
      id: "REC-1093",
      customerName: "Srinivas Rao",
      customerPhone: "+91 97034 56789",
      language: "Telugu (తెలుగు)",
      amount: 5400.0,
      bank: "HDFC Bank (Exceeded daily UPI limit)",
      failureReason: "Daily limit exceeded; needs split or card checkout link",
      confidence: 0.88,
      plannedAction: "Owner approval requested for custom split link (₹5,400 > ₹5,000 threshold)",
      policyVerdict: "ASK_OWNER",
      status: "NEW",
      timeAgo: "5m ago",
    ),
    RecoveryCase(
      id: "REC-1094",
      customerName: "Kavitha Nair",
      customerPhone: "+91 94471 23456",
      language: "Tamil (தமிழ்)",
      amount: 680.0,
      bank: "Canara Bank (Temporary debit reversal)",
      failureReason: "Double debit flagged by payer bank",
      confidence: 0.76,
      plannedAction: "Customer opted out of automated WhatsApp triggers",
      policyVerdict: "BLOCK",
      status: "FAILED",
      timeAgo: "18m ago",
    ),
  ];

  // Khata Ledger
  List<KhataCustomer> khataList = [
    KhataCustomer(id: "KH-1", name: "Suresh Gupta", phone: "+91 98231 44556", totalDue: 2450.0, lastTransactionDate: "Today", status: "Active"),
    KhataCustomer(id: "KH-2", name: "Anand Medicals", phone: "+91 99120 77881", totalDue: 5800.0, lastTransactionDate: "Yesterday", status: "Overdue"),
    KhataCustomer(id: "KH-3", name: "Pooja Sharma", phone: "+91 97412 33221", totalDue: 820.0, lastTransactionDate: "28 Oct", status: "Good Standing"),
    KhataCustomer(id: "KH-4", name: "Rajesh Tailors", phone: "+91 98845 99001", totalDue: 1350.0, lastTransactionDate: "27 Oct", status: "Active"),
  ];

  // Soundbox Live Feed
  List<SoundboxPaymentAlert> soundboxAlerts = [
    SoundboxPaymentAlert(id: "SND-501", amount: 1420.0, customer: "Ramesh Verma", time: "10:14 PM", status: "RECOVERED", orderId: "PAYTM-REC-892"),
    SoundboxPaymentAlert(id: "SND-500", amount: 245.0, customer: "Counter Cashier #1", time: "10:11 PM", status: "VERIFIED", orderId: "POS-BILL-098"),
    SoundboxPaymentAlert(id: "SND-499", amount: 560.0, customer: "Walk-in UPI QR", time: "10:05 PM", status: "VERIFIED", orderId: "POS-BILL-097"),
  ];

  // Cart operations
  void addToCart(ProductItem item) {
    item.quantityInCart++;
    notifyListeners();
  }

  void removeFromCart(ProductItem item) {
    if (item.quantityInCart > 0) {
      item.quantityInCart--;
      notifyListeners();
    }
  }

  void clearCart() {
    for (var item in inventory) {
      item.quantityInCart = 0;
    }
    notifyListeners();
  }

  double get cartTotal {
    double total = 0;
    for (var item in inventory) {
      total += item.price * item.quantityInCart;
    }
    return total;
  }

  int get cartCount {
    int count = 0;
    for (var item in inventory) {
      count += item.quantityInCart;
    }
    return count;
  }

  // Add customer to Khata
  void addKhataCustomer(String name, String phone, double totalDue) {
    khataList.insert(
      0,
      KhataCustomer(
        id: "KH-${khataList.length + 1}",
        name: name,
        phone: phone,
        totalDue: totalDue,
        lastTransactionDate: "Today",
        status: "Active",
      ),
    );
    notifyListeners();
  }

  // Recovery approval action
  void approveCase(String caseId) {
    final idx = recoveryCases.indexWhere((c) => c.id == caseId);
    if (idx != -1) {
      final old = recoveryCases[idx];
      recoveryCases[idx] = RecoveryCase(
        id: old.id,
        customerName: old.customerName,
        customerPhone: old.customerPhone,
        language: old.language,
        amount: old.amount,
        bank: old.bank,
        failureReason: old.failureReason,
        confidence: old.confidence,
        plannedAction: "Authorized by Owner. Recovery link dispatched via SMS & WhatsApp.",
        policyVerdict: "ALLOW",
        status: "SENT",
        timeAgo: "Just now",
      );
      notifyListeners();
    }
  }

  // Record completed counter bill
  void completeCheckout(String paymentMode) {
    if (cartCount == 0) return;
    double billedAmount = cartTotal;
    
    // Add to soundbox feed if UPI
    soundboxAlerts.insert(
      0,
      SoundboxPaymentAlert(
        id: "SND-${soundboxAlerts.length + 500}",
        amount: billedAmount,
        customer: "Counter ($paymentMode)",
        time: "Just now",
        status: "VERIFIED",
        orderId: "BILL-${DateTime.now().millisecondsSinceEpoch.toString().substring(7)}",
      ),
    );

    clearCart();
    notifyListeners();
  }
}

// Global Singleton Store Instance
final storeState = StoreState();
