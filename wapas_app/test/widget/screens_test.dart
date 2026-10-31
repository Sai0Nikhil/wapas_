import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:wapas_app/screens/pos_billing_screen.dart';
import 'package:wapas_app/screens/khata_ledger_screen.dart';
import 'package:wapas_app/screens/soundbox_feed_screen.dart';
import 'package:wapas_app/providers/app_providers.dart';
import 'package:wapas_app/repositories/catalog_repo.dart';
import 'package:wapas_app/repositories/billing_repo.dart';
import 'package:wapas_app/repositories/khata_repo.dart';
import 'package:wapas_app/repositories/sound_repo.dart';
import 'package:wapas_app/models/catalog_models.dart';
import 'package:wapas_app/models/billing_models.dart';
import 'package:wapas_app/models/khata_models.dart';
import 'package:wapas_app/models/sound_models.dart';

class FakeCatalogRepo implements CatalogRepo {
  @override
  Future<List<ProductModel>> getProducts({String? query, String? category}) async {
    return [
      ProductModel(
        id: 'test_atta',
        name: 'Aashirvaad Atta 5kg',
        category: 'Grains',
        price: 245.0,
        unit: 'kg',
        barcode: '8901030000001',
        currentStock: 40.0,
        minStockAlert: 10.0,
        isActive: true,
      ),
    ];
  }

  @override
  Future<ProductModel?> lookupByBarcode(String barcode) async => null;
  @override
  Future<ProductModel> addProduct(Map<String, dynamic> data) async => throw UnimplementedError();
  @override
  Future<void> adjustStock(String productId, double delta, String reason) async {}
  @override
  Future<List<StockMovementModel>> getMovements({String? productId}) async => [];
}

class FakeBillingRepo implements BillingRepo {
  @override
  Future<BillModel> createDraftBill({String? customerName, String? customerPhone}) async {
    return BillModel(
      id: 'draft_1',
      billNumber: 'B101',
      status: 'DRAFT',
      totalPaise: 0,
      lines: [],
    );
  }

  @override
  Future<BillModel> getBill(String billId) async => throw UnimplementedError();
  @override
  Future<BillModel> setLine(String billId, String productId, double quantity, {int? unitPricePaise}) async => throw UnimplementedError();
  @override
  Future<BillModel> removeLine(String billId, String lineId) async => throw UnimplementedError();
  @override
  Future<BillModel> issueBill(String billId) async => throw UnimplementedError();
  @override
  Future<Map<String, dynamic>> recordPayment(String billId) async => {};
  @override
  Future<Map<String, dynamic>> chargeToKhata(String billId, {String? note, DateTime? dueAt}) async => {};
  @override
  Future<void> cancelBill(String billId) async {}
  @override
  Future<String> getReceiptHtml(String billId) async => '';
}

class FakeKhataRepo implements KhataRepo {
  @override
  Future<List<KhataAccountModel>> getAccounts({String? search}) async {
    return [
      KhataAccountModel(
        id: 'khata_1',
        customerName: 'Ramesh Kumar',
        phone: '9876543210',
        balancePaise: 345000,
        creditLimitPaise: 500000,
      ),
    ];
  }

  @override
  Future<Map<String, dynamic>> getAccountDetail(String accountId) async => {'entries': []};
  @override
  Future<void> recordRepayment({required String accountId, required int amountPaise, required String method, String note = '', bool confirmReceived = true}) async {}
  @override
  Future<Map<String, dynamic>> addManualEntry({
    String? accountId,
    String? customerName,
    String? customerPhone,
    required String entryType,
    required int amountPaise,
    String note = '',
    String paymentMethod = 'CASH',
  }) async => {'ok': true};
  @override
  Future<PaymentLinkResponse> createPaymentLink(String accountId, int amountPaise) async => throw UnimplementedError();
  @override
  Future<void> reverseEntry(String entryId, String reason) async {}
  @override
  Future<AgingBucketsModel> getAgingBuckets() async => AgingBucketsModel(
    zeroToThirty: 100000,
    thirtyOneToSixty: 50000,
    sixtyOneToNinety: 0,
    ninetyPlus: 0,
    totalOutstandingPaise: 150000,
  );
  @override
  Future<String> getStatementCsv(String accountId) async => '';
}

class FakeSoundRepo implements SoundRepo {
  @override
  Future<SoundDeviceModel> registerDevice(String deviceKey) async => SoundDeviceModel(deviceKey: deviceKey, cursor: 0, soundDefault: 'MUTED');
  @override
  Future<List<SoundEventModel>> getEvents(String deviceKey, {int limit = 50}) async => [];
  @override
  Future<void> acknowledgeEvent(String deviceKey, int eventId) async {}
}

void main() {
  group('Screen Widget Tests with Fake Repositories', () {
    testWidgets('PosBillingScreen renders catalog items and quick scan buttons', (tester) async {
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            catalogRepoProvider.overrideWithValue(FakeCatalogRepo()),
            billingRepoProvider.overrideWithValue(FakeBillingRepo()),
          ],
          child: const MaterialApp(
            home: PosBillingScreen(),
          ),
        ),
      );

      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      expect(find.text('Scan Item'), findsOneWidget);
      expect(find.text('Scan Parchi'), findsOneWidget);
      expect(find.text('Aashirvaad Atta 5kg'), findsOneWidget);
    });

    testWidgets('KhataLedgerScreen renders aging buckets and customer account row', (tester) async {
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            khataRepoProvider.overrideWithValue(FakeKhataRepo()),
          ],
          child: const MaterialApp(
            home: KhataLedgerScreen(),
          ),
        ),
      );

      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      expect(find.text('Digital Khata Ledger'), findsOneWidget);
      expect(find.text('Credit Aging & Risk Buckets'), findsOneWidget);
      expect(find.text('Ramesh Kumar'), findsOneWidget);
      expect(find.text('9876543210'), findsOneWidget);
    });

    testWidgets('SoundboxFeedScreen renders hardware device status', (tester) async {
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            soundRepoProvider.overrideWithValue(FakeSoundRepo()),
          ],
          child: const MaterialApp(
            home: SoundboxFeedScreen(),
          ),
        ),
      );

      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      expect(find.text('Paytm Soundbox Live'), findsOneWidget);
      expect(find.text('Paytm Soundbox 4G'), findsOneWidget);
    });
  });
}
