class StoreOrderModel {
  final String id;
  final String orderNumber;
  final String customerName;
  final String customerPhone;
  final int totalPaise;
  final String status; // PENDING, FULFILLED, CANCELLED
  final String createdAt;

  StoreOrderModel({
    required this.id,
    required this.orderNumber,
    required this.customerName,
    required this.customerPhone,
    required this.totalPaise,
    required this.status,
    required this.createdAt,
  });

  factory StoreOrderModel.fromJson(Map<String, dynamic> json) {
    return StoreOrderModel(
      id: (json['id'] ?? '').toString(),
      orderNumber: (json['order_number'] ?? json['id'] ?? '').toString(),
      customerName: (json['customer_name'] ?? 'Online Customer').toString(),
      customerPhone: (json['customer_phone'] ?? '').toString(),
      totalPaise: (json['total_paise'] as num?)?.toInt() ?? 0,
      status: (json['status'] ?? 'PENDING').toString(),
      createdAt: (json['created_at'] ?? '').toString(),
    );
  }

  double get totalInr => totalPaise / 100.0;
  bool get isPending => status == 'PENDING';
}

class AgentActivityModel {
  final String id;
  final String agent;
  final String action;
  final String target;
  final int? amountPaise;
  final String status; // DRAFT, REVIEW_REQUIRED, EXECUTED
  final double confidence;
  final String createdAt;
  final String auditTrail;

  AgentActivityModel({
    required this.id,
    required this.agent,
    required this.action,
    required this.target,
    this.amountPaise,
    required this.status,
    required this.confidence,
    required this.createdAt,
    required this.auditTrail,
  });

  factory AgentActivityModel.fromJson(Map<String, dynamic> json) {
    return AgentActivityModel(
      id: (json['id'] ?? '').toString(),
      agent: (json['agent'] ?? 'Autonomous Agent').toString(),
      action: (json['action'] ?? '').toString(),
      target: (json['target'] ?? '').toString(),
      amountPaise: (json['amount_paise'] as num?)?.toInt(),
      status: (json['status'] ?? 'DRAFT_REVIEW_REQUIRED').toString(),
      confidence: (json['confidence'] as num?)?.toDouble() ?? 0.0,
      createdAt: (json['created_at'] ?? '').toString(),
      auditTrail: (json['audit_trail'] ?? '').toString(),
    );
  }

  double? get amountInr => amountPaise != null ? amountPaise! / 100.0 : null;
}
