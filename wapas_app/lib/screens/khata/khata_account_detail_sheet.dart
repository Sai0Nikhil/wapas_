import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:qr_flutter/qr_flutter.dart';
import '../../models/khata_models.dart';
import '../../providers/khata_providers.dart';
import '../../theme/app_theme.dart';
import 'khata_repayment_dialog.dart';

class KhataAccountDetailSheet extends ConsumerWidget {
  final KhataAccountModel account;

  const KhataAccountDetailSheet({
    super.key,
    required this.account,
  });

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(khataLedgerProvider);
    final entries = state.selectedAccountEntries;

    return Container(
      height: MediaQuery.of(context).size.height * 0.85,
      decoration: const BoxDecoration(
        color: AppColors.surfaceLowest,
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      child: Column(
        children: [
          // Drag handle
          Container(
            margin: const EdgeInsets.only(top: 10, bottom: 8),
            width: 40,
            height: 4,
            decoration: BoxDecoration(
              color: AppColors.outlineVariant,
              borderRadius: BorderRadius.circular(2),
            ),
          ),

          // Header
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 8),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      account.customerName,
                      style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      account.phone,
                      style: const TextStyle(fontSize: 13, color: AppColors.outline),
                    ),
                  ],
                ),
                Column(
                  crossAxisAlignment: CrossAxisAlignment.end,
                  children: [
                    const Text("Balance Due", style: TextStyle(fontSize: 11, color: AppColors.outline)),
                    Text(
                      "₹${account.balanceInr.toStringAsFixed(2)}",
                      style: const TextStyle(
                        fontSize: 20,
                        fontWeight: FontWeight.w800,
                        color: AppColors.secondary,
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),

          const Divider(),

          // Action buttons: Payment Link, Record Repayment, Statement CSV
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
            child: Row(
              children: [
                Expanded(
                  child: ElevatedButton.icon(
                    style: ElevatedButton.styleFrom(
                      backgroundColor: AppColors.secondary,
                      foregroundColor: Colors.white,
                      padding: const EdgeInsets.symmetric(vertical: 10),
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                    ),
                    icon: const Icon(Icons.qr_code, size: 16),
                    label: const Text("Pay Link", style: TextStyle(fontSize: 12, fontWeight: FontWeight.bold)),
                    onPressed: () => _showPaymentLinkModal(context, ref),
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: ElevatedButton.icon(
                    style: ElevatedButton.styleFrom(
                      backgroundColor: Colors.green,
                      foregroundColor: Colors.white,
                      padding: const EdgeInsets.symmetric(vertical: 10),
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                    ),
                    icon: const Icon(Icons.payments, size: 16),
                    label: const Text("Repay", style: TextStyle(fontSize: 12, fontWeight: FontWeight.bold)),
                    onPressed: () {
                      showDialog(
                        context: context,
                        builder: (ctx) => KhataRepaymentDialog(
                          account: account,
                          onConfirm: ref.read(khataLedgerProvider.notifier).recordRepayment,
                        ),
                      );
                    },
                  ),
                ),
                const SizedBox(width: 8),
                OutlinedButton.icon(
                  style: OutlinedButton.styleFrom(
                    foregroundColor: AppColors.onSurface,
                    padding: const EdgeInsets.symmetric(vertical: 10, horizontal: 12),
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                  ),
                  icon: const Icon(Icons.download, size: 16),
                  label: const Text("CSV", style: TextStyle(fontSize: 12)),
                  onPressed: () => _downloadCsvStatement(context, ref),
                ),
              ],
            ),
          ),

          const Divider(),

          // Entries Header
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 6),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text(
                  "Ledger History (${entries.length} entries)",
                  style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 13),
                ),
                if (state.isDetailLoading)
                  const SizedBox(width: 14, height: 14, child: CircularProgressIndicator(strokeWidth: 2)),
              ],
            ),
          ),

          // Entries List
          Expanded(
            child: entries.isEmpty
                ? const Center(
                    child: Text(
                      "No transactions recorded for this account.",
                      style: TextStyle(color: AppColors.outline),
                    ),
                  )
                : ListView.separated(
                    padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                    itemCount: entries.length,
                    separatorBuilder: (ctx, idx) => const SizedBox(height: 8),
                    itemBuilder: (ctx, idx) {
                      final e = entries[idx];
                      final isDebit = e.isDebit;

                      return Container(
                        padding: const EdgeInsets.all(12),
                        decoration: BoxDecoration(
                          color: e.isReversed
                              ? Colors.grey.shade100
                              : (isDebit ? const Color(0xFFFFF3E0) : const Color(0xFFE8F5E9)),
                          borderRadius: BorderRadius.circular(10),
                          border: Border.all(
                            color: e.isReversed
                                ? Colors.grey.shade400
                                : (isDebit ? Colors.orange.shade300 : Colors.green.shade300),
                          ),
                        ),
                        child: Row(
                          children: [
                            Icon(
                              e.isReversed
                                  ? Icons.undo
                                  : (isDebit ? Icons.arrow_upward : Icons.arrow_downward),
                              color: e.isReversed
                                  ? Colors.grey
                                  : (isDebit ? Colors.deepOrange : Colors.green),
                              size: 20,
                            ),
                            const SizedBox(width: 10),
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Row(
                                    children: [
                                      Text(
                                        isDebit ? "Credit Given (उधार)" : "Repayment Received (जमा)",
                                        style: TextStyle(
                                          fontWeight: FontWeight.bold,
                                          fontSize: 13,
                                          color: e.isReversed ? Colors.grey : AppColors.onSurface,
                                          decoration: e.isReversed ? TextDecoration.lineThrough : null,
                                        ),
                                      ),
                                      if (e.isReversed) ...[
                                        const SizedBox(width: 6),
                                        Container(
                                          padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 1),
                                          decoration: BoxDecoration(
                                            color: Colors.grey.shade300,
                                            borderRadius: BorderRadius.circular(4),
                                          ),
                                          child: const Text("REVERSED", style: TextStyle(fontSize: 9, fontWeight: FontWeight.bold)),
                                        ),
                                      ],
                                    ],
                                  ),
                                  if (e.note.isNotEmpty)
                                    Text(
                                      e.note,
                                      style: const TextStyle(fontSize: 11, color: AppColors.outline),
                                    ),
                                  Text(
                                    "Balance After: ₹${e.balanceAfterInr.toStringAsFixed(2)}",
                                    style: const TextStyle(fontSize: 11, color: AppColors.outline),
                                  ),
                                ],
                              ),
                            ),
                            Column(
                              crossAxisAlignment: CrossAxisAlignment.end,
                              children: [
                                Text(
                                  "${isDebit ? '+' : '-'}₹${e.amountInr.toStringAsFixed(2)}",
                                  style: TextStyle(
                                    fontWeight: FontWeight.w800,
                                    fontSize: 14,
                                    color: e.isReversed
                                        ? Colors.grey
                                        : (isDebit ? Colors.deepOrange : Colors.green),
                                  ),
                                ),
                                if (!e.isReversed)
                                  InkWell(
                                    onTap: () => _showReversePrompt(context, ref, e.id),
                                    child: const Padding(
                                      padding: EdgeInsets.only(top: 4),
                                      child: Text(
                                        "Reverse",
                                        style: TextStyle(fontSize: 11, color: AppColors.error, fontWeight: FontWeight.bold),
                                      ),
                                    ),
                                  ),
                              ],
                            ),
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

  void _showPaymentLinkModal(BuildContext context, WidgetRef ref) async {
    final res = await ref.read(khataLedgerProvider.notifier).generatePaymentLink(
      account.id,
      account.balanceInr,
    );

    if (!context.mounted) return;
    if (res == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text("Failed to generate payment link")),
      );
      return;
    }

    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        title: Row(
          children: const [
            Icon(Icons.qr_code_2, color: AppColors.secondary),
            SizedBox(width: 8),
            Text("Paytm Collection Link", style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
          ],
        ),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              "Share this link with ${account.customerName} for ₹${account.balanceInr.toStringAsFixed(2)}",
              style: const TextStyle(fontSize: 12, color: AppColors.outline),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 14),
            QrImageView(
              data: res.shortUrl.isNotEmpty ? res.shortUrl : "http://localhost:8000/pay/khata",
              version: QrVersions.auto,
              size: 160,
            ),
            const SizedBox(height: 12),
            SelectableText(
              res.shortUrl,
              style: const TextStyle(fontSize: 11, color: AppColors.secondary, fontWeight: FontWeight.bold),
            ),
          ],
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text("Close")),
          ElevatedButton.icon(
            style: ElevatedButton.styleFrom(backgroundColor: const Color(0xFF25D366), foregroundColor: Colors.white),
            icon: const Icon(Icons.share, size: 16),
            label: const Text("Copy & WhatsApp"),
            onPressed: () {
              Clipboard.setData(ClipboardData(
                text: "Namaste ${account.customerName}, please pay ₹${account.balanceInr.toStringAsFixed(0)} for your Kirana Khata bill: ${res.shortUrl}",
              ));
              Navigator.pop(ctx);
              ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(
                  backgroundColor: Color(0xFF25D366),
                  content: Text("WhatsApp reminder copied to clipboard!"),
                ),
              );
            },
          ),
        ],
      ),
    );
  }

  void _showReversePrompt(BuildContext context, WidgetRef ref, String entryId) {
    final reasonCtrl = TextEditingController(text: "Wrong entry by mistake");

    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text("Reverse Transaction?", style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Text("This will append an immutable REVERSAL entry and restore the balance.", style: TextStyle(fontSize: 12, color: AppColors.outline)),
            const SizedBox(height: 12),
            TextField(
              controller: reasonCtrl,
              decoration: const InputDecoration(labelText: "Reason for reversal", border: OutlineInputBorder()),
            ),
          ],
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text("Cancel")),
          ElevatedButton(
            style: ElevatedButton.styleFrom(backgroundColor: AppColors.error, foregroundColor: Colors.white),
            onPressed: () async {
              Navigator.pop(ctx);
              final ok = await ref.read(khataLedgerProvider.notifier).reverseEntry(
                entryId,
                reasonCtrl.text.trim(),
              );
              if (ok && context.mounted) {
                ScaffoldMessenger.of(context).showSnackBar(
                  const SnackBar(backgroundColor: Color(0xFF2E7D32), content: Text("Transaction reversed successfully!")),
                );
              }
            },
            child: const Text("CONFIRM REVERSE"),
          ),
        ],
      ),
    );
  }

  void _downloadCsvStatement(BuildContext context, WidgetRef ref) async {
    final csv = await ref.read(khataLedgerProvider.notifier).downloadStatementCsv(account.id);
    if (!context.mounted) return;

    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        title: Row(
          children: const [
            Icon(Icons.table_chart_outlined, color: AppColors.secondary),
            SizedBox(width: 8),
            Text("Statement CSV Export", style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
          ],
        ),
        content: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                "Statement for ${account.customerName} (${account.phone}):",
                style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 12),
              ),
              const SizedBox(height: 8),
              Container(
                padding: const EdgeInsets.all(8),
                decoration: BoxDecoration(
                  color: AppColors.surfaceLow,
                  borderRadius: BorderRadius.circular(6),
                ),
                child: SelectableText(
                  csv.isNotEmpty ? csv : "Date,Entry ID,Type,Debit,Credit,Note\nNo transactions.",
                  style: const TextStyle(fontFamily: 'monospace', fontSize: 10),
                ),
              ),
            ],
          ),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text("Close")),
          ElevatedButton.icon(
            style: ElevatedButton.styleFrom(backgroundColor: AppColors.secondary, foregroundColor: Colors.white),
            icon: const Icon(Icons.copy, size: 16),
            label: const Text("Copy CSV"),
            onPressed: () {
              Clipboard.setData(ClipboardData(text: csv));
              Navigator.pop(ctx);
              ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(content: Text("CSV statement copied to clipboard!")),
              );
            },
          ),
        ],
      ),
    );
  }
}
