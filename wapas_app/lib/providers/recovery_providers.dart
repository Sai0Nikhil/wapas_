import 'dart:async';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/recovery_models.dart';
import 'app_providers.dart';

class RecoveryTowerState {
  final bool isLoading;
  final bool isRefreshing;
  final RecoveryStateData? data;
  final CaseDetailData? activeCaseDetail;
  final String? errorMessage;
  final DateTime? lastUpdated;

  RecoveryTowerState({
    this.isLoading = false,
    this.isRefreshing = false,
    this.data,
    this.activeCaseDetail,
    this.errorMessage,
    this.lastUpdated,
  });

  RecoveryTowerState copyWith({
    bool? isLoading,
    bool? isRefreshing,
    RecoveryStateData? data,
    CaseDetailData? activeCaseDetail,
    String? errorMessage,
    DateTime? lastUpdated,
  }) {
    return RecoveryTowerState(
      isLoading: isLoading ?? this.isLoading,
      isRefreshing: isRefreshing ?? this.isRefreshing,
      data: data ?? this.data,
      activeCaseDetail: activeCaseDetail ?? this.activeCaseDetail,
      errorMessage: errorMessage,
      lastUpdated: lastUpdated ?? this.lastUpdated,
    );
  }
}

class RecoveryTowerNotifier extends Notifier<RecoveryTowerState> {
  @override
  RecoveryTowerState build() {
    // Initial fetch on mount
    Future.microtask(() => fetchState());
    return RecoveryTowerState(isLoading: true);
  }

  Future<void> fetchState({bool isRefresh = false}) async {
    if (!isRefresh && state.data == null) {
      state = state.copyWith(isLoading: true, errorMessage: null);
    } else {
      state = state.copyWith(isRefreshing: true, errorMessage: null);
    }

    try {
      final repo = ref.read(recoveryRepoProvider);
      final data = await repo.fetchState();
      state = state.copyWith(
        isLoading: false,
        isRefreshing: false,
        data: data,
        lastUpdated: DateTime.now(),
        errorMessage: null,
      );
    } catch (e) {
      state = state.copyWith(
        isLoading: false,
        isRefreshing: false,
        errorMessage: e.toString(),
      );
    }
  }

  Future<CaseDetailData?> fetchCaseDetail(String caseId) async {
    try {
      final repo = ref.read(recoveryRepoProvider);
      final detail = await repo.fetchCaseDetail(caseId);
      state = state.copyWith(activeCaseDetail: detail);
      return detail;
    } catch (e) {
      return null;
    }
  }

  Future<bool> approveCase(String caseId) async {
    final oldData = state.data;
    if (oldData == null) return false;

    // Optimistic UI update
    final updatedCases = oldData.cases.map((c) {
      if (c.id == caseId) {
        return RecoveryCaseSummary(
          id: c.id,
          name: c.name,
          customerId: c.customerId,
          language: c.language,
          languageName: c.languageName,
          amount: c.amount,
          amountFmt: c.amountFmt,
          orderId: c.orderId,
          bank: c.bank,
          failureCode: c.failureCode,
          state: 'APPROVED',
          reason: c.reason,
          diagnosis: c.diagnosis,
          confidence: c.confidence,
          messagesSent: c.messagesSent + 1,
          openedAt: c.openedAt,
          source: c.source,
        );
      }
      return c;
    }).toList();

    state = state.copyWith(
      data: RecoveryStateData(
        merchant: oldData.merchant,
        gateway: oldData.gateway,
        llm: oldData.llm,
        sarvam: oldData.sarvam,
        counts: oldData.counts,
        cases: updatedCases,
        messages: oldData.messages,
        events: oldData.events,
      ),
    );

    try {
      final repo = ref.read(recoveryRepoProvider);
      await repo.approveCase(caseId);
      // Re-sync with backend
      await fetchState(isRefresh: true);
      return true;
    } catch (e) {
      // Rollback on failure
      state = state.copyWith(data: oldData, errorMessage: 'Approval failed: $e');
      return false;
    }
  }

  Future<bool> skipCase(String caseId) async {
    final oldData = state.data;
    if (oldData == null) return false;

    // Optimistic UI update
    final updatedCases = oldData.cases.map((c) {
      if (c.id == caseId) {
        return RecoveryCaseSummary(
          id: c.id,
          name: c.name,
          customerId: c.customerId,
          language: c.language,
          languageName: c.languageName,
          amount: c.amount,
          amountFmt: c.amountFmt,
          orderId: c.orderId,
          bank: c.bank,
          failureCode: c.failureCode,
          state: 'SKIPPED',
          reason: 'Skipped by owner',
          diagnosis: c.diagnosis,
          confidence: c.confidence,
          messagesSent: c.messagesSent,
          openedAt: c.openedAt,
          source: c.source,
        );
      }
      return c;
    }).toList();

    state = state.copyWith(
      data: RecoveryStateData(
        merchant: oldData.merchant,
        gateway: oldData.gateway,
        llm: oldData.llm,
        sarvam: oldData.sarvam,
        counts: oldData.counts,
        cases: updatedCases,
        messages: oldData.messages,
        events: oldData.events,
      ),
    );

    try {
      final repo = ref.read(recoveryRepoProvider);
      await repo.skipCase(caseId);
      await fetchState(isRefresh: true);
      return true;
    } catch (e) {
      state = state.copyWith(data: oldData, errorMessage: 'Skip failed: $e');
      return false;
    }
  }

  Future<bool> demoPay(String caseId) async {
    try {
      final repo = ref.read(recoveryRepoProvider);
      final ok = await repo.demoPay(caseId);
      await fetchState(isRefresh: true);
      return ok;
    } catch (e) {
      state = state.copyWith(errorMessage: 'Payment simulation failed: $e');
      return false;
    }
  }

  Future<bool> replayWebhook(String caseId) async {
    try {
      final repo = ref.read(recoveryRepoProvider);
      final ok = await repo.replayWebhook(caseId);
      await fetchState(isRefresh: true);
      return ok;
    } catch (e) {
      state = state.copyWith(errorMessage: 'Webhook replay failed: $e');
      return false;
    }
  }

  Future<bool> resetIncident() async {
    state = state.copyWith(isRefreshing: true);
    try {
      final repo = ref.read(recoveryRepoProvider);
      final ok = await repo.resetIncident();
      await fetchState(isRefresh: true);
      return ok;
    } catch (e) {
      state = state.copyWith(isRefreshing: false, errorMessage: 'Reset failed: $e');
      return false;
    }
  }
}

final recoveryTowerProvider =
    NotifierProvider<RecoveryTowerNotifier, RecoveryTowerState>(RecoveryTowerNotifier.new);
