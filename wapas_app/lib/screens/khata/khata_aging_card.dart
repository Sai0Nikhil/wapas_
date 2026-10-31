import 'package:flutter/material.dart';
import '../../models/khata_models.dart';
import '../../theme/app_theme.dart';

class KhataAgingCard extends StatelessWidget {
  final AgingBucketsModel? aging;
  final double totalOutstanding;

  const KhataAgingCard({
    super.key,
    required this.aging,
    required this.totalOutstanding,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.all(12),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppColors.surfaceLowest,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: AppColors.outlineVariant.withValues(alpha: 0.5)),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.03),
            blurRadius: 8,
            offset: const Offset(0, 2),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Row(
                children: const [
                  Icon(Icons.query_builder, color: AppColors.secondary, size: 20),
                  SizedBox(width: 8),
                  Text(
                    "Credit Aging & Risk Buckets",
                    style: TextStyle(fontWeight: FontWeight.bold, fontSize: 14),
                  ),
                ],
              ),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                decoration: BoxDecoration(
                  color: AppColors.secondaryContainer.withValues(alpha: 0.15),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Text(
                  "Total: ₹${totalOutstanding.toStringAsFixed(0)}",
                  style: const TextStyle(
                    fontSize: 12,
                    fontWeight: FontWeight.w800,
                    color: AppColors.secondary,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 14),
          Row(
            children: [
              _buildBucketItem("0-30 Days", (aging?.zeroToThirty ?? 0) / 100.0, Colors.green),
              _buildBucketItem("31-60 Days", (aging?.thirtyOneToSixty ?? 0) / 100.0, Colors.amber.shade800),
              _buildBucketItem("61-90 Days", (aging?.sixtyOneToNinety ?? 0) / 100.0, Colors.orange.shade900),
              _buildBucketItem("90+ Days", (aging?.ninetyPlus ?? 0) / 100.0, Colors.red.shade700),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildBucketItem(String label, double amount, Color color) {
    return Expanded(
      child: Container(
        margin: const EdgeInsets.symmetric(horizontal: 3),
        padding: const EdgeInsets.symmetric(vertical: 8, horizontal: 6),
        decoration: BoxDecoration(
          color: color.withValues(alpha: 0.08),
          borderRadius: BorderRadius.circular(8),
          border: Border.all(color: color.withValues(alpha: 0.3)),
        ),
        child: Column(
          children: [
            Text(
              label,
              style: TextStyle(fontSize: 10, fontWeight: FontWeight.bold, color: color),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 4),
            Text(
              "₹${amount.toStringAsFixed(0)}",
              style: TextStyle(fontSize: 12, fontWeight: FontWeight.w800, color: color),
              textAlign: TextAlign.center,
            ),
          ],
        ),
      ),
    );
  }
}
