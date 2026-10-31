import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../../models/khata_models.dart';
import '../../theme/app_theme.dart';

class KhataManualEntryDialog extends StatefulWidget {
  final KhataAccountModel? preselectedAccount;
  final List<KhataAccountModel> existingAccounts;
  final String initialType; // "CREDIT_GIVEN" or "REPAYMENT"
  final Future<bool> Function({
    String? accountId,
    String? customerName,
    String? customerPhone,
    required String entryType,
    required double amountInr,
    String note,
    String paymentMethod,
  }) onSubmit;

  const KhataManualEntryDialog({
    super.key,
    this.preselectedAccount,
    this.existingAccounts = const [],
    this.initialType = "CREDIT_GIVEN",
    required this.onSubmit,
  });

  @override
  State<KhataManualEntryDialog> createState() => _KhataManualEntryDialogState();
}

class _KhataManualEntryDialogState extends State<KhataManualEntryDialog> {
  late String _entryType; // "CREDIT_GIVEN" (Udhaar) vs "REPAYMENT" (Jama)
  bool _isNewCustomer = false;
  KhataAccountModel? _selectedAccount;

  final TextEditingController _nameController = TextEditingController();
  final TextEditingController _phoneController = TextEditingController();
  final TextEditingController _amountController = TextEditingController();
  final TextEditingController _noteController = TextEditingController();

  String _paymentMethod = "CASH";
  bool _isSubmitting = false;

  @override
  void initState() {
    super.initState();
    _entryType = widget.initialType;
    if (widget.preselectedAccount != null) {
      _selectedAccount = widget.preselectedAccount;
      _isNewCustomer = false;
    } else if (widget.existingAccounts.isNotEmpty) {
      _selectedAccount = widget.existingAccounts.first;
      _isNewCustomer = false;
    } else {
      _isNewCustomer = true;
    }
  }

  @override
  void dispose() {
    _nameController.dispose();
    _phoneController.dispose();
    _amountController.dispose();
    _noteController.dispose();
    super.dispose();
  }

  void _addAmount(double add) {
    final current = double.tryParse(_amountController.text.trim()) ?? 0.0;
    final updated = current + add;
    _amountController.text = updated.toStringAsFixed(0);
    setState(() {});
  }

