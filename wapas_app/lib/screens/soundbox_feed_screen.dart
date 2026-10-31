import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/sound_models.dart';
import '../providers/soundbox_providers.dart';
import '../theme/app_theme.dart';

class SoundboxFeedScreen extends ConsumerWidget {
  const SoundboxFeedScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final soundboxState = ref.watch(soundboxProvider);
    final totalAnnounced = soundboxState.events.fold(0.0, (acc, a) => acc + a.amountInr);

    return Scaffold(
      backgroundColor: AppColors.surface,
      appBar: AppBar(
        backgroundColor: AppColors.surfaceLowest,
        elevation: 0.5,
        title: const Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text("Paytm Soundbox Live", style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
            Text("Acoustic payment verification & 4G event stream", style: TextStyle(fontSize: 11, color: AppColors.outline)),
          ],
        ),
        actions: [
          IconButton(
            icon: Icon(
              soundboxState.isMuted ? Icons.volume_off : Icons.volume_up,
              color: soundboxState.isMuted ? Colors.grey : AppColors.secondary,
            ),
            tooltip: soundboxState.isMuted ? "Unmute Announcements" : "Mute Announcements",
            onPressed: () => ref.read(soundboxProvider.notifier).toggleMute(),
          ),
          IconButton(
            icon: const Icon(Icons.campaign, color: AppColors.secondary),
            tooltip: "Test Speaker Voice Broadcast",
            onPressed: () {
              ref.read(soundboxProvider.notifier).testBroadcast();
              ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(
                  content: Text("Triggered Paytm Soundbox voice announcement test"),
                  backgroundColor: AppColors.secondary,
                ),
              );
            },
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: () => ref.read(soundboxProvider.notifier).pollEvents(),
        color: AppColors.secondary,
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            // Top Soundbox Hardware Status Widget
            Container(
              padding: const EdgeInsets.all(18),
              decoration: BoxDecoration(
                color: AppColors.surfaceLowest,
                borderRadius: BorderRadius.circular(16),
                border: Border.all(color: AppColors.outlineVariant.withValues(alpha: 0.3)),
                boxShadow: [
                  BoxShadow(
                    color: Colors.black.withValues(alpha: 0.04),
                    blurRadius: 10,
                    offset: const Offset(0, 3),
                  ),
                ],
              ),
              child: Row(
                children: [
                  Container(
                    padding: const EdgeInsets.all(12),
                    decoration: BoxDecoration(
                      color: soundboxState.isSpeaking
                          ? Colors.amber.withValues(alpha: 0.2)
                          : AppColors.tertiaryContainer,
                      shape: BoxShape.circle,
                    ),
                    child: Icon(
                      soundboxState.isSpeaking ? Icons.graphic_eq : Icons.speaker,
                      color: soundboxState.isSpeaking ? Colors.amber.shade900 : AppColors.tertiary,
                      size: 28,
                    ),
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
                                color: soundboxState.isRegistered
                                    ? AppColors.tertiaryContainer
                                    : Colors.orange.withValues(alpha: 0.15),
                                borderRadius: BorderRadius.circular(6),
                              ),
                              child: Text(
                                soundboxState.isRegistered ? "ONLINE (4G)" : "REGISTERING",
                                style: TextStyle(
                                  fontSize: 9,
                                  fontWeight: FontWeight.bold,
                                  color: soundboxState.isRegistered ? AppColors.onTertiaryContainer : Colors.orange.shade900,
                                ),
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 4),
                        Text(
                          "Verified Broadcasts: ₹${totalAnnounced.toStringAsFixed(2)} (${soundboxState.events.length} events)",
                          style: const TextStyle(fontSize: 13, color: AppColors.onSurfaceVariant),
                        ),
                        if (soundboxState.lastAnnouncedText != null) ...[
                          const SizedBox(height: 4),
                          Text(
                            '🎙️ "${soundboxState.lastAnnouncedText}"',
                            style: TextStyle(fontSize: 11, fontStyle: FontStyle.italic, color: Colors.blue.shade900),
                          ),
                        ],
                      ],
                    ),
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
                  "Recent Verified Soundbox Broadcasts",
                  style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: AppColors.onSurface),
                ),
                Text(
                  "${soundboxState.events.length} Events",
                  style: const TextStyle(fontSize: 12, color: AppColors.outline),
                ),
              ],
            ),
            const SizedBox(height: 12),

            if (soundboxState.events.isEmpty)
              _buildEmptyState()
            else
              ...soundboxState.events.map((event) => _buildEventCard(event)),
          ],
        ),
      ),
    );
  }

  Widget _buildEventCard(SoundEventModel event) {
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: AppColors.surfaceLowest,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: AppColors.outlineVariant.withValues(alpha: 0.3)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          Container(
            padding: const EdgeInsets.all(10),
            decoration: BoxDecoration(
              color: AppColors.tertiaryContainer,
              shape: BoxShape.circle,
            ),
            child: const Icon(Icons.check, color: AppColors.tertiary, size: 20),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Text(
                      "₹${event.amountInr.toStringAsFixed(2)}",
                      style: const TextStyle(
                        fontSize: 18,
                        fontWeight: FontWeight.w800,
                        color: AppColors.onSurface,
                      ),
                    ),
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                      decoration: BoxDecoration(
                        color: AppColors.tertiaryContainer,
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: const Text(
                        "PAYTM VERIFIED",
                        style: TextStyle(fontSize: 9, fontWeight: FontWeight.bold, color: AppColors.onTertiaryContainer),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 4),
                Text(
                  "Source: ${event.sourceType} • Txn: ${event.paymentId}",
                  style: const TextStyle(fontSize: 12, color: AppColors.onSurfaceVariant),
                ),
                const SizedBox(height: 2),
                Text(
                  "Verified at: ${event.verifiedAt}",
                  style: const TextStyle(fontSize: 10, color: AppColors.outline),
                ),
              ],
            ),
          ),
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
          Icon(Icons.speaker_notes_off_outlined, size: 48, color: Colors.grey.shade400),
          const SizedBox(height: 12),
          const Text(
            "Waiting for incoming Soundbox events",
            style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16),
          ),
          const SizedBox(height: 4),
          const Text(
            "When a customer pays via UPI QR, Counter bill, or Khata payment link, the 4G Soundbox will broadcast the amount aloud and log it here.",
            textAlign: TextAlign.center,
            style: TextStyle(color: AppColors.outline, fontSize: 12),
          ),
        ],
      ),
    );
  }
}
