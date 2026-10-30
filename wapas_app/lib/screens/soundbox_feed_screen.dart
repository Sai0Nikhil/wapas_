import 'package:flutter/material.dart';
import '../theme/app_theme.dart';
import '../services/store_state.dart';
import '../models/app_models.dart';

class SoundboxFeedScreen extends StatelessWidget {
  const SoundboxFeedScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: storeState,
      builder: (context, _) {
        final totalAnnounced = storeState.soundboxAlerts.fold(0.0, (acc, a) => acc + a.amount);

        return Scaffold(
          backgroundColor: AppColors.surface,
          appBar: AppBar(
            backgroundColor: AppColors.surfaceLowest,
            title: const Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text("Paytm Soundbox Live", style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
                Text("Real-time voice payment confirmation stream", style: TextStyle(fontSize: 11, color: AppColors.outline)),
              ],
            ),
            actions: [
              IconButton(
                icon: const Icon(Icons.volume_up, color: AppColors.secondary),
                onPressed: () {
                  ScaffoldMessenger.of(context).showSnackBar(
                    const SnackBar(content: Text("Paytm Soundbox Speaker test broadcast: 100% volume")),
                  );
                },
              ),
            ],
          ),
          body: SingleChildScrollView(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Top Soundbox Hardware Status Widget
                Container(
                  padding: const EdgeInsets.all(18),
                  decoration: BoxDecoration(
                    color: AppColors.surfaceLowest,
                    borderRadius: BorderRadius.circular(16),
                    border: Border.all(color: AppColors.outlineVariant.withOpacity(0.3)),
                  ),
                  child: Row(
                    children: [
                      Container(
                        padding: const EdgeInsets.all(12),
                        decoration: BoxDecoration(
                          color: AppColors.tertiaryContainer,
                          shape: BoxShape.circle,
                        ),
                        child: const Icon(Icons.speaker, color: AppColors.tertiary, size: 28),
                      ),
                      const SizedBox(width: 14),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Row(
                              children: [
                                const Text(
                                  "Paytm Soundbox 4G",
                                  style: TextStyle(fontSize: 15, fontWeight: FontWeight.bold, color: AppColors.onSurface),
                                ),
                                const SizedBox(width: 8),
                                Container(
                                  padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                                  decoration: BoxDecoration(
                                    color: AppColors.tertiaryContainer,
                                    borderRadius: BorderRadius.circular(6),
                                  ),
                                  child: const Text(
                                    "ONLINE",
                                    style: TextStyle(fontSize: 9, fontWeight: FontWeight.bold, color: AppColors.onTertiaryContainer),
                                  ),
                                ),
                              ],
                            ),
                            const SizedBox(height: 4),
                            Text(
                              "Today's Voice Broadcasts: ₹${totalAnnounced.toStringAsFixed(2)}",
                              style: const TextStyle(fontSize: 13, color: AppColors.onSurfaceVariant),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),

                const SizedBox(height: 20),
                const Text(
                  "Recent Verified Soundbox Broadcasts",
                  style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: AppColors.onSurface),
                ),
                const SizedBox(height: 12),

                ...storeState.soundboxAlerts.map((alert) => _buildAlertItem(alert)),
              ],
            ),
          ),
        );
      },
    );
  }

  Widget _buildAlertItem(SoundboxPaymentAlert alert) {
    final isRecovered = alert.status == "RECOVERED";

    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: AppColors.surfaceLowest,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppColors.outlineVariant.withOpacity(0.3)),
      ),
      child: Row(
        children: [
          Container(
            padding: const EdgeInsets.all(10),
            decoration: BoxDecoration(
              color: isRecovered ? AppColors.secondaryContainer.withOpacity(0.15) : AppColors.tertiaryContainer,
              shape: BoxShape.circle,
            ),
            child: Icon(
              isRecovered ? Icons.autorenew : Icons.check_circle,
              color: isRecovered ? AppColors.secondary : AppColors.tertiary,
              size: 20,
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Text(
                      alert.customer,
                      style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600, color: AppColors.onSurface),
                    ),
                    const SizedBox(width: 6),
                    if (isRecovered)
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                        decoration: BoxDecoration(
                          color: AppColors.secondaryContainer.withOpacity(0.12),
                          borderRadius: BorderRadius.circular(4),
                        ),
                        child: const Text(
                          "AI RECOVERED",
                          style: TextStyle(fontSize: 9, fontWeight: FontWeight.bold, color: AppColors.secondary),
                        ),
                      ),
                  ],
                ),
                const SizedBox(height: 2),
                Text(
                  "Ref: ${alert.orderId} • ${alert.time}",
                  style: const TextStyle(fontSize: 11, color: AppColors.outline),
                ),
              ],
            ),
          ),
          Text(
            "+₹${alert.amount.toStringAsFixed(0)}",
            style: TextStyle(
              fontSize: 17,
              fontWeight: FontWeight.w800,
              color: isRecovered ? AppColors.secondary : AppColors.tertiary,
            ),
          ),
        ],
      ),
    );
  }
}
