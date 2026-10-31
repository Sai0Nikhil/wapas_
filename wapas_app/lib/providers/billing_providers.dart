import 'dart:async';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/billing_models.dart';
import '../models/catalog_models.dart';
import '../repositories/billing_repo.dart';
import '../repositories/catalog_repo.dart';
import 'app_providers.dart';

class PosBillingState {
  final BillModel? bill;
  final List<ProductModel> catalog;
  final bool isLoading;
  final bool isCatalogLoading;
  final String? errorMessage;
  final Map<String, dynamic>? paymentData;
  final String? receiptHtml;
  final bool isPaymentCompleted;

  const PosBillingState({
    this.bill,
    this.catalog = const [],
    this.isLoading = false,
    this.isCatalogLoading = false,
    this.errorMessage,
    this.paymentData,
    this.receiptHtml,
    this.isPaymentCompleted = false,
  });

  PosBillingState copyWith({
    BillModel? bill,
    List<ProductModel>? catalog,
    bool? isLoading,
    bool? isCatalogLoading,
    String? errorMessage,
    Map<String, dynamic>? paymentData,
    String? receiptHtml,
    bool? isPaymentCompleted,
    bool clearError = false,
    bool clearPayment = false,
  }) {
    return PosBillingState(
      bill: bill ?? this.bill,
      catalog: catalog ?? this.catalog,
      isLoading: isLoading ?? this.isLoading,
      isCatalogLoading: isCatalogLoading ?? this.isCatalogLoading,
      errorMessage: clearError ? null : (errorMessage ?? this.errorMessage),
      paymentData: clearPayment ? null : (paymentData ?? this.paymentData),
      receiptHtml: receiptHtml ?? this.receiptHtml,
      isPaymentCompleted: isPaymentCompleted ?? this.isPaymentCompleted,
    );
  }

  int get cartCount => bill?.lines.fold<int>(0, (sum, l) => sum + l.quantity.toInt()) ?? 0;
  double get cartTotal => bill?.totalInr ?? 0.0;

  double getQuantityForProduct(String productId) {
    if (bill == null) return 0.0;
    for (var l in bill!.lines) {
      if (l.productId == productId) return l.quantity;
    }
    return 0.0;
  }
}

class PosBillingNotifier extends Notifier<PosBillingState> {
  Timer? _pollingTimer;

  BillingRepo get _billingRepo => ref.read(billingRepoProvider);
  CatalogRepo get _catalogRepo => ref.read(catalogRepoProvider);

  @override
  PosBillingState build() {
    ref.onDispose(() {
      _pollingTimer?.cancel();
    });
    // Async load
    Future.microtask(() => init());
    return const PosBillingState(isCatalogLoading: true);
  }

  Future<void> init() async {
    await loadCatalog();
    await ensureDraftBill();
  }

  Future<void> loadCatalog({String? query}) async {
    state = state.copyWith(isCatalogLoading: true, clearError: true);
    try {
      final items = await _catalogRepo.getProducts(query: query);
      state = state.copyWith(catalog: items, isCatalogLoading: false);
    } catch (e) {
      state = state.copyWith(
        isCatalogLoading: false,
        errorMessage: 'Catalog load failed: $e',
      );
    }
  }

  Future<void> ensureDraftBill({String? customerName, String? customerPhone}) async {
    if (state.bill != null && state.bill!.isDraft) return;

    state = state.copyWith(isLoading: true, clearError: true);
    try {
      final bill = await _billingRepo.createDraftBill(
        customerName: customerName ?? 'Counter Customer',
        customerPhone: customerPhone ?? '',
      );
      state = state.copyWith(
        bill: bill,
        isLoading: false,
        clearPayment: true,
        isPaymentCompleted: false,
      );
    } catch (e) {
      state = state.copyWith(
        isLoading: false,
        errorMessage: 'Failed to create draft bill: $e',
      );
    }
  }

  Future<void> addToCart(ProductModel product, {double qty = 1.0}) async {
    await ensureDraftBill();
    if (state.bill == null) return;

    final currentQty = state.getQuantityForProduct(product.id);
    final newQty = currentQty + qty;

    state = state.copyWith(isLoading: true, clearError: true);
    try {
      final updatedBill = await _billingRepo.setLine(
        state.bill!.id,
        product.id,
        newQty,
      );
      state = state.copyWith(bill: updatedBill, isLoading: false);
    } catch (e) {
      state = state.copyWith(
        isLoading: false,
        errorMessage: 'Failed to add item: $e',
      );
    }
  }

  Future<void> removeFromCart(ProductModel product) async {
    if (state.bill == null) return;

    final currentQty = state.getQuantityForProduct(product.id);
    if (currentQty <= 0) return;

    state = state.copyWith(isLoading: true, clearError: true);
    try {
      if (currentQty > 1) {
        final updatedBill = await _billingRepo.setLine(
          state.bill!.id,
          product.id,
          currentQty - 1,
        );
        state = state.copyWith(bill: updatedBill, isLoading: false);
      } else {
        // Find line ID
        final line = state.bill!.lines.firstWhere((l) => l.productId == product.id);
        final updatedBill = await _billingRepo.removeLine(state.bill!.id, line.id);
        state = state.copyWith(bill: updatedBill, isLoading: false);
      }
    } catch (e) {
      state = state.copyWith(
        isLoading: false,
        errorMessage: 'Failed to remove item: $e',
      );
    }
  }

