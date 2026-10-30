import 'package:flutter/material.dart';
import '../theme/app_theme.dart';
import '../services/store_state.dart';
import '../models/app_models.dart';

class RecoveryTowerScreen extends StatelessWidget {
  const RecoveryTowerScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: storeState,
      builder: (context, _) {
        final totalRecovered = storeState.recoveryCases
            .where((c) => c.status == "RECOVERED")
            .fold(0.0, (acc, item) => acc + item.amount);

        final pendingRecovery = storeState.recoveryCases
            .where((c) => c.status != "RECOVERED")
            .fold(0.0, (acc, item) => acc + item.amount);

        return Scaffold(
          backgroundColor: AppColors.surface,
          appBar: AppBar(
            backgroundColor: AppColors.surfaceLowest,
            title: const Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  "AI Recovery Control Tower",
                  style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
                ),
                Text(
                  "See the leak • Act in customer language • Paytm verified",
                  style: TextStyle(fontSize: 11, color: AppColors.outline),
                ),
              ],
            ),
          ),
          body: SingleChildScrollView(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Top Autonomous Impact Card
                Container(
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
                        color: Colors.black.withOpacity(0.12),
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
                              color: Colors.white.withOpacity(0.12),
                              borderRadius: BorderRadius.circular(8),
                            ),
                            child: const Text(
                              "FAIL-CLOSED",
                              style: TextStyle(fontSize: 10, color: Colors.white, fontWeight: FontWeight.w600),
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
                                  "Recovered Today",
                                  style: TextStyle(fontSize: 12, color: Color(0xFFC1C6DB)),
                                ),
                                const SizedBox(height: 4),
                                Text(
                                  "₹${totalRecovered.toStringAsFixed(0)}",
                                  style: const TextStyle(
                                    fontSize: 26,
                                    fontWeight: FontWeight.w800,
                                    color: Color(0xFF4EDEA3),
                                  ),
                                ),
                              ],
                            ),
                          ),
                          Container(
                            width: 1,
                            height: 40,
                            color: Colors.white.withOpacity(0.2),
                          ),
                          const SizedBox(width: 16),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                const Text(
                                  "Eligible In-Pipeline",
                                  style: TextStyle(fontSize: 12, color: Color(0xFFC1C6DB)),
                                ),
                                const SizedBox(height: 4),
                                Text(
                                  "₹${pendingRecovery.toStringAsFixed(0)}",
                                  style: const TextStyle(
                                    fontSize: 26,
                                    fontWeight: FontWeight.w800,
                                    color: Colors.white,
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ],
                      ),
                    ],
                  ),
                ),

                const SizedBox(height: 20),

                // Section Header
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    const Text(
                      "Live Failure Cases & Decisions",
                      style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: AppColors.onSurface),
                    ),
                    Text(
                      "${storeState.recoveryCases.length} Events",
                      style: const TextStyle(fontSize: 12, color: AppColors.outline),
                    ),
                  ],
                ),
                const SizedBox(height: 12),

                // Recovery Cards
                ...storeState.recoveryCases.map((rc) => _buildCaseCard(context, rc)),
              ],
            ),
          ),
        );
      },
    );
  }

  Widget _buildCaseCard(BuildContext context, RecoveryCase rc) {
    Color verdictBg;
    Color verdictFg;
    if (rc.policyVerdict == "ALLOW") {
      verdictBg = AppColors.tertiaryContainer;
      verdictFg = AppColors.onTertiaryContainer;
    } else if (rc.policyVerdict == "ASK_OWNER") {
      verdictBg = const Color(0xFFFFF3CD);
      verdictFg = const Color(0xFF856404);
    } else {
      verdictBg = AppColors.errorContainer;
      verdictFg = AppColors.error;
    }

    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: AppColors.surfaceLowest,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: AppColors.outlineVariant.withOpacity(0.3)),
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
                    rc.customerName,
                    style: const TextStyle(fontSize: 15, fontWeight: FontWeight.bold, color: AppColors.onSurface),
                  ),
                  const SizedBox(width: 6),
                  Text(
                    "(${rc.language})",
                    style: const TextStyle(fontSize: 11, color: AppColors.secondary, fontWeight: FontWeight.w500),
                  ),
                ],
              ),
              Text(
                "₹${rc.amount.toStringAsFixed(0)}",
                style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w800, color: AppColors.onSurface),
              ),
            ],
          ),
          const SizedBox(height: 4),
          Text(
            "Reason: ${rc.failureReason}",
            style: const TextStyle(fontSize: 12, color: AppColors.onSurfaceVariant),
          ),
          const SizedBox(height: 2),
          Text(
            "Provider: ${rc.bank}",
            style: const TextStyle(fontSize: 11, color: AppColors.outline),
          ),
          const SizedBox(height: 10),

          // Policy Verdict & AI Confidence
          Row(
            children: [
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                decoration: BoxDecoration(color: verdictBg, borderRadius: BorderRadius.circular(6)),
                child: Text(
                  "POLICY: ${rc.policyVerdict}",
                  style: TextStyle(fontSize: 10, fontWeight: FontWeight.bold, color: verdictFg),
                ),
              ),
              const SizedBox(width: 8),
              Text(
                "Confidence: ${(rc.confidence * 100).toInt()}%",
                style: const TextStyle(fontSize: 11, color: AppColors.outline),
              ),
              const Spacer(),
              Text(
                rc.timeAgo,
                style: const TextStyle(fontSize: 11, color: AppColors.outline),
              ),
            ],
          ),

          const SizedBox(height: 8),
          Container(
            padding: const EdgeInsets.all(8),
            decoration: BoxDecoration(
              color: AppColors.surfaceLow,
              borderRadius: BorderRadius.circular(8),
            ),
            child: Row(
              children: [
                const Icon(Icons.psychology, size: 16, color: AppColors.secondary),
                const SizedBox(width: 6),
                Expanded(
                  child: Text(
                    rc.plannedAction,
                    style: const TextStyle(fontSize: 11, color: AppColors.onSurface),
                  ),
                ),
              ],
            ),
          ),

          if (rc.policyVerdict == "ASK_OWNER" && rc.status != "SENT") ...[
            const SizedBox(height: 10),
            Row(
              children: [
                Expanded(
                  child: OutlinedButton(
                    onPressed: () {
                      ScaffoldMessenger.of(context).showSnackBar(
                        const SnackBar(content: Text("Action skipped by owner")),
                      );
                    },
                    style: OutlinedButton.styleFrom(
                      side: const BorderSide(color: AppColors.outline),
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                    ),
                    child: const Text("Skip", style: TextStyle(color: AppColors.onSurface)),
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: ElevatedButton(
                    onPressed: () {
                      storeState.approveCase(rc.id);
                      ScaffoldMessenger.of(context).showSnackBar(
                        const SnackBar(
                          backgroundColor: AppColors.secondary,
                          content: Text("Case Approved! Recovery link dispatched via SMS & WhatsApp"),
                        ),
                      );
                    },
                    style: ElevatedButton.styleFrom(
                      backgroundColor: AppColors.secondary,
                      foregroundColor: Colors.white,
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                    ),
                    child: const Text("1-Tap Approve"),
                  ),
                ),
              ],
            ),
          ],
        ],
      ),
    );
  }
}
