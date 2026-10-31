import 'package:flutter/material.dart';
import '../../models/khata_models.dart';
import '../../theme/app_theme.dart';

class KhataRepaymentDialog extends StatefulWidget {
  final KhataAccountModel account;
  final Future<bool> Function({
    required String accountId,
    required double amountInr,
    required String method,
    String note,
  }) onConfirm;

  const KhataRepaymentDialog({
    super.key,
    required this.account,
    required this.onConfirm,
  });

  @override
  State<KhataRepaymentDialog> createState() => _KhataRepaymentDialogState();
}

class _KhataRepaymentDialogState extends State<KhataRepaymentDialog> {
  late final TextEditingController _amountController;
  final TextEditingController _noteController = TextEditingController();
  String _selectedMethod = "CASH";
  bool _confirmReceived = true;
  bool _isSubmitting = false;

  @override
  void initState() {
    super.initState();
    _amountController = TextEditingController(text: widget.account.balanceInr.toStringAsFixed(0));
  }

  @override
  void dispose() {
    _amountController.dispose();
    _noteController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      title: Row(
        children: const [
          Icon(Icons.payments_outlined, color: Colors.green),
          SizedBox(width: 8),
          Text("Record Repayment", style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
        ],
      ),
      content: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              "Customer: ${widget.account.customerName} (${widget.account.phone})",
              style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 13),
            ),
            Text(
              "Total Outstanding: ₹${widget.account.balanceInr.toStringAsFixed(2)}",
              style: const TextStyle(fontSize: 12, color: AppColors.secondary),
            ),
            const SizedBox(height: 16),
            TextField(
              controller: _amountController,
              keyboardType: TextInputType.number,
              decoration: const InputDecoration(
                labelText: "Repayment Amount (₹)",
                border: OutlineInputBorder(),
                prefixIcon: Icon(Icons.currency_rupee, size: 18),
              ),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: _noteController,
              decoration: const InputDecoration(
                labelText: "Note (Optional)",
                hintText: "e.g. Cleared Diwali debt",
                border: OutlineInputBorder(),
              ),
            ),
            const SizedBox(height: 12),
            const Text("Payment Method:", style: TextStyle(fontWeight: FontWeight.bold, fontSize: 12)),
            const SizedBox(height: 4),
            Row(
              children: [
                ChoiceChip(
                  label: const Text("CASH"),
                  selected: _selectedMethod == "CASH",
                  onSelected: (val) => setState(() => _selectedMethod = "CASH"),
                ),
                const SizedBox(width: 8),
                ChoiceChip(
                  label: const Text("OTHER / UPI"),
                  selected: _selectedMethod == "OTHER",
                  onSelected: (val) => setState(() => _selectedMethod = "OTHER"),
                ),
              ],
            ),
            const SizedBox(height: 8),
            CheckboxListTile(
              contentPadding: EdgeInsets.zero,
              title: const Text("I confirm payment was received", style: TextStyle(fontSize: 12)),
              value: _confirmReceived,
              onChanged: (val) => setState(() => _confirmReceived = val ?? true),
              controlAffinity: ListTileControlAffinity.leading,
            ),
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: _isSubmitting ? null : () => Navigator.pop(context),
          child: const Text("Cancel"),
        ),
        ElevatedButton(
          style: ElevatedButton.styleFrom(
            backgroundColor: Colors.green,
            foregroundColor: Colors.white,
          ),
          onPressed: _isSubmitting || !_confirmReceived
              ? null
              : () async {
                  final amt = double.tryParse(_amountController.text) ?? 0.0;
                  if (amt <= 0) return;
                  setState(() => _isSubmitting = true);
                  final nav = Navigator.of(context);
                  final ok = await widget.onConfirm(
                    accountId: widget.account.id,
                    amountInr: amt,
                    method: _selectedMethod,
                    note: _noteController.text.trim(),
                  );
                  if (!mounted) return;
                  setState(() => _isSubmitting = false);
                  if (ok) nav.pop();
                },
          child: _isSubmitting
              ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
              : const Text("RECORD REPAYMENT"),
        ),
      ],
    );
  }
}
