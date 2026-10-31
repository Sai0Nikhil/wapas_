class BillLineModel {
  final String id;
  final String productId;
  final String productName;
  final double quantity;
  final int unitPricePaise;
  final int subtotalPaise;

  BillLineModel({
    required this.id,
    required this.productId,
    required this.productName,
    required this.quantity,
    required this.unitPricePaise,
    required this.subtotalPaise,
  });

  factory BillLineModel.fromJson(Map<String, dynamic> json) {
    return BillLineModel(
      id: (json['id'] ?? '').toString(),
      productId: (json['product_id'] ?? '').toString(),
      productName: (json['name'] ?? json['product_name'] ?? 'Item').toString(),
      quantity: num.tryParse((json['quantity'] ?? '1').toString())?.toDouble() ?? 1.0,
      unitPricePaise: (json['unit_price_paise'] as num?)?.toInt() ?? 0,
      subtotalPaise: (json['line_total_paise'] ?? json['subtotal_paise'] as num?)?.toInt() ?? 0,
    );
  }

  double get unitPriceInr => unitPricePaise / 100.0;
  double get subtotalInr => subtotalPaise / 100.0;
}

class BillModel {
  final String id;
  final String billNumber;
  final String status; // DRAFT, ISSUED, PAID, CANCELLED
  final String? customerName;
  final String? customerPhone;
  final int totalPaise;
  final List<BillLineModel> lines;
  final String? paymentMethod;
  final String? paymentStatus;
  final String? qrPayload;
  final String? createdAt;

  BillModel({
    required this.id,
    required this.billNumber,
    required this.status,
    this.customerName,
    this.customerPhone,
    required this.totalPaise,
    required this.lines,
    this.paymentMethod,
    this.paymentStatus,
    this.qrPayload,
    this.createdAt,
  });

  factory BillModel.fromJson(Map<String, dynamic> json) {
    return BillModel(
      id: (json['id'] ?? '').toString(),
      billNumber: (json['bill_number'] ?? '').toString(),
      status: (json['state'] ?? json['status'] ?? 'DRAFT').toString(),
      customerName: json['customer_name']?.toString(),
      customerPhone: json['customer_phone']?.toString(),
      totalPaise: (json['total_paise'] as num?)?.toInt() ?? 0,
      lines: (json['lines'] as List?)
              ?.map((l) => BillLineModel.fromJson(l as Map<String, dynamic>))
              .toList() ??
          [],
      paymentMethod: (json['payment_provider'] ?? json['payment_method'])?.toString(),
      paymentStatus: (json['payment_status'] ?? json['payment_state'])?.toString(),
      qrPayload: (json['payment_url'] ?? json['checkout_url'] ?? json['qr_payload'])?.toString(),
      createdAt: json['created_at']?.toString(),
    );
  }

  double get totalInr => totalPaise / 100.0;
  bool get isDraft => status == 'DRAFT';
  bool get isIssued => status == 'ISSUED';
  bool get isPaid => status == 'PAID' || paymentStatus == 'VERIFIED' || paymentStatus == 'SUCCESS';
}
