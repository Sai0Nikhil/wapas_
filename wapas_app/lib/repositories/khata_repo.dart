import '../core/network/api_client.dart';
import '../models/khata_models.dart';

abstract class KhataRepo {
  Future<List<KhataAccountModel>> getAccounts({String? search});
  Future<Map<String, dynamic>> getAccountDetail(String accountId);
  Future<void> recordRepayment({
    required String accountId,
    required int amountPaise,
    required String method,
    String note = '',
    bool confirmReceived = true,
  });
  Future<PaymentLinkResponse> createPaymentLink(String accountId, int amountPaise);
  Future<void> reverseEntry(String entryId, String reason);
  Future<AgingBucketsModel> getAgingBuckets();
}

class HttpKhataRepo implements KhataRepo {
  final ApiClient _client;

  HttpKhataRepo(this._client);

  @override
  Future<List<KhataAccountModel>> getAccounts({String? search}) async {
    final params = <String, dynamic>{
      if (search != null && search.isNotEmpty) 'search': search,
      'limit': 100,
    };
    final res = await _client.get('/api/merchant/khata/accounts', queryParams: params);
    if (res is Map<String, dynamic> && res['items'] is List) {
      return (res['items'] as List)
          .map((a) => KhataAccountModel.fromJson(a as Map<String, dynamic>))
          .toList();
    }
    return [];
  }

  @override
  Future<Map<String, dynamic>> getAccountDetail(String accountId) async {
    final res = await _client.get('/api/merchant/khata/accounts/$accountId');
    return res is Map<String, dynamic> ? res : {};
  }

  @override
  Future<void> recordRepayment({
    required String accountId,
    required int amountPaise,
    required String method,
    String note = '',
    bool confirmReceived = true,
  }) async {
    final idempotencyKey = _client.generateIdempotencyKey('repay');
    final payload = {
      'amount_paise': amountPaise,
      'method': method,
      'idempotency_key': idempotencyKey,
      'note': note,
      'confirm_received': confirmReceived,
    };
    await _client.post(
      '/api/merchant/khata/accounts/$accountId/repayments',
      body: payload,
    );
  }

  @override
  Future<PaymentLinkResponse> createPaymentLink(String accountId, int amountPaise) async {
    final idempotencyKey = _client.generateIdempotencyKey('plink');
    final payload = {
      'amount_paise': amountPaise,
      'idempotency_key': idempotencyKey,
    };
    final res = await _client.post(
      '/api/merchant/khata/accounts/$accountId/payment-links',
      body: payload,
    );
    return PaymentLinkResponse.fromJson(res as Map<String, dynamic>);
  }

  @override
  Future<void> reverseEntry(String entryId, String reason) async {
    final idempotencyKey = _client.generateIdempotencyKey('rev');
    final payload = {
      'reason': reason,
      'idempotency_key': idempotencyKey,
    };
    await _client.post(
      '/api/merchant/khata/entries/$entryId/reverse',
      body: payload,
    );
  }

  @override
  Future<AgingBucketsModel> getAgingBuckets() async {
    final res = await _client.get('/api/merchant/khata/aging');
    return AgingBucketsModel.fromJson(res as Map<String, dynamic>);
  }
}
