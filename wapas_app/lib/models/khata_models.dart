class KhataAccountModel {
  final String id;
  final String customerName;
  final String phone;
  final int balancePaise;
  final int creditLimitPaise;
  final String? lastActivityAt;

  KhataAccountModel({
    required this.id,
    required this.customerName,
    required this.phone,
    required this.balancePaise,
    required this.creditLimitPaise,
    this.lastActivityAt,
  });

  factory KhataAccountModel.fromJson(Map<String, dynamic> json) {
    return KhataAccountModel(
      id: (json['id'] ?? '').toString(),
      customerName: (json['name'] ?? json['customer_name'] ?? 'Customer').toString(),
      phone: (json['phone'] ?? '').toString(),
      balancePaise: (json['outstanding_paise'] ?? json['balance_paise'] as num?)?.toInt() ?? 0,
      creditLimitPaise: (json['credit_limit_paise'] as num?)?.toInt() ?? 0,
      lastActivityAt: (json['created_at'] ?? json['last_activity_at'])?.toString(),
    );
  }

  double get balanceInr => balancePaise / 100.0;
  double get creditLimitInr => creditLimitPaise / 100.0;
  bool get hasOutstanding => balancePaise > 0;
}

class KhataEntryModel {
  final String id;
  final String type; // DEBIT (credit given), CREDIT (payment received)
  final int amountPaise;
  final int balanceAfterPaise;
  final String note;
  final String createdAt;
  final bool isReversed;

  KhataEntryModel({
    required this.id,
    required this.type,
    required this.amountPaise,
    required this.balanceAfterPaise,
    required this.note,
    required this.createdAt,
    this.isReversed = false,
  });

  factory KhataEntryModel.fromJson(Map<String, dynamic> json) {
    final delta = (json['delta_paise'] as num?)?.toInt() ?? (json['amount_paise'] as num?)?.toInt() ?? 0;
    final isDebit = delta > 0 || json['entry_type'] == 'CREDIT_GIVEN' || json['type'] == 'DEBIT';

    return KhataEntryModel(
      id: (json['id'] ?? '').toString(),
      type: isDebit ? 'DEBIT' : 'CREDIT',
      amountPaise: delta.abs(),
      balanceAfterPaise: (json['running_balance_paise'] ?? json['balance_after_paise'] as num?)?.toInt() ?? 0,
      note: (json['note'] ?? '').toString(),
      createdAt: (json['created_at'] ?? '').toString(),
      isReversed: json['reverses_entry_id'] != null || json['is_reversed'] == true,
    );
  }

  double get amountInr => amountPaise / 100.0;
  double get balanceAfterInr => balanceAfterPaise / 100.0;
  bool get isDebit => type == 'DEBIT';
}

class AgingBucketsModel {
  final int zeroToThirty;
  final int thirtyOneToSixty;
  final int sixtyOneToNinety;
  final int ninetyPlus;
  final int totalOutstandingPaise;

  AgingBucketsModel({
    required this.zeroToThirty,
    required this.thirtyOneToSixty,
    required this.sixtyOneToNinety,
    required this.ninetyPlus,
    required this.totalOutstandingPaise,
  });

  factory AgingBucketsModel.fromJson(Map<String, dynamic> json) {
    final buckets = json['buckets'] is Map<String, dynamic>
        ? json['buckets'] as Map<String, dynamic>
        : <String, dynamic>{};

    return AgingBucketsModel(
      zeroToThirty: (json['current_paise'] ?? buckets['0_30'] as num?)?.toInt() ?? 0,
      thirtyOneToSixty: (json['days_31_60_paise'] ?? buckets['31_60'] as num?)?.toInt() ?? 0,
      sixtyOneToNinety: (json['days_61_90_paise'] ?? buckets['61_90'] as num?)?.toInt() ?? 0,
      ninetyPlus: (json['days_over_90_paise'] ?? buckets['90_plus'] as num?)?.toInt() ?? 0,
      totalOutstandingPaise: (json['total_outstanding_paise'] as num?)?.toInt() ?? 0,
    );
  }

  double get totalOutstandingInr => totalOutstandingPaise / 100.0;
}

class PaymentLinkResponse {
  final String paymentLinkId;
  final String shortUrl;
  final String qrCode;
  final int amountPaise;

  PaymentLinkResponse({
    required this.paymentLinkId,
    required this.shortUrl,
    required this.qrCode,
    required this.amountPaise,
  });

  factory PaymentLinkResponse.fromJson(Map<String, dynamic> json) {
    return PaymentLinkResponse(
      paymentLinkId: (json['payment_id'] ?? json['payment_link_id'] ?? '').toString(),
      shortUrl: (json['checkout_url'] ?? json['short_url'] ?? '').toString(),
      qrCode: (json['checkout_url'] ?? json['qr_code'] ?? '').toString(),
      amountPaise: (json['amount_paise'] as num?)?.toInt() ?? 0,
    );
  }

  double get amountInr => amountPaise / 100.0;
}
