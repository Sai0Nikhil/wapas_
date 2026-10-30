class ProductItem {
  final String id;
  final String name;
  final String weight;
  final double price;
  final int stock;
  final String category;
  int quantityInCart;

  ProductItem({
    required this.id,
    required this.name,
    required this.weight,
    required this.price,
    required this.stock,
    required this.category,
    this.quantityInCart = 0,
  });
}

class RecoveryCase {
  final String id;
  final String customerName;
  final String customerPhone;
  final String language;
  final double amount;
  final String bank;
  final String failureReason;
  final double confidence;
  final String plannedAction;
  final String policyVerdict; // ALLOW, ASK_OWNER, BLOCK
  final String status; // NEW, SENT, RECOVERED, FAILED
  final String timeAgo;

  RecoveryCase({
    required this.id,
    required this.customerName,
    required this.customerPhone,
    required this.language,
    required this.amount,
    required this.bank,
    required this.failureReason,
    required this.confidence,
    required this.plannedAction,
    required this.policyVerdict,
    required this.status,
    required this.timeAgo,
  });
}

class KhataCustomer {
  final String id;
  final String name;
  final String phone;
  final double totalDue;
  final String lastTransactionDate;
  final String status; // Active, Overdue, Good Standing

  KhataCustomer({
    required this.id,
    required this.name,
    required this.phone,
    required this.totalDue,
    required this.lastTransactionDate,
    required this.status,
  });
}

class SoundboxPaymentAlert {
  final String id;
  final double amount;
  final String customer;
  final String time;
  final String status; // VERIFIED, RECOVERED
  final String orderId;

  SoundboxPaymentAlert({
    required this.id,
    required this.amount,
    required this.customer,
    required this.time,
    required this.status,
    required this.orderId,
  });
}
