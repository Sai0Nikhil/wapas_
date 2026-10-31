class SoundDeviceModel {
  final String deviceKey;
  final int cursor;
  final String soundDefault;

  SoundDeviceModel({
    required this.deviceKey,
    required this.cursor,
    required this.soundDefault,
  });

  factory SoundDeviceModel.fromJson(Map<String, dynamic> json) {
    return SoundDeviceModel(
      deviceKey: (json['device_key'] ?? '').toString(),
      cursor: (json['cursor'] as num?)?.toInt() ?? 0,
      soundDefault: (json['sound_default'] ?? 'MUTED').toString(),
    );
  }
}

class SoundEventModel {
  final int id;
  final String paymentId;
  final String sourceType;
  final String? sourceId;
  final String? providerOrderId;
  final String? providerTransactionId;
  final int amountPaise;
  final String currency;
  final String verifiedAt;

  SoundEventModel({
    required this.id,
    required this.paymentId,
    required this.sourceType,
    this.sourceId,
    this.providerOrderId,
    this.providerTransactionId,
    required this.amountPaise,
    required this.currency,
    required this.verifiedAt,
  });

  factory SoundEventModel.fromJson(Map<String, dynamic> json) {
    return SoundEventModel(
      id: (json['id'] as num?)?.toInt() ?? 0,
      paymentId: (json['payment_id'] ?? '').toString(),
      sourceType: (json['source_type'] ?? 'PAYMENT').toString(),
      sourceId: json['source_id']?.toString(),
      providerOrderId: json['provider_order_id']?.toString(),
      providerTransactionId: json['provider_transaction_id']?.toString(),
      amountPaise: (json['amount_paise'] as num?)?.toInt() ?? 0,
      currency: (json['currency'] ?? 'INR').toString(),
      verifiedAt: (json['verified_at'] ?? '').toString(),
    );
  }

  double get amountInr => amountPaise / 100.0;
}
