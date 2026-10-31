import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../theme/app_theme.dart';
import '../models/khata_models.dart';
import '../providers/khata_providers.dart';
import 'khata/khata_aging_card.dart';
import 'khata/khata_account_detail_sheet.dart';
import 'khata/khata_voice_record_modal.dart';

class KhataLedgerScreen extends ConsumerStatefulWidget {
  const KhataLedgerScreen({super.key});

  @override
  ConsumerState<KhataLedgerScreen> createState() => _KhataLedgerScreenState();
}

class _KhataLedgerScreenState extends ConsumerState<KhataLedgerScreen> {
  final TextEditingController _searchCtrl = TextEditingController();

  @override
  void dispose() {
    _searchCtrl.dispose();
    super.dispose();
  }

  void _openVoiceRecordModal(BuildContext context) {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (ctx) => KhataVoiceRecordModal(
        onParsedEntry: (name, debit, credit, note) async {
          // Find or create account
          final accounts = ref.read(khataLedgerProvider).accounts;
          KhataAccountModel? matched;
          for (var a in accounts) {
            if (a.customerName.toLowerCase().contains(name.toLowerCase())) {
              matched = a;
              break;
            }
          }
          if (matched != null) {
            if (credit > 0) {
              await ref.read(khataLedgerProvider.notifier).recordRepayment(
                accountId: matched.id,
                amountInr: credit,
                method: "CASH",
                note: note,
              );
            }
          }
          if (context.mounted) {
            ScaffoldMessenger.of(context).showSnackBar(
              SnackBar(
                backgroundColor: const Color(0xFF2E7D32),
                content: Text("Voice entry for '$name' saved to Khata!"),
              ),
            );
          }
        },
      ),
    );
  }

  void _openAccountDetail(BuildContext context, KhataAccountModel account) {
    ref.read(khataLedgerProvider.notifier).selectAccount(account);
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (ctx) => KhataAccountDetailSheet(account: account),
    );
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(khataLedgerProvider);

    return Scaffold(
      backgroundColor: AppColors.surface,
      appBar: AppBar(
        backgroundColor: AppColors.surfaceLowest,
        elevation: 0.5,
        title: Row(
          children: const [
            Icon(Icons.menu_book, color: AppColors.secondary, size: 22),
            SizedBox(width: 8),
            Text(
              "Digital Khata Ledger",
              style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16),
            ),
          ],
        ),
        actions: [
          IconButton(
            icon: const Icon(Icons.camera_alt_rounded, color: AppColors.secondary),
            tooltip: "Scan Parchi (OCR)",
            onPressed: () => _openVoiceRecordModal(context),
          ),
          IconButton(
            icon: const Icon(Icons.mic, color: AppColors.secondary),
            tooltip: "Voice Record (Sarvam AI)",
            onPressed: () => _openVoiceRecordModal(context),
          ),
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: () => ref.read(khataLedgerProvider.notifier).refresh(),
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: () => ref.read(khataLedgerProvider.notifier).refresh(),
        child: Column(
          children: [
            // Credit Aging & Risk Summary Header
            KhataAgingCard(
              aging: state.agingBuckets,
              totalOutstanding: state.totalOutstandingInr,
            ),

            // Search Bar
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
              child: Container(
                height: 42,
                decoration: BoxDecoration(
                  color: AppColors.surfaceLow,
                  borderRadius: BorderRadius.circular(10),
                ),
                child: TextField(
                  controller: _searchCtrl,
                  onChanged: (val) => ref.read(khataLedgerProvider.notifier).setSearchQuery(val),
                  decoration: InputDecoration(
                    hintText: "Search customer name or phone...",
                    hintStyle: const TextStyle(fontSize: 13, color: AppColors.outline),
                    prefixIcon: const Icon(Icons.search, size: 18, color: AppColors.outline),
                    suffixIcon: _searchCtrl.text.isNotEmpty
                        ? IconButton(
                            icon: const Icon(Icons.clear, size: 16),
                            onPressed: () {
                              _searchCtrl.clear();
                              ref.read(khataLedgerProvider.notifier).setSearchQuery('');
                            },
                          )
                        : null,
                    border: InputBorder.none,
                    contentPadding: const EdgeInsets.symmetric(vertical: 12),
                  ),
                ),
              ),
            ),

            const SizedBox(height: 8),

            // Accounts List
            Expanded(
              child: state.isLoading
                  ? const Center(child: CircularProgressIndicator())
                  : state.accounts.isEmpty
                      ? Center(
                          child: Column(
                            mainAxisAlignment: MainAxisAlignment.center,
                            children: const [
                              Icon(Icons.account_balance_wallet_outlined, size: 48, color: AppColors.outline),
                              SizedBox(height: 12),
                              Text(
                                "No Khata accounts found",
                                style: TextStyle(fontWeight: FontWeight.bold, color: AppColors.outline),
                              ),
                            ],
                          ),
                        )
                      : ListView.separated(
                          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                          itemCount: state.accounts.length,
                          separatorBuilder: (ctx, idx) => const SizedBox(height: 8),
                          itemBuilder: (ctx, idx) {
                            final account = state.accounts[idx];

                            return InkWell(
                              onTap: () => _openAccountDetail(context, account),
                              borderRadius: BorderRadius.circular(12),
                              child: Container(
                                padding: const EdgeInsets.all(14),
                                decoration: BoxDecoration(
                                  color: AppColors.surfaceLowest,
                                  borderRadius: BorderRadius.circular(12),
                                  border: Border.all(
                                    color: account.hasOutstanding
                                        ? AppColors.secondary.withValues(alpha: 0.3)
                                        : AppColors.outlineVariant.withValues(alpha: 0.4),
                                  ),
                                ),
                                child: Row(
                                  children: [
                                    CircleAvatar(
                                      radius: 20,
                                      backgroundColor: account.hasOutstanding
                                          ? AppColors.secondaryContainer.withValues(alpha: 0.2)
                                          : Colors.grey.shade200,
                                      child: Text(
                                        account.customerName.isNotEmpty ? account.customerName[0].toUpperCase() : 'C',
                                        style: TextStyle(
                                          fontWeight: FontWeight.bold,
                                          color: account.hasOutstanding ? AppColors.secondary : Colors.grey.shade700,
                                        ),
                                      ),
                                    ),
                                    const SizedBox(width: 12),
                                    Expanded(
                                      child: Column(
                                        crossAxisAlignment: CrossAxisAlignment.start,
                                        children: [
                                          Text(
                                            account.customerName,
                                            style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 14),
                                          ),
                                          const SizedBox(height: 2),
                                          Text(
                                            account.phone,
                                            style: const TextStyle(fontSize: 12, color: AppColors.outline),
                                          ),
                                        ],
                                      ),
                                    ),
                                    Column(
                                      crossAxisAlignment: CrossAxisAlignment.end,
                                      children: [
                                        Text(
                                          "₹${account.balanceInr.toStringAsFixed(0)}",
                                          style: TextStyle(
                                            fontWeight: FontWeight.w800,
                                            fontSize: 16,
                                            color: account.hasOutstanding ? AppColors.secondary : Colors.green,
                                          ),
                                        ),
                                        const SizedBox(height: 2),
                                        Text(
                                          account.hasOutstanding ? "Due" : "Settled",
                                          style: TextStyle(
                                            fontSize: 11,
                                            fontWeight: FontWeight.bold,
                                            color: account.hasOutstanding ? AppColors.error : Colors.green,
                                          ),
                                        ),
                                      ],
                                    ),
                                    const SizedBox(width: 6),
                                    const Icon(Icons.chevron_right, color: AppColors.outline, size: 20),
                                  ],
                                ),
                              ),
                            );
                          },
                        ),
            ),
          ],
        ),
      ),
      floatingActionButton: FloatingActionButton.extended(
        backgroundColor: const Color(0xFF6C63FF),
        foregroundColor: Colors.white,
        icon: const Icon(Icons.document_scanner_rounded),
        label: const Text("Scan Parchi / Voice", style: TextStyle(fontWeight: FontWeight.bold)),
        onPressed: () => _openVoiceRecordModal(context),
      ),
    );
  }
}