  Future<void> clearCart() async {
    if (state.bill == null) return;

    state = state.copyWith(isLoading: true, clearError: true);
    try {
      await _billingRepo.cancelBill(state.bill!.id);
      final newBill = await _billingRepo.createDraftBill(
        customerName: 'Counter Customer',
      );
      state = state.copyWith(
        bill: newBill,
        isLoading: false,
        clearPayment: true,
        isPaymentCompleted: false,
      );
    } catch (e) {
      state = state.copyWith(
        isLoading: false,
        errorMessage: 'Failed to clear cart: $e',
      );
    }
  }

  Future<ProductModel?> quickAddProduct(String name, double price, {String? barcode}) async {
    state = state.copyWith(isLoading: true, clearError: true);
    try {
      final newProd = await _catalogRepo.addProduct({
        'name': name,
        'price': price,
        'barcode': barcode ?? '',
        'unit': 'each',
        'opening_stock': 50,
      });
      await loadCatalog();
      await addToCart(newProd);
      return newProd;
    } catch (e) {
      state = state.copyWith(
        isLoading: false,
        errorMessage: 'Failed to add custom product: $e',
      );
      return null;
    }
  }

  Future<Map<String, dynamic>?> initiateUpiPayment() async {
    if (state.bill == null) return null;

    state = state.copyWith(isLoading: true, clearError: true);
    try {
      // 1. Issue bill if still DRAFT
      BillModel bill = state.bill!;
      if (bill.isDraft) {
        bill = await _billingRepo.issueBill(bill.id);
        state = state.copyWith(bill: bill);
      }

      // 2. Request payment link
      final paymentData = await _billingRepo.recordPayment(bill.id);
      state = state.copyWith(
        paymentData: paymentData,
        isLoading: false,
      );

      // 3. Start polling for payment verification
      _startPaymentPolling(bill.id);

      return paymentData;
    } catch (e) {
      state = state.copyWith(
        isLoading: false,
        errorMessage: 'Payment initialization failed: $e',
      );
      return null;
    }
  }

  void _startPaymentPolling(String billId) {
    _pollingTimer?.cancel();
    _pollingTimer = Timer.periodic(const Duration(seconds: 3), (timer) async {
      try {
        final bill = await _billingRepo.getBill(billId);
        if (bill.isPaid) {
          timer.cancel();
          final receipt = await _billingRepo.getReceiptHtml(billId);
          state = state.copyWith(
            bill: bill,
            receiptHtml: receipt,
            isPaymentCompleted: true,
          );
        }
      } catch (_) {}
    });
  }

  Future<bool> completeCashPayment() async {
    if (state.bill == null) return false;

    state = state.copyWith(isLoading: true, clearError: true);
    try {
      BillModel bill = state.bill!;
      if (bill.isDraft) {
        bill = await _billingRepo.issueBill(bill.id);
      }
      final receipt = await _billingRepo.getReceiptHtml(bill.id);
      state = state.copyWith(
        bill: bill,
        receiptHtml: receipt,
        isLoading: false,
        isPaymentCompleted: true,
      );
      return true;
    } catch (e) {
      state = state.copyWith(
        isLoading: false,
        errorMessage: 'Cash payment failed: $e',
      );
      return false;
    }
  }

  Future<bool> completeKhataPayment({String? note, DateTime? dueAt}) async {
    if (state.bill == null) return false;

    state = state.copyWith(isLoading: true, clearError: true);
    try {
      BillModel bill = state.bill!;
      if (bill.isDraft) {
        bill = await _billingRepo.issueBill(bill.id);
      }
      await _billingRepo.chargeToKhata(bill.id, note: note, dueAt: dueAt);
      final receipt = await _billingRepo.getReceiptHtml(bill.id);
      state = state.copyWith(
        bill: bill,
        receiptHtml: receipt,
        isLoading: false,
        isPaymentCompleted: true,
      );
      return true;
    } catch (e) {
      state = state.copyWith(
        isLoading: false,
        errorMessage: 'Khata charge failed: $e',
      );
      return false;
    }
  }

  Future<void> startFreshBill() async {
    _pollingTimer?.cancel();
    state = state.copyWith(
      clearPayment: true,
      isPaymentCompleted: false,
      receiptHtml: null,
      isLoading: true,
    );
    try {
      final bill = await _billingRepo.createDraftBill(
        customerName: 'Counter Customer',
      );
      state = state.copyWith(
        bill: bill,
        isLoading: false,
      );
    } catch (e) {
      state = state.copyWith(
        isLoading: false,
        errorMessage: 'Failed to start fresh bill: $e',
      );
    }
  }
}

final posBillingProvider = NotifierProvider<PosBillingNotifier, PosBillingState>(
  PosBillingNotifier.new,
);
