import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/khata_models.dart';
import '../repositories/khata_repo.dart';
import 'app_providers.dart';

class KhataLedgerState {
  final List<KhataAccountModel> accounts;
  final AgingBucketsModel? agingBuckets;
  final bool isLoading;
  final String? errorMessage;
  final String searchQuery;
  final KhataAccountModel? selectedAccount;
  final List<KhataEntryModel> selectedAccountEntries;
  final bool isDetailLoading;

  const KhataLedgerState({
    this.accounts = const [],
    this.agingBuckets,
    this.isLoading = false,
    this.errorMessage,
    this.searchQuery = '',
    this.selectedAccount,
    this.selectedAccountEntries = const [],
    this.isDetailLoading = false,
  });

  KhataLedgerState copyWith({
    List<KhataAccountModel>? accounts,
    AgingBucketsModel? agingBuckets,
    bool? isLoading,
    String? errorMessage,
    String? searchQuery,
    KhataAccountModel? selectedAccount,
    List<KhataEntryModel>? selectedAccountEntries,
    bool? isDetailLoading,
    bool clearError = false,
    bool clearSelected = false,
  }) {
    return KhataLedgerState(
      accounts: accounts ?? this.accounts,
      agingBuckets: agingBuckets ?? this.agingBuckets,
      isLoading: isLoading ?? this.isLoading,
      errorMessage: clearError ? null : (errorMessage ?? this.errorMessage),
      searchQuery: searchQuery ?? this.searchQuery,
      selectedAccount: clearSelected ? null : (selectedAccount ?? this.selectedAccount),
      selectedAccountEntries: clearSelected ? const [] : (selectedAccountEntries ?? this.selectedAccountEntries),
      isDetailLoading: isDetailLoading ?? this.isDetailLoading,
    );
  }

  double get totalOutstandingInr =>
      agingBuckets?.totalOutstandingInr ??
      accounts.fold(0.0, (sum, a) => sum + a.balanceInr);
}

class KhataLedgerNotifier extends Notifier<KhataLedgerState> {
  KhataRepo get _repo => ref.read(khataRepoProvider);

  @override
  KhataLedgerState build() {
    Future.microtask(() => refresh());
    return const KhataLedgerState(isLoading: true);
  }

  Future<void> refresh() async {
    state = state.copyWith(isLoading: true, clearError: true);
    try {
      final accounts = await _repo.getAccounts(search: state.searchQuery);
      AgingBucketsModel? aging;
      try {
        aging = await _repo.getAgingBuckets();
      } catch (_) {}
      state = state.copyWith(
        accounts: accounts,
        agingBuckets: aging,
        isLoading: false,
      );
    } catch (e) {
      state = state.copyWith(
        isLoading: false,
        errorMessage: 'Failed to load Khata accounts: $e',
      );
    }
  }

  void setSearchQuery(String query) {
    state = state.copyWith(searchQuery: query);
    refresh();
  }

  Future<void> selectAccount(KhataAccountModel account) async {
    state = state.copyWith(
      selectedAccount: account,
      isDetailLoading: true,
      selectedAccountEntries: [],
    );
    try {
      final detail = await _repo.getAccountDetail(account.id);
      final rawEntries = detail['entries'] as List? ?? [];
      final entries = rawEntries
          .map((e) => KhataEntryModel.fromJson(e as Map<String, dynamic>))
          .toList();
      state = state.copyWith(
        selectedAccountEntries: entries,
        isDetailLoading: false,
      );
    } catch (e) {
      state = state.copyWith(
        isDetailLoading: false,
        errorMessage: 'Failed to load account ledger: $e',
      );
    }
  }

  Future<bool> recordRepayment({
    required String accountId,
    required double amountInr,
    required String method,
    String note = '',
  }) async {
    state = state.copyWith(isLoading: true, clearError: true);
    try {
      final paise = (amountInr * 100).toInt();
      await _repo.recordRepayment(
        accountId: accountId,
        amountPaise: paise,
        method: method,
        note: note,
      );
      await refresh();
      if (state.selectedAccount?.id == accountId) {
        await selectAccount(state.selectedAccount!);
      }
      return true;
    } catch (e) {
      state = state.copyWith(
        isLoading: false,
        errorMessage: 'Repayment failed: $e',
      );
      return false;
    }
  }

  Future<PaymentLinkResponse?> generatePaymentLink(String accountId, double amountInr) async {
    try {
      final paise = (amountInr * 100).toInt();
      return await _repo.createPaymentLink(accountId, paise);
    } catch (e) {
      state = state.copyWith(errorMessage: 'Payment link creation failed: $e');
      return null;
    }
  }

  Future<bool> reverseEntry(String entryId, String reason) async {
    state = state.copyWith(isLoading: true, clearError: true);
    try {
      await _repo.reverseEntry(entryId, reason);
      await refresh();
      if (state.selectedAccount != null) {
        await selectAccount(state.selectedAccount!);
      }
      return true;
    } catch (e) {
      state = state.copyWith(
        isLoading: false,
        errorMessage: 'Reversal failed: $e',
      );
      return false;
    }
  }

  Future<String> downloadStatementCsv(String accountId) async {
    try {
      return await _repo.getStatementCsv(accountId);
    } catch (e) {
      state = state.copyWith(errorMessage: 'CSV download failed: $e');
      return '';
    }
  }
}

final khataLedgerProvider = NotifierProvider<KhataLedgerNotifier, KhataLedgerState>(
  KhataLedgerNotifier.new,
);