  @override
  Widget build(BuildContext context) {
    final isUdhaar = _entryType == "CREDIT_GIVEN";
    final activeColor = isUdhaar ? const Color(0xFFD32F2F) : const Color(0xFF2E7D32);

    return Dialog(
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
      insetPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 24),
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 480),
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(20),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              // Header
              Row(
                children: [
                  Container(
                    padding: const EdgeInsets.all(8),
                    decoration: BoxDecoration(
                      color: activeColor.withValues(alpha: 0.12),
                      shape: BoxShape.circle,
                    ),
                    child: Icon(
                      isUdhaar ? Icons.call_made_rounded : Icons.call_received_rounded,
                      color: activeColor,
                      size: 22,
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Text(
                          "Manual Khata Entry",
                          style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
                        ),
                        Text(
                          isUdhaar ? "Udhaar Diya (Customer Debt Increases)" : "Jama Mila (Customer Debt Decreases)",
                          style: TextStyle(fontSize: 11, color: activeColor, fontWeight: FontWeight.w600),
                        ),
                      ],
                    ),
                  ),
                  IconButton(
                    icon: const Icon(Icons.close, size: 20),
                    onPressed: () => Navigator.of(context).pop(),
                  ),
                ],
              ),

              const SizedBox(height: 16),

              // Segmented Udhaar vs Jama Toggle
              Container(
                decoration: BoxDecoration(
                  color: Colors.grey.shade100,
                  borderRadius: BorderRadius.circular(12),
                ),
                padding: const EdgeInsets.all(4),
                child: Row(
                  children: [
                    Expanded(
                      child: GestureDetector(
                        onTap: () => setState(() => _entryType = "CREDIT_GIVEN"),
                        child: AnimatedContainer(
                          duration: const Duration(milliseconds: 180),
                          padding: const EdgeInsets.symmetric(vertical: 10),
                          decoration: BoxDecoration(
                            color: isUdhaar ? const Color(0xFFD32F2F) : Colors.transparent,
                            borderRadius: BorderRadius.circular(8),
                          ),
                          alignment: Alignment.center,
                          child: Row(
                            mainAxisAlignment: MainAxisAlignment.center,
                            children: [
                              Icon(
                                Icons.arrow_upward_rounded,
                                size: 16,
                                color: isUdhaar ? Colors.white : Colors.grey.shade700,
                              ),
                              const SizedBox(width: 4),
                              Text(
                                "Udhaar Diya (Gave)",
                                style: TextStyle(
                                  fontSize: 12,
                                  fontWeight: FontWeight.bold,
                                  color: isUdhaar ? Colors.white : Colors.grey.shade800,
                                ),
                              ),
                            ],
                          ),
                        ),
                      ),
                    ),
                    Expanded(
                      child: GestureDetector(
                        onTap: () => setState(() => _entryType = "REPAYMENT"),
                        child: AnimatedContainer(
                          duration: const Duration(milliseconds: 180),
                          padding: const EdgeInsets.symmetric(vertical: 10),
                          decoration: BoxDecoration(
                            color: !isUdhaar ? const Color(0xFF2E7D32) : Colors.transparent,
                            borderRadius: BorderRadius.circular(8),
                          ),
                          alignment: Alignment.center,
                          child: Row(
                            mainAxisAlignment: MainAxisAlignment.center,
                            children: [
                              Icon(
                                Icons.arrow_downward_rounded,
                                size: 16,
                                color: !isUdhaar ? Colors.white : Colors.grey.shade700,
                              ),
                              const SizedBox(width: 4),
                              Text(
                                "Jama Mila (Got)",
                                style: TextStyle(
                                  fontSize: 12,
                                  fontWeight: FontWeight.bold,
                                  color: !isUdhaar ? Colors.white : Colors.grey.shade800,
                                ),
                              ),
                            ],
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
              ),

              const SizedBox(height: 16),

              // Customer Selection
              if (widget.preselectedAccount != null)
                Container(
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: AppColors.surfaceLow,
                    borderRadius: BorderRadius.circular(10),
                    border: Border.all(color: AppColors.outlineVariant),
                  ),
                  child: Row(
                    children: [
                      CircleAvatar(
                        radius: 18,
                        backgroundColor: activeColor.withValues(alpha: 0.15),
                        child: Text(
                          widget.preselectedAccount!.customerName.isNotEmpty
                              ? widget.preselectedAccount!.customerName[0].toUpperCase()
                              : 'C',
                          style: TextStyle(fontWeight: FontWeight.bold, color: activeColor),
                        ),
                      ),
                      const SizedBox(width: 10),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              widget.preselectedAccount!.customerName,
                              style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 13),
                            ),
                            Text(
                              widget.preselectedAccount!.phone.isNotEmpty
                                  ? widget.preselectedAccount!.phone
                                  : "Existing Customer",
                              style: const TextStyle(fontSize: 11, color: AppColors.outline),
                            ),
                          ],
                        ),
                      ),
                      Column(
                        crossAxisAlignment: CrossAxisAlignment.end,
                        children: [
                          const Text("Due", style: TextStyle(fontSize: 10, color: AppColors.outline)),
                          Text(
                            "₹${widget.preselectedAccount!.balanceInr.toStringAsFixed(0)}",
                            style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 13),
                          ),
                        ],
                      ),
                    ],
                  ),
                )
              else ...[
                // Tabs: Existing vs New Customer
                Row(
                  children: [
                    Expanded(
                      child: ChoiceChip(
                        label: const Center(child: Text("Existing Customer")),
                        selected: !_isNewCustomer,
                        onSelected: (val) {
                          if (val) setState(() => _isNewCustomer = false);
                        },
                      ),
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: ChoiceChip(
                        label: const Center(child: Text("+ New Customer")),
                        selected: _isNewCustomer,
                        onSelected: (val) {
                          if (val) setState(() => _isNewCustomer = true);
                        },
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 10),

                if (!_isNewCustomer && widget.existingAccounts.isNotEmpty)
                  DropdownButtonFormField<KhataAccountModel>(
                    initialValue: _selectedAccount,
                    decoration: const InputDecoration(
                      labelText: "Select Customer",
                      border: OutlineInputBorder(),
                      contentPadding: EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                    ),
                    items: widget.existingAccounts.map((acc) {
                      return DropdownMenuItem<KhataAccountModel>(
                        value: acc,
                        child: Text(
                          "${acc.customerName} (${acc.phone.isNotEmpty ? acc.phone : 'No phone'}) · Due: ₹${acc.balanceInr.toStringAsFixed(0)}",
                          style: const TextStyle(fontSize: 13),
                          overflow: TextOverflow.ellipsis,
                        ),
                      );
                    }).toList(),
                    onChanged: (acc) => setState(() => _selectedAccount = acc),
                  )
                else ...[
                  TextField(
                    controller: _nameController,
                    decoration: const InputDecoration(
                      labelText: "Customer Name *",
                      hintText: "e.g. Ramesh Kumar",
                      prefixIcon: Icon(Icons.person_outline, size: 20),
                      border: OutlineInputBorder(),
                      contentPadding: EdgeInsets.symmetric(horizontal: 12, vertical: 12),
                    ),
                  ),
                  const SizedBox(height: 10),
                  TextField(
                    controller: _phoneController,
                    keyboardType: TextInputType.phone,
                    inputFormatters: [FilteringTextInputFormatter.digitsOnly, LengthLimitingTextInputFormatter(10)],
                    decoration: const InputDecoration(
                      labelText: "10-Digit Mobile Number (Optional)",
                      hintText: "e.g. 9876543210",
                      prefixIcon: Icon(Icons.phone_outlined, size: 20),
                      border: OutlineInputBorder(),
                      contentPadding: EdgeInsets.symmetric(horizontal: 12, vertical: 12),
                    ),
                  ),
                ],
              ],

              const SizedBox(height: 14),

              // Amount Field
              TextField(
                controller: _amountController,
                keyboardType: TextInputType.number,
                autofocus: widget.preselectedAccount != null,
                style: const TextStyle(fontSize: 22, fontWeight: FontWeight.bold),
                decoration: InputDecoration(
                  labelText: "Amount (₹) *",
                  labelStyle: const TextStyle(fontSize: 14, fontWeight: FontWeight.normal),
                  prefixIcon: const Icon(Icons.currency_rupee, size: 22),
                  border: const OutlineInputBorder(),
                  focusedBorder: OutlineInputBorder(
                    borderSide: BorderSide(color: activeColor, width: 2),
                  ),
                ),
              ),

              const SizedBox(height: 8),

              // Quick Preset Amount Chips
              Wrap(
                spacing: 6,
                runSpacing: 4,
                children: [
                  _presetChip("+₹100", 100),
                  _presetChip("+₹200", 200),
                  _presetChip("+₹500", 500),
                  _presetChip("+₹1,000", 1000),
                  _presetChip("+₹2,000", 2000),
                ],
              ),

              const SizedBox(height: 12),

              // Note Field
              TextField(
                controller: _noteController,
                decoration: InputDecoration(
                  labelText: isUdhaar ? "Items / Note (Optional)" : "Note (Optional)",
                  hintText: isUdhaar ? "e.g. 2 bags Atta + 1L Oil" : "e.g. Cleared Diwali balance",
                  prefixIcon: const Icon(Icons.edit_note, size: 20),
                  border: const OutlineInputBorder(),
                  contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                ),
              ),

              const SizedBox(height: 12),

              // Payment Method (for Jama or Udhaar basis)
              Row(
                children: [
                  const Text("Mode: ", style: TextStyle(fontWeight: FontWeight.bold, fontSize: 12)),
                  const SizedBox(width: 8),
                  ChoiceChip(
                    label: const Text("CASH", style: TextStyle(fontSize: 11)),
                    selected: _paymentMethod == "CASH",
                    onSelected: (val) => setState(() => _paymentMethod = "CASH"),
                  ),
                  const SizedBox(width: 6),
                  ChoiceChip(
                    label: const Text("UPI", style: TextStyle(fontSize: 11)),
                    selected: _paymentMethod == "UPI",
                    onSelected: (val) => setState(() => _paymentMethod = "UPI"),
                  ),
                  const SizedBox(width: 6),
                  ChoiceChip(
                    label: const Text("OTHER", style: TextStyle(fontSize: 11)),
                    selected: _paymentMethod == "OTHER",
                    onSelected: (val) => setState(() => _paymentMethod = "OTHER"),
                  ),
                ],
              ),

              const SizedBox(height: 20),

              // Submit & Cancel Buttons
              Row(
                children: [
                  Expanded(
                    child: OutlinedButton(
                      style: OutlinedButton.styleFrom(
                        padding: const EdgeInsets.symmetric(vertical: 13),
                        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                      ),
                      onPressed: _isSubmitting ? null : () => Navigator.of(context).pop(),
                      child: const Text("Cancel"),
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    flex: 2,
                    child: ElevatedButton(
                      style: ElevatedButton.styleFrom(
                        backgroundColor: activeColor,
                        foregroundColor: Colors.white,
                        padding: const EdgeInsets.symmetric(vertical: 13),
                        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                      ),
                      onPressed: _isSubmitting ? null : _submit,
                      child: _isSubmitting
                          ? const SizedBox(
                              width: 18,
                              height: 18,
                              child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                            )
                          : Text(
                              isUdhaar ? "SAVE UDHAAR" : "SAVE PAYMENT",
                              style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 13),
                            ),
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _presetChip(String label, double val) {
    return ActionChip(
      label: Text(label, style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w600)),
      padding: EdgeInsets.zero,
      visualDensity: VisualDensity.compact,
      onPressed: () => _addAmount(val),
    );
  }

  Future<void> _submit() async {
    final amt = double.tryParse(_amountController.text.trim()) ?? 0.0;
    if (amt <= 0) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text("Please enter a valid amount greater than ₹0")),
      );
      return;
    }

    String? accountId;
    String? customerName;
    String? customerPhone;

    if (widget.preselectedAccount != null) {
      accountId = widget.preselectedAccount!.id;
      customerName = widget.preselectedAccount!.customerName;
      customerPhone = widget.preselectedAccount!.phone;
    } else if (!_isNewCustomer && _selectedAccount != null) {
      accountId = _selectedAccount!.id;
      customerName = _selectedAccount!.customerName;
      customerPhone = _selectedAccount!.phone;
    } else {
      customerName = _nameController.text.trim();
      customerPhone = _phoneController.text.trim();
      if (customerName.isEmpty) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text("Please enter customer name")),
        );
        return;
      }
    }

    setState(() => _isSubmitting = true);
    final nav = Navigator.of(context);

    final ok = await widget.onSubmit(
      accountId: accountId,
      customerName: customerName,
      customerPhone: customerPhone,
      entryType: _entryType,
      amountInr: amt,
      note: _noteController.text.trim(),
      paymentMethod: _paymentMethod,
    );

    if (!mounted) return;
    setState(() => _isSubmitting = false);

    if (ok) {
      nav.pop();
    }
  }
}
