import 'package:flutter/material.dart';
import '../../theme/app_theme.dart';

class KhataVoiceRecordModal extends StatefulWidget {
  final Function(String name, double debit, double credit, String note) onParsedEntry;

  const KhataVoiceRecordModal({
    super.key,
    required this.onParsedEntry,
  });

  @override
  State<KhataVoiceRecordModal> createState() => _KhataVoiceRecordModalState();
}

class _KhataVoiceRecordModalState extends State<KhataVoiceRecordModal> {
  bool _isListening = false;
  String _recognizedText = "";
  String _parsedName = "Rao Garu";
  double _parsedDebit = 300.0;
  double _parsedCredit = 30.0;

  void _simulateVoiceListening() async {
    setState(() {
      _isListening = true;
      _recognizedText = "Listening to Kirana merchant speech...";
    });

    await Future.delayed(const Duration(milliseconds: 1500));
    if (!mounted) return;

    setState(() {
      _recognizedText = "today rao garu took 300 rupees and he only paid 30 rupees";
      _parsedName = "Rao Garu";
      _parsedDebit = 300.0;
      _parsedCredit = 30.0;
      _isListening = false;
    });
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: EdgeInsets.only(
        left: 20,
        right: 20,
        top: 20,
        bottom: MediaQuery.of(context).viewInsets.bottom + 20,
      ),
      decoration: const BoxDecoration(
        color: AppColors.surfaceLowest,
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: const [
              Icon(Icons.mic, color: AppColors.secondary, size: 22),
              SizedBox(width: 8),
              Text(
                "Voice Khata Record (Sarvam AI)",
                style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
              ),
            ],
          ),
          const SizedBox(height: 6),
          const Text(
            "Speak naturally in Hindi, Telugu, or English to record debit or repayments.",
            style: TextStyle(fontSize: 12, color: AppColors.outline),
          ),
          const SizedBox(height: 16),
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: AppColors.surfaceLow,
              borderRadius: BorderRadius.circular(10),
            ),
            child: Row(
              children: [
                Expanded(
                  child: Text(
                    _recognizedText.isEmpty ? "Tap microphone and speak..." : _recognizedText,
                    style: TextStyle(
                      fontStyle: _recognizedText.isEmpty ? FontStyle.italic : FontStyle.normal,
                      fontSize: 13,
                    ),
                  ),
                ),
                IconButton(
                  icon: Icon(
                    _isListening ? Icons.graphic_eq : Icons.mic,
                    color: _isListening ? Colors.red : AppColors.secondary,
                  ),
                  onPressed: _simulateVoiceListening,
                ),
              ],
            ),
          ),
          if (_recognizedText.isNotEmpty && !_isListening) ...[
            const SizedBox(height: 14),
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: const Color(0xFFE8F5E9),
                borderRadius: BorderRadius.circular(10),
                border: Border.all(color: Colors.green.shade300),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: const [
                      Icon(Icons.auto_awesome, size: 16, color: Colors.green),
                      SizedBox(width: 6),
                      Text("Sarvam AI Structured Extraction", style: TextStyle(fontWeight: FontWeight.bold, fontSize: 12, color: Colors.green)),
                    ],
                  ),
                  const SizedBox(height: 6),
                  Text("Customer: $_parsedName", style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 13)),
                  Text("Debit Added: ₹${_parsedDebit.toStringAsFixed(0)} • Repaid: ₹${_parsedCredit.toStringAsFixed(0)}", style: const TextStyle(fontSize: 12)),
                  Text("Net Balance Added: ₹${(_parsedDebit - _parsedCredit).toStringAsFixed(0)}", style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 12, color: AppColors.secondary)),
                ],
              ),
            ),
            const SizedBox(height: 14),
            SizedBox(
              width: double.infinity,
              child: ElevatedButton.icon(
                style: ElevatedButton.styleFrom(backgroundColor: AppColors.secondary, foregroundColor: Colors.white),
                icon: const Icon(Icons.check, size: 18),
                label: const Text("CONFIRM & ADD TO KHATA"),
                onPressed: () {
                  widget.onParsedEntry(_parsedName, _parsedDebit, _parsedCredit, "Voice parsed entry");
                  Navigator.pop(context);
                },
              ),
            ),
          ],
        ],
      ),
    );
  }
}
