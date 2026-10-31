import 'package:flutter_test/flutter_test.dart';
import 'package:wapas_app/core/network/api_client.dart';
import 'package:wapas_app/repositories/khata_repo.dart';

class MockKhataApiClient extends ApiClient {
  dynamic nextGetResponse;
  dynamic nextPostResponse;

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
}

void main() {
  group('KhataRepo Unit Tests', () {
    late MockKhataApiClient mockClient;
    late HttpKhataRepo repo;

    setUp(() {
      mockClient = MockKhataApiClient();
      repo = HttpKhataRepo(mockClient);
    });

    test('getAccounts parses list of customer accounts', () async {
      mockClient.nextGetResponse = [
        {
          'id': 'khata_1',
          'customer_id': 'cust_1',
          'name': 'Ramesh Kumar',
          'phone': '9876543210',
          'outstanding_paise': 345000,
          'reminder_consent': false,
          'created_at': '2026-10-31T05:00:00Z',
        }
      ];

      final accounts = await repo.getAccounts();
      expect(accounts.length, 1);
      expect(accounts.first.customerName, 'Ramesh Kumar');
      expect(accounts.first.balanceInr, 3450.0);
      expect(accounts.first.hasOutstanding, true);
    });

    test('recordRepayment issues POST with idempotency_key', () async {
      mockClient.nextPostResponse = {
        'entry': {
          'id': 'kentry_1',
          'entry_type': 'REPAYMENT',
          'delta_paise': -50000,
          'note': 'Cash repayment',
          'created_at': '2026-10-31T05:00:00Z',
        },
        'outstanding_paise': 0,
      };

      await repo.recordRepayment(
        accountId: 'khata_1',
        amountPaise: 50000,
        method: 'CASH',
        note: 'Cash repayment',
      );

      expect(mockClient.lastPostPath, '/api/merchant/khata/accounts/khata_1/repayments');
      expect(mockClient.lastPostBody?['amount_paise'], 50000);
      expect(mockClient.lastPostBody?['method'], 'CASH');
      expect(mockClient.lastPostBody?['idempotency_key'], isNotNull);
    });

    test('createPaymentLink returns payment link model', () async {
      mockClient.nextPostResponse = {
        'payment_id': 'pay_lnk_1',
        'checkout_url': 'http://localhost:8000/pay/LNK999',
        'amount_paise': 120000,
      };

      final res = await repo.createPaymentLink('khata_1', 120000);
      expect(res.paymentLinkId, 'pay_lnk_1');
      expect(res.shortUrl, 'http://localhost:8000/pay/LNK999');
      expect(res.amountInr, 1200.0);
    });

    test('getAgingBuckets parses risk distribution brackets', () async {
      mockClient.nextGetResponse = {
        'total_outstanding_paise': 450000,
        'current_paise': 100000,
        'days_31_60_paise': 150000,
        'days_61_90_paise': 120000,
        'days_over_90_paise': 80000,
      };

      final aging = await repo.getAgingBuckets();
      expect(aging.totalOutstandingInr, 4500.0);
      expect(aging.zeroToThirty, 100000);
      expect(aging.thirtyOneToSixty, 150000);
      expect(aging.sixtyOneToNinety, 120000);
      expect(aging.ninetyPlus, 80000);
    });

    test('addManualEntry sends manual credit or repayment payload', () async {
      mockClient.nextPostResponse = {
        'ok': true,
        'account_id': 'khata_1',
        'entry_type': 'CREDIT_GIVEN',
        'amount_paise': 25000,
        'outstanding_paise': 370000,
      };

      final res = await repo.addManualEntry(
        customerName: 'Asha Sharma',
        customerPhone: '9876543299',
        entryType: 'CREDIT_GIVEN',
        amountPaise: 25000,
        note: 'Atta + Dal',
      );

      expect(res['ok'], true);
      expect(mockClient.lastPostPath, '/api/merchant/khata/entries');
      expect(mockClient.lastPostBody?['customer_name'], 'Asha Sharma');
      expect(mockClient.lastPostBody?['customer_phone'], '9876543299');
      expect(mockClient.lastPostBody?['amount_paise'], 25000);
      expect(mockClient.lastPostBody?['entry_type'], 'CREDIT_GIVEN');
    });
  });
}
