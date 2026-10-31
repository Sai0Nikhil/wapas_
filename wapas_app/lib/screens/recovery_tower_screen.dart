import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';

import '../models/recovery_models.dart';
import '../providers/app_providers.dart';
import '../providers/recovery_providers.dart';
import '../theme/app_theme.dart';

class RecoveryTowerScreen extends ConsumerStatefulWidget {
  const RecoveryTowerScreen({super.key});

  @override
  ConsumerState<RecoveryTowerScreen> createState() => _RecoveryTowerScreenState();
}

class _RecoveryTowerScreenState extends ConsumerState<RecoveryTowerScreen> {
  Timer? _pollTimer;

  @override
  void initState() {
    super.initState();
    // Auto-refresh poll every 5 seconds while foregrounded
    _pollTimer = Timer.periodic(const Duration(seconds: 5), (_) {
      if (mounted) {
        ref.read(recoveryTowerProvider.notifier).fetchState(isRefresh: true);
      }
    });
  }

  @override
  void dispose() {
    _pollTimer?.cancel();
    super.dispose();
  }

  void _showCaseEvidenceModal(BuildContext context, String caseId) async {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (ctx) => _CaseEvidenceSheet(caseId: caseId),
    );
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(recoveryTowerProvider);
    final authState = ref.watch(authNotifierProvider);
    final isOwner = authState.isOwner;
    final counts = state.data?.counts ?? RecoveryCounts.empty();
    final cases = state.data?.cases ?? [];

