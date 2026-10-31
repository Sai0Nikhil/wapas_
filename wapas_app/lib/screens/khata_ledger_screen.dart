import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../theme/app_theme.dart';
import '../models/khata_models.dart';
import '../providers/khata_providers.dart';
import 'khata/khata_aging_card.dart';
import 'khata/khata_account_detail_sheet.dart';
import 'khata/khata_voice_record_modal.dart';
import 'khata/khata_manual_entry_dialog.dart';

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

  void _openManualEntryDialog(BuildContext context, {KhataAccountModel? account, String initialType = "CREDIT_GIVEN"}) {
    final accounts = ref.read(khataLedgerProvider).accounts;
    showDialog(
      context: context,
      builder: (ctx) => KhataManualEntryDialog(
        preselectedAccount: account,
        existingAccounts: accounts,
        initialType: initialType,
        onSubmit: ({
          String? accountId,
          String? customerName,
          String? customerPhone,
          required String entryType,
          required double amountInr,
          String note = '',
          String paymentMethod = 'CASH',
        }) async {
          final ok = await ref.read(khataLedgerProvider.notifier).addManualEntry(
            accountId: accountId,
            customerName: customerName,
            customerPhone: customerPhone,
            entryType: entryType,
            amountInr: amountInr,
            note: note,
            paymentMethod: paymentMethod,
          );
          if (context.mounted && ok) {
            final isUdhaar = entryType == "CREDIT_GIVEN";
            ScaffoldMessenger.of(context).showSnackBar(
              SnackBar(
                backgroundColor: isUdhaar ? const Color(0xFFD32F2F) : const Color(0xFF2E7D32),
                content: Text(
                  "${isUdhaar ? 'Udhaar' : 'Payment'} of ₹${amountInr.toStringAsFixed(0)} for '${customerName ?? 'Customer'}' saved!",
                ),
              ),
            );
          }
          return ok;
        },
      ),
    );
  }

  void _openVoiceRecordModal(BuildContext context) {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (ctx) => KhataVoiceRecordModal(
        onParsedEntry: (name, debit, credit, note) async {
          final isDebit = debit > 0;
          final amount = isDebit ? debit : credit;
          if (amount <= 0) return;

          final ok = await ref.read(khataLedgerProvider.notifier).addManualEntry(
            customerName: name,
            entryType: isDebit ? "CREDIT_GIVEN" : "REPAYMENT",
            amountInr: amount,
            note: note,
          );

          if (context.mounted && ok) {
            ScaffoldMessenger.of(context).showSnackBar(
              SnackBar(
                backgroundColor: isDebit ? const Color(0xFFD32F2F) : const Color(0xFF2E7D32),
                content: Text(
                  "AI Entry: ₹${amount.toStringAsFixed(0)} ${isDebit ? 'Udhaar' : 'Jama'} for '$name' saved to Khata!",
                ),
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
      builder: (ctx) => KhataAccountDetailSheet(
        account: account,
        onAddUdhaar: () => _openManualEntryDialog(context, account: account, initialType: "CREDIT_GIVEN"),
      ),
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
            icon: const Icon(Icons.person_add_alt_1_rounded, color: AppColors.secondary),
            tooltip: "Add Manual Entry / Customer",
            onPressed: () => _openManualEntryDialog(context),
          ),
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
                            children: [
                              const Icon(Icons.account_balance_wallet_outlined, size: 48, color: AppColors.outline),
                              const SizedBox(height: 12),
                              const Text(
                                "No Khata accounts found",
                                style: TextStyle(fontWeight: FontWeight.bold, color: AppColors.outline),
                              ),
                              const SizedBox(height: 16),
                              ElevatedButton.icon(
                                style: ElevatedButton.styleFrom(
                                  backgroundColor: const Color(0xFF0051D5),
                                  foregroundColor: Colors.white,
                                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                                ),
                                icon: const Icon(Icons.add, size: 18),
                                label: const Text("Add First Khata Entry"),
                                onPressed: () => _openManualEntryDialog(context),
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
                                            account.phone.isNotEmpty ? account.phone : "Customer",
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
      floatingActionButton: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          FloatingActionButton.extended(
            heroTag: "fab_manual_entry",
            backgroundColor: const Color(0xFF0051D5),
            foregroundColor: Colors.white,
            elevation: 3,
            icon: const Icon(Icons.add, size: 20),
            label: const Text("Add Entry", style: TextStyle(fontWeight: FontWeight.bold)),
            onPressed: () => _openManualEntryDialog(context),
          ),
          const SizedBox(width: 10),
          FloatingActionButton.extended(
            heroTag: "fab_voice_parchi",
            backgroundColor: const Color(0xFF6C63FF),
            foregroundColor: Colors.white,
            elevation: 3,
            icon: const Icon(Icons.document_scanner_rounded, size: 18),
            label: const Text("Scan / Voice", style: TextStyle(fontWeight: FontWeight.bold)),
            onPressed: () => _openVoiceRecordModal(context),
          ),
        ],
      ),
    );
  }
}
