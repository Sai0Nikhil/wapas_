import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/sarkar_models.dart';
import '../providers/app_providers.dart';
import '../services/voice_service.dart';
import '../theme/app_theme.dart';

class SarkarChatMessage {
  final bool isUser;
  final String text;
  final DateTime timestamp;
  final SarkarAskResponse? response;
  bool isActionConfirmed;
  bool isActionCancelled;
  bool isConfirming;

  SarkarChatMessage({
    required this.isUser,
    required this.text,
    required this.timestamp,
    this.response,
    this.isActionConfirmed = false,
    this.isActionCancelled = false,
    this.isConfirming = false,
  });
}

// ── Voice state ──────────────────────────────────────────────────────────────
enum VoiceState { idle, recording, transcribing, thinking, speaking }

class SarkarCopilotScreen extends ConsumerStatefulWidget {
  const SarkarCopilotScreen({super.key});

  @override
  ConsumerState<SarkarCopilotScreen> createState() => _SarkarCopilotScreenState();
}

class _SarkarCopilotScreenState extends ConsumerState<SarkarCopilotScreen>
    with TickerProviderStateMixin {
  final TextEditingController _msgCtrl = TextEditingController();
  final ScrollController _scrollCtrl = ScrollController();

  // Language
  String _selectedLang = 'en';
  final Map<String, String> _languages = {
    'en': 'English',
    'hi_en': 'Hinglish',
    'te': 'తెలుగు',
    'kn': 'ಕನ್ನಡ',
    'ta': 'தமிழ்',
    'hi': 'हिंदी',
  };

  // Voice
  final VoiceService _voice = VoiceService();
  VoiceState _voiceState = VoiceState.idle;
  bool _autoSpeak = true; // auto-play AI responses with ElevenLabs

  // Pulse animation for mic button
  late AnimationController _pulseCtrl;
  late Animation<double> _pulseAnim;

  // Waveform animation
  late AnimationController _waveCtrl;

  // Messages
  late List<SarkarChatMessage> _messages;
  bool _isLoading = false;

  @override
  void initState() {
    super.initState();

    _pulseCtrl = AnimationController(vsync: this, duration: const Duration(milliseconds: 900))
      ..repeat(reverse: true);
    _pulseAnim = Tween<double>(begin: 1.0, end: 1.25).animate(
      CurvedAnimation(parent: _pulseCtrl, curve: Curves.easeInOut),
    );

    _waveCtrl = AnimationController(vsync: this, duration: const Duration(milliseconds: 800))
      ..repeat();

    _messages = [_buildWelcome('en')];
  }

  @override
  void dispose() {
    _msgCtrl.dispose();
    _scrollCtrl.dispose();
    _pulseCtrl.dispose();
    _waveCtrl.dispose();
    _voice.dispose();
    super.dispose();
  }

  // ── Welcome message ─────────────────────────────────────────────────────────

  SarkarChatMessage _buildWelcome(String lang) {
    final greetings = {
      'te': 'నమస్తే! Wapas కోపైలట్‌కి స్వాగతం. మీ స్టోర్ గురించి ఏదైనా అడగండి.',
      'kn': 'ನಮಸ್ಕಾರ! Wapas ಕೋಪೈಲಟ್‌ಗೆ ಸ್ವಾಗತ.',
      'hi_en': 'Namaste! Main Wapas Sarkar Copilot hoon. Poochiye kuch bhi.',
      'ta': 'வணக்கம்! Wapas கோபிலட்டுக்கு வரவேற்கிறோம்.',
      'hi': 'नमस्ते! Wapas कोपायलट में आपका स्वागत है।',
      'en': 'Namaste! I\'m Sarkar, your Wapas AI Copilot. Ask me about daily sales, khata dues, low stock, or restock orders.',
    };
    return SarkarChatMessage(
      isUser: false,
      text: greetings[lang] ?? greetings['en']!,
      timestamp: DateTime.now(),
    );
  }

  // ── Scroll ───────────────────────────────────────────────────────────────────

  void _scrollToBottom() {
    Future.delayed(const Duration(milliseconds: 150), () {
      if (_scrollCtrl.hasClients) {
        _scrollCtrl.animateTo(
          _scrollCtrl.position.maxScrollExtent,
          duration: const Duration(milliseconds: 300),
          curve: Curves.easeOut,
        );
      }
    });
  }

  // ── Voice pipeline ───────────────────────────────────────────────────────────

  Future<void> _onMicTap() async {
    if (_voiceState == VoiceState.speaking) {
      await _voice.stopSpeaking();
      setState(() => _voiceState = VoiceState.idle);
      return;
    }

    if (_voiceState == VoiceState.recording) {
      // Stop recording → transcribe → send
      setState(() => _voiceState = VoiceState.transcribing);
      final path = await _voice.stopRecording();
      if (path == null || path.isEmpty) {
        setState(() => _voiceState = VoiceState.idle);
        return;
      }
      try {
        final transcript = await _voice.transcribeWithSarvam(
          path,
          langCode: VoiceService.toSarvamLang(_selectedLang),
        );
        if (transcript.isNotEmpty) {
          await _handleSend(transcript);
        } else {
          _showSnack('Could not understand. Please try again.');
          setState(() => _voiceState = VoiceState.idle);
        }
      } catch (e) {
        _showSnack('Transcription failed: $e');
        setState(() => _voiceState = VoiceState.idle);
      }
    } else {
      // Start recording
      try {
        await _voice.startRecording();
        setState(() => _voiceState = VoiceState.recording);
      } catch (e) {
        _showSnack('Microphone error: $e');
      }
    }
  }

  // ── Send to Sarvam-105B ──────────────────────────────────────────────────────

  Future<void> _handleSend(String query) async {
    if (query.trim().isEmpty) return;
    final q = query.trim();
    _msgCtrl.clear();

    setState(() {
      _messages.add(SarkarChatMessage(isUser: true, text: q, timestamp: DateTime.now()));
      _isLoading = true;
      _voiceState = VoiceState.thinking;
    });
    _scrollToBottom();

    try {
      final res = await ref.read(sarkarRepoProvider).ask(q);
      if (!mounted) return;
      setState(() {
        _isLoading = false;
        _messages.add(SarkarChatMessage(
          isUser: false,
          text: res.message,
          timestamp: DateTime.now(),
          response: res,
        ));
        _voiceState = _autoSpeak ? VoiceState.speaking : VoiceState.idle;
      });
      _scrollToBottom();

      // Auto-speak the response
      if (_autoSpeak) {
        await _voice.speakWithElevenLabs(res.message);
        if (mounted) setState(() => _voiceState = VoiceState.idle);
      }
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _isLoading = false;
        _voiceState = VoiceState.idle;
        _messages.add(SarkarChatMessage(
          isUser: false,
          text: 'Request failed: ${e.toString()}',
          timestamp: DateTime.now(),
        ));
      });
      _scrollToBottom();
    }
  }

  // ── Confirm action ───────────────────────────────────────────────────────────

  Future<void> _confirmAction(SarkarChatMessage msg) async {
    final conf = msg.response?.confirmation;
    if (conf == null) return;
    setState(() => msg.isConfirming = true);
    try {
      await ref.read(sarkarRepoProvider).confirmAction(conf.actionId, conf.token);
      if (mounted) setState(() { msg.isConfirming = false; msg.isActionConfirmed = true; });
      _showSnack('Action confirmed ✓', success: true);
    } catch (e) {
      if (mounted) setState(() => msg.isConfirming = false);
      _showSnack('Confirmation failed: $e');
    }
  }

  void _showSnack(String msg, {bool success = false}) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
      content: Text(msg),
      backgroundColor: success ? AppColors.tertiary : AppColors.error,
      behavior: SnackBarBehavior.floating,
    ));
  }

  // ── Build ────────────────────────────────────────────────────────────────────

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFFF5F5F8),
      appBar: _buildAppBar(),
      body: Column(
        children: [
          _buildSuggestionsBar(),
          Expanded(child: _buildMessageList()),
          _buildStatusBar(),
          _buildInputBar(),
        ],
      ),
    );
  }

  AppBar _buildAppBar() {
    return AppBar(
      elevation: 0,
      backgroundColor: Colors.white,
      surfaceTintColor: Colors.white,
      title: Row(
        children: [
          Container(
            width: 36,
            height: 36,
            decoration: BoxDecoration(
              gradient: const LinearGradient(
                colors: [Color(0xFF6C63FF), Color(0xFF4FACFE)],
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
              ),
              borderRadius: BorderRadius.circular(10),
            ),
            child: const Icon(Icons.psychology_rounded, color: Colors.white, size: 20),
          ),
          const SizedBox(width: 10),
          const Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('Sarkar AI', style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: Color(0xFF1A1A2E))),
              Text('Sarvam-105B + ElevenLabs Voice', style: TextStyle(fontSize: 10, color: Color(0xFF888888))),
            ],
          ),
        ],
      ),
      actions: [
        // Auto-speak toggle
        IconButton(
          tooltip: _autoSpeak ? 'Voice ON' : 'Voice OFF',
          icon: Icon(
            _autoSpeak ? Icons.volume_up_rounded : Icons.volume_off_rounded,
            color: _autoSpeak ? const Color(0xFF6C63FF) : Colors.grey,
          ),
          onPressed: () => setState(() => _autoSpeak = !_autoSpeak),
        ),
        // Language picker
        Container(
          margin: const EdgeInsets.only(right: 10, top: 8, bottom: 8),
          padding: const EdgeInsets.symmetric(horizontal: 8),
          decoration: BoxDecoration(
            color: const Color(0xFFF0EEFF),
            borderRadius: BorderRadius.circular(20),
          ),
          child: DropdownButtonHideUnderline(
            child: DropdownButton<String>(
              value: _selectedLang,
              icon: const Icon(Icons.keyboard_arrow_down, size: 16, color: Color(0xFF6C63FF)),
              style: const TextStyle(fontSize: 11, fontWeight: FontWeight.bold, color: Color(0xFF6C63FF)),
              dropdownColor: Colors.white,
              onChanged: (val) {
                if (val != null && val != _selectedLang) {
                  setState(() {
                    _selectedLang = val;
                    _messages.add(_buildWelcome(val));
                  });
                  _scrollToBottom();
                }
              },
              items: _languages.entries.map((e) => DropdownMenuItem(value: e.key, child: Text(e.value))).toList(),
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildSuggestionsBar() {
    final chips = ['Today\'s summary', 'Khata dues', 'Low stock', 'Restock receipt', 'Top sellers'];
    return Container(
      height: 44,
      color: Colors.white,
      child: ListView.separated(
        scrollDirection: Axis.horizontal,
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
        itemCount: chips.length,
        separatorBuilder: (_, __) => const SizedBox(width: 8), // ignore: unnecessary_underscores
        itemBuilder: (ctx, i) => ActionChip(
          label: Text(chips[i], style: const TextStyle(fontSize: 11, color: Color(0xFF6C63FF))),
          backgroundColor: const Color(0xFFF0EEFF),
          side: BorderSide.none,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
          onPressed: () => _handleSend(chips[i]),
        ),
      ),
    );
  }

  Widget _buildMessageList() {
    return ListView.builder(
      controller: _scrollCtrl,
      padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
      itemCount: _messages.length,
      itemBuilder: (ctx, i) => _buildBubble(_messages[i]),
    );
  }

  Widget _buildStatusBar() {
    if (_voiceState == VoiceState.idle && !_isLoading) return const SizedBox.shrink();

    final Map<VoiceState, (String, Color, IconData)> config = {
      VoiceState.recording: ('Recording… tap mic to send', Colors.red, Icons.mic),
      VoiceState.transcribing: ('Transcribing with Sarvam…', const Color(0xFF6C63FF), Icons.transcribe),
      VoiceState.thinking: ('Sarkar is thinking…', const Color(0xFF4FACFE), Icons.psychology),
      VoiceState.speaking: ('Speaking… tap mic to stop', const Color(0xFF00C9A7), Icons.volume_up),
    };

    final entry = config[_voiceState];
    final label = _isLoading && _voiceState == VoiceState.idle ? 'Sarkar is thinking…' : (entry?.$1 ?? '');
    final color = _isLoading && _voiceState == VoiceState.idle ? const Color(0xFF4FACFE) : (entry?.$2 ?? Colors.grey);
    final icon = _isLoading && _voiceState == VoiceState.idle ? Icons.psychology : (entry?.$3 ?? Icons.info);

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      color: color.withValues(alpha: 0.08),
      child: Row(
        children: [
          SizedBox(
            width: 16, height: 16,
            child: CircularProgressIndicator(strokeWidth: 2, color: color),
          ),
          const SizedBox(width: 10),
          Icon(icon, size: 14, color: color),
          const SizedBox(width: 6),
          Text(label, style: TextStyle(fontSize: 12, color: color, fontWeight: FontWeight.w600)),
        ],
      ),
    );
  }

  Widget _buildInputBar() {
    final bool isRecording = _voiceState == VoiceState.recording;
    final bool isBusy = _voiceState == VoiceState.transcribing || _voiceState == VoiceState.thinking;

    return Container(
      padding: const EdgeInsets.fromLTRB(12, 10, 12, 14),
      decoration: const BoxDecoration(
        color: Colors.white,
        boxShadow: [BoxShadow(color: Color(0x12000000), blurRadius: 16, offset: Offset(0, -4))],
      ),
      child: SafeArea(
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            // ── Mic Button with pulse ──────────────────────────────────────
            GestureDetector(
              onTap: isBusy ? null : _onMicTap,
              child: AnimatedBuilder(
                animation: _pulseAnim,
                builder: (ctx, child) {
                  final scale = isRecording ? _pulseAnim.value : 1.0;
                  return Transform.scale(
                    scale: scale,
                    child: Container(
                      width: 52,
                      height: 52,
                      decoration: BoxDecoration(
                        shape: BoxShape.circle,
                        gradient: LinearGradient(
                          colors: isRecording
                              ? [Colors.red.shade400, Colors.red.shade700]
                              : _voiceState == VoiceState.speaking
                                  ? [const Color(0xFF00C9A7), const Color(0xFF009E88)]
                                  : [const Color(0xFF6C63FF), const Color(0xFF4FACFE)],
                          begin: Alignment.topLeft,
                          end: Alignment.bottomRight,
                        ),
                        boxShadow: [
                          BoxShadow(
                            color: (isRecording ? Colors.red : const Color(0xFF6C63FF)).withValues(alpha: 0.35),
                            blurRadius: isRecording ? 20 : 10,
                            spreadRadius: isRecording ? 4 : 0,
                          ),
                        ],
                      ),
                      child: Icon(
                        isRecording ? Icons.stop_rounded
                            : _voiceState == VoiceState.speaking ? Icons.stop_circle_outlined
                            : Icons.mic_rounded,
                        color: Colors.white,
                        size: 26,
                      ),
                    ),
                  );
                },
              ),
            ),
            const SizedBox(width: 10),

            // ── Text field ─────────────────────────────────────────────────
            Expanded(
              child: Container(
                constraints: const BoxConstraints(maxHeight: 120),
                decoration: BoxDecoration(
                  color: const Color(0xFFF5F5F8),
                  borderRadius: BorderRadius.circular(24),
                  border: Border.all(color: const Color(0xFFE0E0E8)),
                ),
                child: TextField(
                  controller: _msgCtrl,
                  maxLines: null,
                  textInputAction: TextInputAction.send,
                  decoration: InputDecoration(
                    hintText: isRecording
                        ? 'Listening in ${_languages[_selectedLang]}…'
                        : 'Ask Sarkar in ${_languages[_selectedLang]}…',
                    hintStyle: const TextStyle(fontSize: 13, color: Color(0xFFAAAAAA)),
                    border: InputBorder.none,
                    contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                  ),
                  onSubmitted: (val) => _handleSend(val),
                ),
              ),
            ),
            const SizedBox(width: 8),

            // ── Send Button ────────────────────────────────────────────────
            GestureDetector(
              onTap: () => _handleSend(_msgCtrl.text),
              child: Container(
                width: 46,
                height: 46,
                decoration: const BoxDecoration(
                  shape: BoxShape.circle,
                  gradient: LinearGradient(
                    colors: [Color(0xFF6C63FF), Color(0xFF4FACFE)],
                    begin: Alignment.topLeft,
                    end: Alignment.bottomRight,
                  ),
                ),
                child: const Icon(Icons.send_rounded, color: Colors.white, size: 20),
              ),
            ),
          ],
        ),
      ),
    );
  }

  // ── Message bubbles ──────────────────────────────────────────────────────────

  Widget _buildBubble(SarkarChatMessage msg) {
    if (msg.isUser) {
      return Align(
        alignment: Alignment.centerRight,
        child: Container(
          margin: const EdgeInsets.only(bottom: 12, left: 60),
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
          decoration: BoxDecoration(
            gradient: const LinearGradient(
              colors: [Color(0xFF6C63FF), Color(0xFF4FACFE)],
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
            ),
            borderRadius: BorderRadius.circular(20).copyWith(bottomRight: Radius.zero),
            boxShadow: [BoxShadow(color: const Color(0xFF6C63FF).withValues(alpha: 0.25), blurRadius: 8, offset: const Offset(0, 3))],
          ),
          child: Text(msg.text, style: const TextStyle(color: Colors.white, fontSize: 14, height: 1.4)),
        ),
      );
    }

    final res = msg.response;
    final traces = res?.toolTrace ?? [];

    return Align(
      alignment: Alignment.centerLeft,
      child: Container(
        margin: const EdgeInsets.only(bottom: 16, right: 40),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // AI avatar + trace chip
            Row(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                Container(
                  width: 32,
                  height: 32,
                  margin: const EdgeInsets.only(right: 8, bottom: 4),
                  decoration: BoxDecoration(
                    gradient: const LinearGradient(colors: [Color(0xFF6C63FF), Color(0xFF4FACFE)]),
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: const Icon(Icons.psychology_rounded, color: Colors.white, size: 16),
                ),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      if (res != null)
                        Container(
                          margin: const EdgeInsets.only(bottom: 4),
                          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                          decoration: BoxDecoration(
                            color: const Color(0xFFF0EEFF),
                            borderRadius: BorderRadius.circular(6),
                          ),
                          child: Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              const Icon(Icons.bolt_rounded, size: 12, color: Color(0xFF6C63FF)),
                              const SizedBox(width: 4),
                              Text(
                                traces.isNotEmpty
                                    ? 'TOOL: ${traces.first.tool} • ${res.engine}'
                                    : 'ROUTER: ${res.engine}',
                                style: const TextStyle(fontSize: 9, fontWeight: FontWeight.bold, color: Color(0xFF6C63FF)),
                              ),
                              if (res.input?.latencyMs != null && res.input!.latencyMs > 0)
                                Text(' • ${res.input!.latencyMs}ms',
                                    style: const TextStyle(fontSize: 9, color: Color(0xFFAAAAAA))),
                            ],
                          ),
                        ),
                      // Message bubble
                      Container(
                        padding: const EdgeInsets.all(14),
                        decoration: BoxDecoration(
                          color: Colors.white,
                          borderRadius: BorderRadius.circular(20).copyWith(topLeft: Radius.zero),
                          boxShadow: [BoxShadow(color: Colors.black.withValues(alpha: 0.05), blurRadius: 10, offset: const Offset(0, 3))],
                          border: Border.all(color: const Color(0xFFEEEEF5)),
                        ),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(msg.text, style: const TextStyle(fontSize: 14, color: Color(0xFF1A1A2E), height: 1.5)),
                            if (res?.data != null && res!.data!.isNotEmpty) ...[
                              const SizedBox(height: 10),
                              _buildDataView(res.data!),
                            ],
                            if (res != null && res.needsConfirmation && !msg.isActionConfirmed && !msg.isActionCancelled) ...[
                              const SizedBox(height: 12),
                              _buildConfirmCard(msg),
                            ],
                            if (msg.isActionConfirmed) _buildStatusChip('Action confirmed ✓', Colors.green),
                            if (msg.isActionCancelled) _buildStatusChip('Action cancelled', Colors.grey),
                          ],
                        ),
                      ),
                      // Speak button
                      GestureDetector(
                        onTap: () => _voice.speakWithElevenLabs(msg.text),
                        child: Container(
                          margin: const EdgeInsets.only(top: 4),
                          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                          decoration: BoxDecoration(
                            color: Colors.white,
                            borderRadius: BorderRadius.circular(20),
                            border: Border.all(color: const Color(0xFFE0E0E8)),
                          ),
                          child: const Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              Icon(Icons.volume_up_rounded, size: 13, color: Color(0xFF6C63FF)),
                              SizedBox(width: 4),
                              Text('Speak', style: TextStyle(fontSize: 11, color: Color(0xFF6C63FF), fontWeight: FontWeight.w600)),
                            ],
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildDataView(Map<String, dynamic> data) {
    return Container(
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: const Color(0xFFF5F5FF),
        borderRadius: BorderRadius.circular(10),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: data.entries.take(5).map((e) => Padding(
          padding: const EdgeInsets.symmetric(vertical: 2),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('${e.key}: ', style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 11, color: Color(0xFF6C63FF))),
              Expanded(child: Text('${e.value}', style: const TextStyle(fontSize: 11, color: Color(0xFF444466)))),
            ],
          ),
        )).toList(),
      ),
    );
  }

  Widget _buildConfirmCard(SarkarChatMessage msg) {
    final conf = msg.response!.confirmation!;
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: const Color(0xFFFFF9E6),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: const Color(0xFFFFCC00), width: 1.5),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Row(
            children: [
              Icon(Icons.warning_amber_rounded, color: Color(0xFF996600), size: 18),
              SizedBox(width: 6),
              Text('Owner Confirmation Required',
                  style: TextStyle(fontWeight: FontWeight.bold, fontSize: 12, color: Color(0xFF996600))),
            ],
          ),
          const SizedBox(height: 6),
          Text(conf.summary, style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600)),
          const SizedBox(height: 10),
          Row(
            children: [
              Expanded(
                child: OutlinedButton(
                  onPressed: msg.isConfirming ? null : () => setState(() => msg.isActionCancelled = true),
                  style: OutlinedButton.styleFrom(
                    visualDensity: VisualDensity.compact,
                    side: const BorderSide(color: Colors.grey),
                  ),
                  child: const Text('Cancel', style: TextStyle(fontSize: 11)),
                ),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: ElevatedButton(
                  onPressed: msg.isConfirming ? null : () => _confirmAction(msg),
                  style: ElevatedButton.styleFrom(
                    visualDensity: VisualDensity.compact,
                    backgroundColor: const Color(0xFF6C63FF),
                    foregroundColor: Colors.white,
                  ),
                  child: msg.isConfirming
                      ? const SizedBox(width: 14, height: 14, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                      : const Text('Confirm', style: TextStyle(fontSize: 11, fontWeight: FontWeight.bold)),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildStatusChip(String text, Color color) {
    return Container(
      margin: const EdgeInsets.only(top: 10),
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(text.contains('✓') ? Icons.check_circle : Icons.cancel, size: 14, color: color),
          const SizedBox(width: 6),
          Text(text, style: TextStyle(fontSize: 11, fontWeight: FontWeight.bold, color: color)),
        ],
      ),
    );
  }
}
