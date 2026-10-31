import '../core/network/api_client.dart';
import '../models/billing_models.dart';

abstract class BillingRepo {
  Future<BillModel> createDraftBill({String? customerName, String? customerPhone});
  Future<BillModel> getBill(String billId);
  Future<BillModel> setLine(String billId, String productId, double quantity, {int? unitPricePaise});
  Future<BillModel> removeLine(String billId, String lineId);
  Future<BillModel> issueBill(String billId);
  Future<BillModel> recordPayment(String billId, String method);
  Future<BillModel> chargeToKhata(String billId, String customerPhone, String customerName);
  Future<void> cancelBill(String billId);
  Future<String> getReceiptHtml(String billId);
}

class HttpBillingRepo implements BillingRepo {
  final ApiClient _client;

  HttpBillingRepo(this._client);

  @override
  Future<BillModel> createDraftBill({String? customerName, String? customerPhone}) async {
    final idempotencyKey = _client.generateIdempotencyKey('bill');
    final payload = {
      'idempotency_key': idempotencyKey,
      'customer_name': customerName ?? '',
      'customer_phone': customerPhone ?? '',
    };
    final res = await _client.post('/api/merchant/bills', body: payload);
    return BillModel.fromJson(res as Map<String, dynamic>);
  }

  @override
  Future<BillModel> getBill(String billId) async {
    final res = await _client.get('/api/merchant/bills/$billId');
    return BillModel.fromJson(res as Map<String, dynamic>);
  }

  @override
  Future<BillModel> setLine(String billId, String productId, double quantity, {int? unitPricePaise}) async {
    final payload = {
      'quantity': quantity,
      'unit_price_paise': ?unitPricePaise,
    };
    final res = await _client.put(
      '/api/merchant/bills/$billId/lines/$productId',
      body: payload,
    );
    return BillModel.fromJson(res as Map<String, dynamic>);
  }

  @override
  Future<BillModel> removeLine(String billId, String lineId) async {
    final res = await _client.delete('/api/merchant/bills/$billId/lines/$lineId');
    return BillModel.fromJson(res as Map<String, dynamic>);
  }

  @override
  Future<BillModel> issueBill(String billId) async {
    final idempotencyKey = _client.generateIdempotencyKey('issue');
    final payload = {'idempotency_key': idempotencyKey};
    final res = await _client.post('/api/merchant/bills/$billId/issue', body: payload);
    return BillModel.fromJson(res as Map<String, dynamic>);
  }

  @override
  Future<BillModel> recordPayment(String billId, String method) async {
    final idempotencyKey = _client.generateIdempotencyKey('pay');
    final payload = {
      'method': method,
      'idempotency_key': idempotencyKey,
    };
    final res = await _client.post('/api/merchant/bills/$billId/payments', body: payload);
    return BillModel.fromJson(res as Map<String, dynamic>);
  }

  @override
  Future<BillModel> chargeToKhata(String billId, String customerPhone, String customerName) async {
    final idempotencyKey = _client.generateIdempotencyKey('khata');
    final payload = {
      'customer_phone': customerPhone,
      'customer_name': customerName,
      'idempotency_key': idempotencyKey,
    };
    final res = await _client.post('/api/merchant/bills/$billId/khata', body: payload);
    return BillModel.fromJson(res as Map<String, dynamic>);
  }

  @override
  Future<void> cancelBill(String billId) async {
    await _client.post('/api/merchant/bills/$billId/cancel');
  }

  @override
  Future<String> getReceiptHtml(String billId) async {
    final res = await _client.get('/api/merchant/bills/$billId/receipt');
    return res?.toString() ?? '';
  }
}
