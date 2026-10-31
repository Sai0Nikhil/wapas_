import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../theme/app_theme.dart';
import '../models/order_models.dart';
import '../providers/app_providers.dart';

class AgentActivityScreen extends ConsumerStatefulWidget {
  const AgentActivityScreen({super.key});

  @override
  ConsumerState<AgentActivityScreen> createState() => _AgentActivityScreenState();
}

class _AgentActivityScreenState extends ConsumerState<AgentActivityScreen> {
  List<AgentActivityModel> _activities = [];
  bool _isLoading = true;

  @override
  void initState() {
    super.initState();
    _loadActivity();
  }

  Future<void> _loadActivity() async {
    setState(() => _isLoading = true);
    try {
      final items = await ref.read(agentsRepoProvider).getActivities();
      if (mounted) {
        setState(() {
          _activities = items;
          _isLoading = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() => _isLoading = false);
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text("Failed to load agent activity: $e")),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.surface,
      appBar: AppBar(
        backgroundColor: AppColors.surfaceLowest,
        elevation: 0.5,
        title: Row(
          children: const [
            Icon(Icons.smart_toy_outlined, color: AppColors.secondary, size: 22),
            SizedBox(width: 8),
            Text("Autonomous Agent Teammates", style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16)),
          ],
        ),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: _loadActivity,
          ),
        ],
      ),
      body: Column(
        children: [
          // Autonomous Teammates Track 3 Badge Header
          Container(
            width: double.infinity,
            margin: const EdgeInsets.all(12),
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(
              gradient: const LinearGradient(
                colors: [Color(0xFF0D47A1), Color(0xFF1976D2)],
              ),
              borderRadius: BorderRadius.circular(14),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: const [
                Row(
                  children: [
                    Icon(Icons.auto_awesome, color: Colors.amberAccent, size: 20),
                    SizedBox(width: 8),
                    Text(
                      "Paytm Build For India: Track 3",
                      style: TextStyle(color: Colors.amberAccent, fontWeight: FontWeight.bold, fontSize: 12),
                    ),
                  ],
                ),
                SizedBox(height: 6),
                Text(
                  "Autonomous AI Teammates: AI that doesn't just respond, it gets the job done.",
                  style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold, fontSize: 14),
                ),
                SizedBox(height: 4),
                Text(
                  "Wapas agents monitor failed payments, restock thresholds, and overdue Khata 24/7 without owner intervention.",
                  style: TextStyle(color: Colors.white70, fontSize: 11),
                ),
              ],
            ),
          ),

          // Activities List
          Expanded(
            child: _isLoading
                ? const Center(child: CircularProgressIndicator())
                : _activities.isEmpty
                    ? const Center(child: Text("No autonomous actions recorded yet.", style: TextStyle(color: AppColors.outline)))
                    : ListView.separated(
                        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
                        itemCount: _activities.length,
                        separatorBuilder: (ctx, idx) => const SizedBox(height: 8),
                        itemBuilder: (ctx, idx) {
                          final a = _activities[idx];
                          final isExecuted = a.status == "EXECUTED";

                          return Container(
                            padding: const EdgeInsets.all(14),
                            decoration: BoxDecoration(
                              color: AppColors.surfaceLowest,
                              borderRadius: BorderRadius.circular(12),
                              border: Border.all(color: AppColors.outlineVariant.withValues(alpha: 0.4)),
                            ),
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Row(
                                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                                  children: [
                                    Row(
                                      children: [
                                        Container(
                                          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                                          decoration: BoxDecoration(
                                            color: AppColors.secondaryContainer.withValues(alpha: 0.15),
                                            borderRadius: BorderRadius.circular(6),
                                          ),
                                          child: Text(
                                            a.agent,
                                            style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 11, color: AppColors.secondary),
                                          ),
                                        ),
                                        const SizedBox(width: 8),
                                        Text(
                                          "Confidence: ${(a.confidence * 100).toStringAsFixed(0)}%",
                                          style: const TextStyle(fontSize: 11, color: AppColors.outline),
                                        ),
                                      ],
                                    ),
                                    Container(
                                      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                                      decoration: BoxDecoration(
                                        color: isExecuted ? Colors.green.shade100 : Colors.amber.shade100,
                                        borderRadius: BorderRadius.circular(6),
                                      ),
                                      child: Text(
                                        a.status,
                                        style: TextStyle(
                                          fontSize: 10,
                                          fontWeight: FontWeight.bold,
                                          color: isExecuted ? Colors.green.shade800 : Colors.amber.shade900,
                                        ),
                                      ),
                                    ),
                                  ],
                                ),
                                const SizedBox(height: 8),
                                Text(
                                  a.action,
                                  style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 14),
                                ),
                                const SizedBox(height: 4),
                                Text(
                                  "Target: ${a.target}",
                                  style: const TextStyle(fontSize: 12, color: AppColors.onSurfaceVariant),
                                ),
                                if (a.auditTrail.isNotEmpty) ...[
                                  const SizedBox(height: 6),
                                  Container(
                                    padding: const EdgeInsets.all(8),
                                    decoration: BoxDecoration(
                                      color: AppColors.surfaceLow,
                                      borderRadius: BorderRadius.circular(6),
                                    ),
                                    child: Row(
                                      children: [
                                        const Icon(Icons.shield_outlined, size: 14, color: AppColors.secondary),
                                        const SizedBox(width: 6),
                                        Expanded(
                                          child: Text(
                                            "Audit Trail: ${a.auditTrail}",
                                            style: const TextStyle(fontSize: 11, color: AppColors.outline),
                                          ),
                                        ),
                                      ],
                                    ),
                                  ),
                                ],
                              ],
                            ),
                          );
                        },
                      ),
          ),
        ],
      ),
    );
  }
}