    return Scaffold(
      backgroundColor: AppColors.surface,
      appBar: AppBar(
        backgroundColor: AppColors.surfaceLowest,
        elevation: 0,
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              "AI Recovery Control Tower",
              style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
            ),
            Row(
              children: [
                Text(
                  state.lastUpdated != null
                      ? "Updated ${DateFormat('HH:mm:ss').format(state.lastUpdated!)}"
                      : "Connecting to live engine...",
                  style: const TextStyle(fontSize: 11, color: AppColors.outline),
                ),
                if (state.isRefreshing) ...[
                  const SizedBox(width: 6),
                  const SizedBox(
                    width: 10,
                    height: 10,
                    child: CircularProgressIndicator(strokeWidth: 1.5, color: AppColors.secondary),
                  ),
                ],
              ],
            ),
          ],
        ),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh, color: AppColors.secondary),
            onPressed: () => ref.read(recoveryTowerProvider.notifier).fetchState(isRefresh: true),
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: () => ref.read(recoveryTowerProvider.notifier).fetchState(isRefresh: true),
        color: AppColors.secondary,
        child: state.isLoading && state.data == null
            ? const Center(child: CircularProgressIndicator(color: AppColors.secondary))
            : state.errorMessage != null && state.data == null
                ? _buildErrorState(state.errorMessage!)
                : ListView(
                    padding: const EdgeInsets.all(16),
                    physics: const AlwaysScrollableScrollPhysics(),
                    children: [
                      // Top Impact Telemetry Card
                      _buildImpactCard(counts, state.data?.gateway ?? 'fake'),
                      const SizedBox(height: 20),

                      // Section Header
                      Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          const Text(
                            "Live Failure Cases & Decisions",
                            style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: AppColors.onSurface),
                          ),
                          Container(
                            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                            decoration: BoxDecoration(
                              color: AppColors.surfaceContainer,
                              borderRadius: BorderRadius.circular(12),
                            ),
                            child: Text(
                              "${cases.length} Cases",
                              style: const TextStyle(fontSize: 12, fontWeight: FontWeight.bold, color: AppColors.secondary),
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 12),

                      if (cases.isEmpty)
                        _buildEmptyState()
                      else
                        ...cases.map((c) => _buildCaseCard(context, c, isOwner)),
                    ],
                  ),
      ),
    );
  }

  Widget _buildImpactCard(RecoveryCounts counts, String gateway) {
    final isPaytm = gateway.toLowerCase() == 'paytm';

    return Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        gradient: const LinearGradient(
          colors: [Color(0xFF0B1C30), Color(0xFF152A4A)],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
        borderRadius: BorderRadius.circular(16),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.12),
            blurRadius: 10,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      child: Column(
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Row(
                children: [
                  Container(
                    width: 10,
                    height: 10,
                    decoration: const BoxDecoration(
                      color: Color(0xFF4EDEA3),
                      shape: BoxShape.circle,
                    ),
                  ),
                  const SizedBox(width: 8),
                  const Text(
                    "AUTONOMOUS REVENUE ENGINE",
                    style: TextStyle(
                      fontSize: 11,
                      fontWeight: FontWeight.bold,
                      color: Color(0xFFC1C6DB),
                      letterSpacing: 0.8,
                    ),
                  ),
                ],
              ),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                decoration: BoxDecoration(
                  color: isPaytm
                      ? Colors.green.withValues(alpha: 0.25)
                      : Colors.orange.withValues(alpha: 0.25),
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(
                    color: isPaytm ? Colors.greenAccent : Colors.orangeAccent,
                    width: 0.5,
                  ),
                ),
                child: Text(
                  isPaytm ? "PAYTM LIVE" : "SIMULATED GATEWAY",
                  style: TextStyle(
                    fontSize: 9,
                    color: isPaytm ? Colors.greenAccent : Colors.orangeAccent,
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      "Recovered",
                      style: TextStyle(fontSize: 12, color: Color(0xFFC1C6DB)),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      counts.recoveredFmt,
                      style: const TextStyle(
                        fontSize: 26,
                        fontWeight: FontWeight.w800,
                        color: Color(0xFF4EDEA3),
                      ),
                    ),
                    Text(
                      "${counts.paid} settled payments",
                      style: const TextStyle(fontSize: 10, color: Color(0xFFC1C6DB)),
                    ),
                  ],
                ),
              ),
              Container(
                width: 1,
                height: 50,
                color: Colors.white.withValues(alpha: 0.2),
              ),
              const SizedBox(width: 16),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      "Waiting Approval",
                      style: TextStyle(fontSize: 12, color: Color(0xFFC1C6DB)),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      "${counts.waitingOwner}",
                      style: const TextStyle(
                        fontSize: 26,
                        fontWeight: FontWeight.w800,
                        color: Colors.amberAccent,
                      ),
                    ),
                    Text(
                      "Flagged: ${counts.flagged} • Stopped: ${counts.stoppedByPolicy}",
                      style: const TextStyle(fontSize: 10, color: Color(0xFFC1C6DB)),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildCaseCard(BuildContext context, RecoveryCaseSummary c, bool isOwner) {
    Color verdictBg;
    Color verdictFg;
    String verdictLabel;

    if (c.state == 'WAITING_OWNER') {
      verdictBg = const Color(0xFFFFF3CD);
      verdictFg = const Color(0xFF856404);
      verdictLabel = 'POLICY: ASK_OWNER';
    } else if (c.isRecovered) {
      verdictBg = AppColors.tertiaryContainer;
      verdictFg = AppColors.onTertiaryContainer;
      verdictLabel = 'RECOVERED & CREDITED';
    } else if (c.isBlocked) {
      verdictBg = AppColors.errorContainer;
      verdictFg = AppColors.error;
      verdictLabel = 'POLICY: BLOCKED';
    } else {
      verdictBg = AppColors.surfaceLow;
      verdictFg = AppColors.secondary;
      verdictLabel = 'STATE: ${c.state}';
    }

    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: AppColors.surfaceLowest,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: AppColors.outlineVariant.withValues(alpha: 0.3)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Row(
                children: [
                  Text(
                    c.name,
                    style: const TextStyle(fontSize: 15, fontWeight: FontWeight.bold, color: AppColors.onSurface),
                  ),
                  const SizedBox(width: 6),
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                    decoration: BoxDecoration(
                      color: AppColors.secondaryContainer.withValues(alpha: 0.15),
                      borderRadius: BorderRadius.circular(6),
                    ),
                    child: Text(
                      c.languageName,
                      style: const TextStyle(fontSize: 10, color: AppColors.secondary, fontWeight: FontWeight.bold),
                    ),
                  ),
                ],
              ),
              Text(
                c.amountFmt,
                style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w800, color: AppColors.onSurface),
              ),
            ],
          ),
          const SizedBox(height: 6),
          if (c.diagnosis != null && c.diagnosis!.isNotEmpty)
            Text(
              c.diagnosis!,
              style: const TextStyle(fontSize: 12, color: AppColors.onSurfaceVariant),
            ),
          if (c.bank != null)
            Padding(
              padding: const EdgeInsets.only(top: 2),
              child: Text(
                "Gateway / Bank: ${c.bank} ${c.failureCode != null ? '(${c.failureCode})' : ''}",
                style: const TextStyle(fontSize: 11, color: AppColors.outline),
              ),
            ),
          const SizedBox(height: 10),

          // Policy Verdict & AI Confidence
          Row(
            children: [
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                decoration: BoxDecoration(color: verdictBg, borderRadius: BorderRadius.circular(6)),
                child: Text(
                  verdictLabel,
                  style: TextStyle(fontSize: 10, fontWeight: FontWeight.bold, color: verdictFg),
                ),
              ),
              const SizedBox(width: 8),
              Text(
                "Confidence: ${(c.confidence * 100).toInt()}%",
                style: const TextStyle(fontSize: 11, color: AppColors.outline),
              ),
              const Spacer(),
              TextButton.icon(
                onPressed: () => _showCaseEvidenceModal(context, c.id),
                icon: const Icon(Icons.analytics_outlined, size: 14),
                label: const Text('Evidence', style: TextStyle(fontSize: 11)),
                style: TextButton.styleFrom(
                  visualDensity: VisualDensity.compact,
                  padding: const EdgeInsets.symmetric(horizontal: 6),
                ),
              ),
            ],
          ),

          // Owner 1-Tap Actions
          if (c.isWaitingOwner) ...[
            const Divider(height: 18),
            Row(
              children: [
                Expanded(
                  child: OutlinedButton(
                    onPressed: isOwner
                        ? () async {
                            final ok = await ref.read(recoveryTowerProvider.notifier).skipCase(c.id);
                            if (ok && context.mounted) {
                              ScaffoldMessenger.of(context).showSnackBar(
                                const SnackBar(content: Text("Case skipped by owner")),
                              );
                            }
                          }
                        : null,
                    style: OutlinedButton.styleFrom(
                      side: const BorderSide(color: AppColors.outline),
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                    ),
                    child: Text(
                      isOwner ? "Skip" : "Owner only",
                      style: const TextStyle(color: AppColors.onSurface, fontSize: 12),
                    ),
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: ElevatedButton(
                    onPressed: isOwner
                        ? () async {
                            final ok = await ref.read(recoveryTowerProvider.notifier).approveCase(c.id);
                            if (ok && context.mounted) {
                              ScaffoldMessenger.of(context).showSnackBar(
                                const SnackBar(
                                  backgroundColor: AppColors.secondary,
                                  content: Text("Case Approved! Recovery link dispatched via SMS & WhatsApp"),
                                ),
                              );
                            }
                          }
                        : null,
                    style: ElevatedButton.styleFrom(
                      backgroundColor: AppColors.secondary,
                      foregroundColor: Colors.white,
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                    ),
                    child: const Text("1-Tap Approve", style: TextStyle(fontSize: 12)),
                  ),
                ),
              ],
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildEmptyState() {
    return Container(
      padding: const EdgeInsets.all(32),
      alignment: Alignment.center,
      child: Column(
        children: [
          Icon(Icons.verified_user, size: 48, color: Colors.green.shade400),
          const SizedBox(height: 12),
          const Text(
            "No active recovery cases",
            style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16),
          ),
          const SizedBox(height: 4),
          const Text(
            "All transactions are settled or verified. The autonomous engine continues monitoring signals in the background.",
            textAlign: TextAlign.center,
            style: TextStyle(color: AppColors.outline, fontSize: 12),
          ),
        ],
      ),
    );
  }

  Widget _buildErrorState(String message) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Icon(Icons.error_outline, size: 48, color: Colors.red),
            const SizedBox(height: 12),
            const Text(
              "Unable to load Recovery Tower data",
              style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16),
            ),
            const SizedBox(height: 6),
            Text(
              message,
              textAlign: TextAlign.center,
              style: const TextStyle(color: AppColors.outline, fontSize: 12),
            ),
            const SizedBox(height: 16),
            ElevatedButton.icon(
              onPressed: () => ref.read(recoveryTowerProvider.notifier).fetchState(),
              icon: const Icon(Icons.refresh),
              label: const Text("Retry Connection"),
              style: ElevatedButton.styleFrom(
                backgroundColor: AppColors.primary,
                foregroundColor: Colors.white,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _CaseEvidenceSheet extends ConsumerWidget {
  final String caseId;

  const _CaseEvidenceSheet({required this.caseId});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final repo = ref.watch(recoveryRepoProvider);

    return Container(
      height: MediaQuery.of(context).size.height * 0.75,
      decoration: const BoxDecoration(
        color: AppColors.surfaceLowest,
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      child: Column(
        children: [
          Container(
            margin: const EdgeInsets.symmetric(vertical: 10),
            width: 40,
            height: 4,
            decoration: BoxDecoration(
              color: Colors.grey.shade300,
              borderRadius: BorderRadius.circular(2),
            ),
          ),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text(
                  "Case Evidence & Job ($caseId)",
                  style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 16),
                ),
                IconButton(
                  icon: const Icon(Icons.close),
                  onPressed: () => Navigator.of(context).pop(),
                ),
              ],
            ),
          ),
          const Divider(height: 1),
          Expanded(
            child: FutureBuilder<CaseDetailData>(
              future: repo.fetchCaseDetail(caseId),
              builder: (context, snapshot) {
                if (snapshot.connectionState == ConnectionState.waiting) {
                  return const Center(child: CircularProgressIndicator(color: AppColors.secondary));
                }
                if (snapshot.hasError) {
                  return Center(child: Text("Failed to load evidence: ${snapshot.error}"));
                }
                final detail = snapshot.data!;
                final dec = detail.decision;

                return ListView(
                  padding: const EdgeInsets.all(16),
                  children: [
                    // Decision Box
                    Container(
                      padding: const EdgeInsets.all(12),
                      decoration: BoxDecoration(
                        color: AppColors.surfaceLow,
                        borderRadius: BorderRadius.circular(10),
                      ),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const Text(
                            "AI Reasoner Decision",
                            style: TextStyle(fontWeight: FontWeight.bold, fontSize: 13, color: AppColors.secondary),
                          ),
                          const SizedBox(height: 4),
                          Text("Diagnosis: ${dec?.diagnosis ?? detail.summary.diagnosis ?? 'N/A'}", style: const TextStyle(fontSize: 12)),
                          Text("Action: ${dec?.chosenAction ?? 'SMS Recovery Link'}", style: const TextStyle(fontSize: 12)),
                          Text("Reasoner: ${dec?.reasoner ?? 'Policy Model'}", style: const TextStyle(fontSize: 12)),
                          Text("Confidence: ${(dec != null ? dec.confidence * 100 : detail.summary.confidence * 100).toInt()}%",
                              style: const TextStyle(fontSize: 12)),
                        ],
                      ),
                    ),
                    const SizedBox(height: 14),

                    // Policy Rules Hit
                    const Text("Policy Rules Evaluated", style: TextStyle(fontWeight: FontWeight.bold, fontSize: 14)),
                    const SizedBox(height: 6),
                    if (detail.policy.isEmpty)
                      const Text("No explicit policy results recorded", style: TextStyle(fontSize: 12, color: AppColors.outline))
                    else
                      ...detail.policy.map((p) => ListTile(
                            dense: true,
                            contentPadding: EdgeInsets.zero,
                            leading: Icon(
                              p.outcome == 'ALLOW' ? Icons.check_circle : Icons.shield,
                              color: p.outcome == 'ALLOW' ? Colors.green : Colors.amber.shade700,
                            ),
                            title: Text("${p.outcome} (Rule: ${p.rule})", style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600)),
                            subtitle: Text("Policy Version: ${p.version}", style: const TextStyle(fontSize: 11)),
                          )),

                    const SizedBox(height: 14),

                    // Action History
                    const Text("Action Dispatch Log", style: TextStyle(fontWeight: FontWeight.bold, fontSize: 14)),
                    const SizedBox(height: 6),
                    if (detail.actions.isEmpty)
                      const Text("No dispatch actions recorded yet", style: TextStyle(fontSize: 12, color: AppColors.outline))
                    else
                      ...detail.actions.map((a) => ListTile(
                            dense: true,
                            contentPadding: EdgeInsets.zero,
                            leading: const Icon(Icons.send, size: 18, color: AppColors.secondary),
                            title: Text(a.kind, style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600)),
                            subtitle: Text("State: ${a.state} • ${a.sentAt ?? 'pending'}", style: const TextStyle(fontSize: 11)),
                          )),
                  ],
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}
