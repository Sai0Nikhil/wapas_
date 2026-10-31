import 'dart:io';

import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:google_mlkit_text_recognition/google_mlkit_text_recognition.dart';

import '../../services/voice_service.dart';
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
  final VoiceService _voice = VoiceService();
  final ImagePicker _picker = ImagePicker();

  bool _isListening = false;
  bool _isProcessing = false;
  String _recognizedText = '';
  File? _capturedImage;

  // Parsed result
  String _parsedName = '';
  double _parsedDebit = 0;
  double _parsedCredit = 0;
  bool _hasParsed = false;

  @override
  void dispose() {
    _voice.dispose();
    super.dispose();
  }

  // ── Voice: Sarvam Saaras v3 STT ─────────────────────────────────────────────

  Future<void> _toggleVoice() async {
    if (_isListening) {
      // Stop → transcribe
      setState(() { _isListening = false; _isProcessing = true; });
      final path = await _voice.stopRecording();
      if (path == null) { setState(() => _isProcessing = false); return; }

      try {
        final text = await _voice.transcribeWithSarvam(path, langCode: 'hi-IN');
        if (text.isNotEmpty) {
          setState(() { _recognizedText = text; });
          _parseEntry(text);
        } else {
          _showSnack('Could not understand. Try again.');
        }
      } catch (e) {
        _showSnack('Transcription error: $e');
      } finally {
        if (mounted) setState(() => _isProcessing = false);
      }
    } else {
      // Start recording
      try {
        await _voice.startRecording();
        setState(() { _isListening = true; _recognizedText = ''; _hasParsed = false; });
      } catch (e) {
        _showSnack('Microphone error: $e');
      }
    }
  }

  // ── Image: Parchi/Receipt OCR ────────────────────────────────────────────────

  Future<void> _captureParchi({bool fromGallery = false}) async {
    final XFile? file = await _picker.pickImage(
      source: fromGallery ? ImageSource.gallery : ImageSource.camera,
      imageQuality: 85,
    );
    if (file == null) return;

    setState(() { _isProcessing = true; _capturedImage = File(file.path); });

    try {
      final inputImage = InputImage.fromFilePath(file.path);
      final recognizer = TextRecognizer(script: TextRecognitionScript.devanagiri);
      final recognized = await recognizer.processImage(inputImage);
      await recognizer.close();

      // Also try Latin for mixed Hindi/English parchis
      final recognizerLatin = TextRecognizer(script: TextRecognitionScript.latin);
      final recognizedLatin = await recognizerLatin.processImage(inputImage);
      await recognizerLatin.close();

      final combined = '${recognized.text}\n${recognizedLatin.text}'.trim();
      if (combined.isEmpty) {
        _showSnack('No text found in image. Try a clearer photo.');
      } else {
        setState(() => _recognizedText = combined);
        _parseEntry(combined);
      }
    } catch (e) {
      _showSnack('OCR error: $e');
    } finally {
      if (mounted) setState(() => _isProcessing = false);
    }
  }

  // ── Simple parser ─────────────────────────────────────────────────────────────

  void _parseEntry(String text) {
    final lower = text.toLowerCase();

    // Extract name: look for "garu", "bhai", "ji" suffix or first capitalized word
    String name = 'Customer';
    final nameMatch = RegExp(r'([A-Z][a-z]+(?:\s[A-Z][a-z]+)?)\s*(?:garu|bhai|ji|ne|ka|ki)', caseSensitive: false).firstMatch(text);
    if (nameMatch != null) name = nameMatch.group(1)!.trim();

    // Extract amounts
    double debit = 0, credit = 0;
    final amounts = RegExp(r'(?:rs\.?|₹|rupee[s]?)\s*(\d+(?:\.\d{1,2})?)', caseSensitive: false)
        .allMatches(lower)
        .map((m) => double.tryParse(m.group(1) ?? '0') ?? 0)
        .toList();

    // Heuristic: first amount = debit (took), second = credit (paid)
    if (amounts.isNotEmpty) debit = amounts[0];
    if (amounts.length >= 2) credit = amounts[1];

    // Detect repayment keywords
    if (lower.contains('paid') || lower.contains('diya') || lower.contains('jama') || lower.contains('wapas')) {
      if (amounts.length == 1) { credit = amounts[0]; debit = 0; }
    }

    setState(() {
      _parsedName = name;
      _parsedDebit = debit;
      _parsedCredit = credit;
      _hasParsed = true;
    });
  }

  void _showSnack(String msg) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
      content: Text(msg),
      backgroundColor: AppColors.error,
      behavior: SnackBarBehavior.floating,
    ));
  }

  // ── Build ─────────────────────────────────────────────────────────────────────

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: EdgeInsets.only(
        left: 20, right: 20, top: 20,
        bottom: MediaQuery.of(context).viewInsets.bottom + 24,
      ),
      decoration: const BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      child: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Handle bar
            Center(
              child: Container(
                width: 36, height: 4,
                margin: const EdgeInsets.only(bottom: 16),
                decoration: BoxDecoration(color: Colors.grey.shade300, borderRadius: BorderRadius.circular(2)),
              ),
            ),

            const Text('Add Khata Entry', style: TextStyle(fontSize: 17, fontWeight: FontWeight.bold, color: Color(0xFF1A1A2E))),
            const SizedBox(height: 4),
            const Text('Speak or scan a parchi/receipt to record debit/repayment', style: TextStyle(fontSize: 12, color: Colors.grey)),
            const SizedBox(height: 20),

            // ── Action buttons row ─────────────────────────────────────────
            Row(
              children: [
                // Voice mic
                Expanded(
                  child: GestureDetector(
                    onTap: _isProcessing ? null : _toggleVoice,
                    child: AnimatedContainer(
                      duration: const Duration(milliseconds: 200),
                      height: 70,
                      decoration: BoxDecoration(
                        gradient: LinearGradient(
                          colors: _isListening
                              ? [Colors.red.shade400, Colors.red.shade700]
                              : [const Color(0xFF6C63FF), const Color(0xFF4FACFE)],
                        ),
                        borderRadius: BorderRadius.circular(14),
                        boxShadow: [BoxShadow(
                          color: (_isListening ? Colors.red : const Color(0xFF6C63FF)).withValues(alpha: 0.35),
                          blurRadius: 12, offset: const Offset(0, 4),
                        )],
                      ),
                      child: Column(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          Icon(_isListening ? Icons.stop_rounded : Icons.mic_rounded, color: Colors.white, size: 26),
                          const SizedBox(height: 4),
                          Text(_isListening ? 'Tap to stop' : 'Speak', style: const TextStyle(color: Colors.white, fontSize: 11, fontWeight: FontWeight.w600)),
                        ],
                      ),
                    ),
                  ),
                ),
                const SizedBox(width: 10),

                // Camera (parchi scan)
                Expanded(
                  child: GestureDetector(
                    onTap: _isProcessing ? null : () => _captureParchi(fromGallery: false),
                    child: Container(
                      height: 70,
                      decoration: BoxDecoration(
                        gradient: const LinearGradient(colors: [Color(0xFFFF6B35), Color(0xFFFF9F1C)]),
                        borderRadius: BorderRadius.circular(14),
                        boxShadow: [BoxShadow(color: const Color(0xFFFF6B35).withValues(alpha: 0.35), blurRadius: 12, offset: const Offset(0, 4))],
                      ),
                      child: const Column(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          Icon(Icons.camera_alt_rounded, color: Colors.white, size: 26),
                          SizedBox(height: 4),
                          Text('Scan Parchi', style: TextStyle(color: Colors.white, fontSize: 11, fontWeight: FontWeight.w600)),
                        ],
                      ),
                    ),
                  ),
                ),
                const SizedBox(width: 10),

                // Gallery
                Expanded(
                  child: GestureDetector(
                    onTap: _isProcessing ? null : () => _captureParchi(fromGallery: true),
                    child: Container(
                      height: 70,
                      decoration: BoxDecoration(
                        color: const Color(0xFFF5F5F8),
                        borderRadius: BorderRadius.circular(14),
                        border: Border.all(color: const Color(0xFFE0E0E8)),
                      ),
                      child: const Column(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          Icon(Icons.photo_library_rounded, color: Color(0xFF6C63FF), size: 26),
                          SizedBox(height: 4),
                          Text('Gallery', style: TextStyle(color: Color(0xFF6C63FF), fontSize: 11, fontWeight: FontWeight.w600)),
                        ],
                      ),
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 16),

            // ── Processing indicator ───────────────────────────────────────
            if (_isProcessing)
              Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(color: const Color(0xFFF0EEFF), borderRadius: BorderRadius.circular(10)),
                child: const Row(
                  children: [
                    SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2, color: Color(0xFF6C63FF))),
                    SizedBox(width: 10),
                    Text('Processing with Sarvam AI...', style: TextStyle(fontSize: 12, color: Color(0xFF6C63FF), fontWeight: FontWeight.w600)),
                  ],
                ),
              ),

            // ── Listening indicator ────────────────────────────────────────
            if (_isListening)
              Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(color: Colors.red.shade50, borderRadius: BorderRadius.circular(10)),
                child: const Row(
                  children: [
                    SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.red)),
                    SizedBox(width: 10),
                    Text('Listening... Speak in Hindi, Telugu or English', style: TextStyle(fontSize: 12, color: Colors.red, fontWeight: FontWeight.w600)),
                  ],
                ),
              ),

            // ── Captured image preview ─────────────────────────────────────
            if (_capturedImage != null) ...[
              const SizedBox(height: 12),
              ClipRRect(
                borderRadius: BorderRadius.circular(10),
                child: Image.file(_capturedImage!, height: 120, width: double.infinity, fit: BoxFit.cover),
              ),
            ],

            // ── Recognized text ────────────────────────────────────────────
            if (_recognizedText.isNotEmpty && !_isListening && !_isProcessing) ...[
              const SizedBox(height: 14),
              Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: const Color(0xFFF5F5F8),
                  borderRadius: BorderRadius.circular(10),
                  border: Border.all(color: const Color(0xFFE0E0E8)),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text('Recognized:', style: TextStyle(fontSize: 10, fontWeight: FontWeight.bold, color: Colors.grey)),
                    const SizedBox(height: 4),
                    Text(_recognizedText, style: const TextStyle(fontSize: 13, color: Color(0xFF1A1A2E))),
                  ],
                ),
              ),
            ],

            // ── Parsed result ──────────────────────────────────────────────
            if (_hasParsed && !_isProcessing) ...[
              const SizedBox(height: 12),
              Container(
                padding: const EdgeInsets.all(14),
                decoration: BoxDecoration(
                  gradient: const LinearGradient(
                    colors: [Color(0xFFE8F5E9), Color(0xFFF1F8E9)],
                  ),
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: Colors.green.shade300),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Row(
                      children: [
                        Icon(Icons.auto_awesome, size: 16, color: Colors.green),
                        SizedBox(width: 6),
                        Text('Sarvam AI Extraction', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 12, color: Colors.green)),
                      ],
                    ),
                    const SizedBox(height: 10),
                    _infoRow('Customer', _parsedName),
                    _infoRow('Debit (gave)', '₹${_parsedDebit.toStringAsFixed(0)}', color: Colors.red.shade700),
                    _infoRow('Credit (paid back)', '₹${_parsedCredit.toStringAsFixed(0)}', color: Colors.green.shade700),
                    _infoRow('Net Due Added', '₹${(_parsedDebit - _parsedCredit).toStringAsFixed(0)}', bold: true),
                  ],
                ),
              ),
              const SizedBox(height: 6),
              // Manual correction hint
              const Text('Wrong? Edit name/amount manually before confirming.', style: TextStyle(fontSize: 10, color: Colors.grey)),
              const SizedBox(height: 14),
              SizedBox(
                width: double.infinity,
                height: 48,
                child: ElevatedButton.icon(
                  style: ElevatedButton.styleFrom(
                    backgroundColor: const Color(0xFF6C63FF),
                    foregroundColor: Colors.white,
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                  ),
                  icon: const Icon(Icons.check_rounded, size: 20),
                  label: const Text('CONFIRM & ADD TO KHATA', style: TextStyle(fontWeight: FontWeight.bold)),
                  onPressed: () {
                    widget.onParsedEntry(_parsedName, _parsedDebit, _parsedCredit, _recognizedText);
                    Navigator.pop(context);
                  },
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }

  Widget _infoRow(String label, String value, {Color? color, bool bold = false}) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 3),
      child: Row(
        children: [
          Text('$label: ', style: const TextStyle(fontSize: 12, color: Colors.black54)),
          Text(value, style: TextStyle(fontSize: 13, fontWeight: bold ? FontWeight.bold : FontWeight.w600, color: color ?? const Color(0xFF1A1A2E))),
        ],
      ),
    );
  }
}
