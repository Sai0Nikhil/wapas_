import 'package:flutter_test/flutter_test.dart';
import 'package:wapas_app/core/network/api_client.dart';
import 'package:wapas_app/repositories/billing_repo.dart';
import 'package:wapas_app/repositories/catalog_repo.dart';


class MockApiClient extends ApiClient {
  dynamic nextGetResponse;
  dynamic nextPostResponse;
  dynamic nextPutResponse;
  dynamic nextDeleteResponse;

  String? lastGetPath;
  String? lastPostPath;
  Map<String, dynamic>? lastPostBody;

  @override
  Future<dynamic> get(String path, {Map<String, dynamic>? queryParams, int maxRetries = 2}) async {
    lastGetPath = path;
    return nextGetResponse;
  }

  @override
  Future<dynamic> post(String path, {dynamic body, Map<String, String>? extraHeaders}) async {
    lastPostPath = path;
    lastPostBody = body is Map<String, dynamic> ? body : null;
    return nextPostResponse;
  }

  @override
  Future<dynamic> put(String path, {dynamic body, Map<String, String>? extraHeaders}) async {
    return nextPutResponse;
  }

  @override
  Future<dynamic> delete(String path, {dynamic body, Map<String, String>? extraHeaders}) async {
    return nextDeleteResponse;
  }
}

void main() {
  group('BillingRepo and CatalogRepo Unit Tests', () {
    late MockApiClient mockClient;
    late HttpBillingRepo billingRepo;
    late HttpCatalogRepo catalogRepo;

    setUp(() {
      mockClient = MockApiClient();
      billingRepo = HttpBillingRepo(mockClient);
      catalogRepo = HttpCatalogRepo(mockClient);
    });

    test('createDraftBill sends idempotency_key and parses draft bill', () async {
      mockClient.nextPostResponse = {
        'id': 'bill_123',
        'bill_number': 'B123',
        'state': 'DRAFT',
        'customer_name': 'Ramesh',
        'customer_phone': '9876543210',
        'total_paise': 0,
        'lines': [],
      };

      final bill = await billingRepo.createDraftBill(
        customerName: 'Ramesh',
        customerPhone: '9876543210',
      );

      expect(bill.id, 'bill_123');
      expect(bill.isDraft, true);
      expect(mockClient.lastPostPath, '/api/merchant/bills');
      expect(mockClient.lastPostBody?['customer_name'], 'Ramesh');
      expect(mockClient.lastPostBody?['idempotency_key'], isNotNull);
    });

    test('setLine calls PUT and updates line quantity', () async {
      mockClient.nextPutResponse = {
        'id': 'bill_123',
        'bill_number': 'B123',
        'state': 'DRAFT',
        'total_paise': 49000,
        'lines': [
          {
            'id': 'line_1',
            'product_id': 'prod_atta',
            'name': 'Aashirvaad Atta 5kg',
            'quantity': '2',
            'unit_price_paise': 24500,
            'line_total_paise': 49000,
          }
        ],
      };

      final bill = await billingRepo.setLine('bill_123', 'prod_atta', 2.0);

      expect(bill.totalPaise, 49000);
      expect(bill.totalInr, 490.0);
      expect(bill.lines.length, 1);
      expect(bill.lines.first.productName, 'Aashirvaad Atta 5kg');
      expect(bill.lines.first.quantity, 2.0);
    });

    test('issueBill transitions bill state to ISSUED', () async {
      mockClient.nextPostResponse = {
        'id': 'bill_123',
        'bill_number': 'B123',
        'state': 'ISSUED',
        'total_paise': 49000,
        'lines': [],
      };

      final bill = await billingRepo.issueBill('bill_123');
      expect(bill.isIssued, true);
      expect(bill.status, 'ISSUED');
    });

    test('recordPayment returns checkout link and simulated mode', () async {
      mockClient.nextPostResponse = {
        'payment_id': 'pay_456',
        'status': 'PENDING',
        'provider': 'fake',
        'checkout_url': 'http://localhost:8000/pay/LNK123',
        'mode': 'SIMULATED',
      };

      final res = await billingRepo.recordPayment('bill_123');
      expect(res['payment_id'], 'pay_456');
      expect(res['checkout_url'], contains('/pay/LNK123'));
      expect(res['mode'], 'SIMULATED');
    });

    test('getProducts parses catalog products from backend list', () async {
      mockClient.nextGetResponse = [
        {
          'id': 'prod_1',
          'name': 'Tata Salt 1kg',
          'unit_price_paise': 2800,
          'available': '120.000',
          'low_stock_threshold': '20.000',
          'barcode': '8901030000002',
          'unit': 'packet',
          'status': 'ACTIVE',
        }
      ];

      final products = await catalogRepo.getProducts();
      expect(products.length, 1);
      expect(products.first.name, 'Tata Salt 1kg');
      expect(products.first.price, 28.0);
      expect(products.first.currentStock, 120.0);
      expect(products.first.isLowStock, false);
    });
  });
}
