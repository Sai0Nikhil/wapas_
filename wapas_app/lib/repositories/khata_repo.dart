import 'package:flutter/foundation.dart';
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
  Future<Map<String, dynamic>> addManualEntry({
    String? accountId,
    String? customerName,
    String? customerPhone,
    required String entryType, // "CREDIT_GIVEN" (Udhaar) or "REPAYMENT" (Jama)
    required int amountPaise,
    String note = '',
    String paymentMethod = 'CASH',
  });
  Future<PaymentLinkResponse> createPaymentLink(String accountId, int amountPaise);
  Future<void> reverseEntry(String entryId, String reason);
  Future<AgingBucketsModel> getAgingBuckets();
  Future<String> getStatementCsv(String accountId);
}

class HttpKhataRepo implements KhataRepo {
  final ApiClient _client;

  HttpKhataRepo(this._client);

  @override
  Future<List<KhataAccountModel>> getAccounts({String? search}) async {
    final params = <String, dynamic>{
      'limit': 100,
    };
    dynamic res;
    try {
      res = await _client.get('/api/merchant/khata/accounts', queryParams: params);
    } catch (e) {
      debugPrint('HttpKhataRepo: /api/merchant/khata/accounts failed, trying demo fallback: $e');
      res = await _client.get('/api/demo/khata/accounts', queryParams: params);
    }

    if (res is List) {
      final list = res
          .map((a) => KhataAccountModel.fromJson(a as Map<String, dynamic>))
          .toList();
      if (search != null && search.isNotEmpty) {
        final query = search.toLowerCase();
        return list
            .where((a) =>
                a.customerName.toLowerCase().contains(query) ||
                a.phone.contains(query))
            .toList();
      }
      return list;
    }
    if (res is Map<String, dynamic> && res['items'] is List) {
      return (res['items'] as List)
          .map((a) => KhataAccountModel.fromJson(a as Map<String, dynamic>))
          .toList();
    }
    return [];
  }

  @override
  Future<Map<String, dynamic>> getAccountDetail(String accountId) async {
    try {
      final res = await _client.get('/api/merchant/khata/accounts/$accountId');
      if (res is Map<String, dynamic>) return res;
    } catch (e) {
      debugPrint('HttpKhataRepo: /api/merchant/khata/accounts/$accountId failed, trying demo fallback: $e');
    }
    try {
      final res = await _client.get('/api/demo/khata/accounts/$accountId');
      if (res is Map<String, dynamic>) return res;
    } catch (_) {}
    return {};
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
      'method': method.toUpperCase() == 'CASH' ? 'CASH' : 'OTHER',
      'idempotency_key': idempotencyKey,
      'note': note,
      'confirm_received': confirmReceived,
    };
    try {
      await _client.post(
        '/api/merchant/khata/accounts/$accountId/repayments',
        body: payload,
      );
    } catch (e) {
      debugPrint('recordRepayment: merchant route failed, trying demo fallback: $e');
      await _client.post(
        '/api/demo/khata/entries',
        body: {
          'account_id': accountId,
          'entry_type': 'REPAYMENT',
          'amount_paise': amountPaise,
          'note': note,
          'payment_method': method.toUpperCase() == 'CASH' ? 'CASH' : 'OTHER',
          'idempotency_key': idempotencyKey,
        },
      );
    }
  }

  @override
  Future<Map<String, dynamic>> addManualEntry({
    String? accountId,
    String? customerName,
    String? customerPhone,
    required String entryType,
    required int amountPaise,
    String note = '',
    String paymentMethod = 'CASH',
  }) async {
    final idempotencyKey = _client.generateIdempotencyKey('manual');
    final payload = {
      if (accountId != null && accountId.isNotEmpty) 'account_id': accountId,
      if (customerName != null && customerName.isNotEmpty) 'customer_name': customerName,
      if (customerPhone != null && customerPhone.isNotEmpty) 'customer_phone': customerPhone,
      'entry_type': entryType,
      'amount_paise': amountPaise,
      'note': note,
      'payment_method': paymentMethod,
      'idempotency_key': idempotencyKey,
    };

    try {
      final res = await _client.post(
        '/api/merchant/khata/entries',
        body: payload,
      );
      if (res is Map<String, dynamic>) return res;
    } catch (e) {
      debugPrint('addManualEntry: merchant route failed, trying demo fallback: $e');
    }

    final res = await _client.post(
      '/api/demo/khata/entries',
      body: payload,
    );
    return res is Map<String, dynamic> ? res : {'ok': true};
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
    final payload = {
      'reason': reason,
    };
    await _client.post(
      '/api/merchant/khata/entries/$entryId/reverse',
      body: payload,
    );
  }

  @override
  Future<AgingBucketsModel> getAgingBuckets() async {
    try {
      final res = await _client.get('/api/merchant/khata/aging');
      return AgingBucketsModel.fromJson(res as Map<String, dynamic>);
    } catch (_) {
      return AgingBucketsModel(
        zeroToThirty: 0,
        thirtyOneToSixty: 0,
        sixtyOneToNinety: 0,
        ninetyPlus: 0,
        totalOutstandingPaise: 0,
      );
    }
  }

  @override
  Future<String> getStatementCsv(String accountId) async {
    final res = await _client.get('/api/merchant/khata/accounts/$accountId/statement.csv');
    return res?.toString() ?? '';
  }
}
