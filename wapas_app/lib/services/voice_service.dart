import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:just_audio/just_audio.dart';
import 'package:path_provider/path_provider.dart';
import 'package:record/record.dart';

/// Handles the full voice pipeline for Sarkar AI:
///   1. Record mic → WAV/M4A via `record` package
///   2. Sarvam Saaras v3 STT → transcript text
///   3. Caller sends text to Sarvam-105B (via existing SarkarRepo)
///   4. ElevenLabs Flash v2.5 TTS → stream audio bytes → play via just_audio
class VoiceService {
  // ── Sarvam STT ──────────────────────────────────────────────────────────────
  static const String _sarvamKey = 'sk_tlhz0ys9_CJq36YnlAS1INRQLh8b7vGuT';
  static const String _sarvamSttUrl = 'https://api.sarvam.ai/speech-to-text';

  // ── ElevenLabs TTS ──────────────────────────────────────────────────────────
  // Voice ID: Rachel – natural, calm, English/Hindi friendly
  static const String _elevenLabsKey = 'sk_ca9ddbca4a484951ab3f8f4abbabc4a1f60a139f411e7b1c';
  static const String _elevenLabsVoiceId = '21m00Tcm4TlvDq8ikWAM'; // Rachel


  final AudioRecorder _recorder = AudioRecorder();
  final AudioPlayer _player = AudioPlayer();

  bool _isRecording = false;
  bool _isSpeaking = false;

  bool get isRecording => _isRecording;
  bool get isSpeaking => _isSpeaking;

  // ── Recording ────────────────────────────────────────────────────────────────

  /// Starts recording mic audio to a temp file. Returns immediately.
  Future<void> startRecording() async {
    if (_isRecording) return;
    final hasPermission = await _recorder.hasPermission();
    if (!hasPermission) throw Exception('Microphone permission denied');

    final dir = await getTemporaryDirectory();
    final path = '${dir.path}/sarkar_voice_${DateTime.now().millisecondsSinceEpoch}.m4a';

    await _recorder.start(
      const RecordConfig(
        encoder: AudioEncoder.aacLc,
        sampleRate: 16000,
        numChannels: 1,
        bitRate: 64000,
      ),
      path: path,
    );
    _isRecording = true;
    debugPrint('[VoiceService] Recording started → $path');
  }

  /// Stops recording and returns the file path.
  Future<String?> stopRecording() async {
    if (!_isRecording) return null;
    _isRecording = false;
    final path = await _recorder.stop();
    debugPrint('[VoiceService] Recording stopped → $path');
    return path;
  }

  // ── Sarvam STT ───────────────────────────────────────────────────────────────

  /// Sends the recorded audio file to Sarvam Saaras v3 for transcription.
  /// [langCode] examples: 'hi-IN', 'te-IN', 'en-IN', 'ta-IN', 'kn-IN'
  Future<String> transcribeWithSarvam(String filePath, {String langCode = 'en-IN'}) async {
    final file = File(filePath);
    if (!file.existsSync()) throw Exception('Audio file not found: $filePath');

    final bytes = await file.readAsBytes();
    debugPrint('[VoiceService] Sending ${bytes.length} bytes to Sarvam STT (lang=$langCode)');

    final request = http.MultipartRequest('POST', Uri.parse(_sarvamSttUrl))
      ..headers['api-subscription-key'] = _sarvamKey
      ..fields['language_code'] = langCode
      ..fields['model'] = 'saaras:v3'
      ..fields['with_timestamps'] = 'false'
      ..files.add(http.MultipartFile.fromBytes(
        'file',
        bytes,
        filename: 'audio.m4a',
      ));

    final streamed = await request.send().timeout(const Duration(seconds: 30));
    final body = await streamed.stream.bytesToString();

    if (streamed.statusCode != 200) {
      debugPrint('[VoiceService] Sarvam STT error ${streamed.statusCode}: $body');
      throw Exception('Sarvam STT failed (${streamed.statusCode})');
    }

    final json = jsonDecode(body) as Map<String, dynamic>;
    // Response format: { "transcript": "...", "language_code": "...", ... }
    final transcript = json['transcript'] as String? ?? '';
    debugPrint('[VoiceService] Transcript: "$transcript"');
    return transcript.trim();
  }

  // ── ElevenLabs TTS ───────────────────────────────────────────────────────────

  /// Converts text to speech with ElevenLabs Flash v2.5 and plays it.
  Future<void> speakWithElevenLabs(String text) async {
    if (text.trim().isEmpty) return;
    _isSpeaking = true;

    try {
      debugPrint('[VoiceService] ElevenLabs TTS: "${text.substring(0, text.length.clamp(0, 60))}…"');

      final response = await http.post(
        Uri.parse('https://api.elevenlabs.io/v1/text-to-speech/$_elevenLabsVoiceId?output_format=mp3_44100_128'),
        headers: {
          'xi-api-key': _elevenLabsKey,
          'Content-Type': 'application/json',
          'Accept': 'audio/mpeg',
        },
        body: jsonEncode({
          'text': text,
          'model_id': 'eleven_flash_v2_5', // Lowest latency model
          'voice_settings': {
            'stability': 0.5,
            'similarity_boost': 0.8,
            'style': 0.0,
            'use_speaker_boost': true,
          },
        }),
      ).timeout(const Duration(seconds: 30));

      if (response.statusCode != 200) {
        debugPrint('[VoiceService] ElevenLabs error ${response.statusCode}: ${response.body}');
        _isSpeaking = false;
        return;
      }

      // Save MP3 bytes to temp file and play
      final dir = await getTemporaryDirectory();
      final mp3File = File('${dir.path}/sarkar_tts_${DateTime.now().millisecondsSinceEpoch}.mp3');
      await mp3File.writeAsBytes(response.bodyBytes);

      await _player.stop();
      await _player.setFilePath(mp3File.path);
      await _player.play();
      await _player.processingStateStream
          .firstWhere((s) => s == ProcessingState.completed || s == ProcessingState.idle);

      // Cleanup
      try { mp3File.deleteSync(); } catch (_) {}
    } catch (e) {
      debugPrint('[VoiceService] TTS error: $e');
    } finally {
      _isSpeaking = false;
    }
  }

  /// Stops any currently playing TTS audio.
  Future<void> stopSpeaking() async {
    _isSpeaking = false;
    await _player.stop();
  }

  Future<void> dispose() async {
    await _recorder.dispose();
    await _player.dispose();
  }

  /// Maps Sarkar lang code to Sarvam BCP-47 code.
  static String toSarvamLang(String sarkarLang) {
    switch (sarkarLang) {
      case 'hi':
      case 'hi_en':
        return 'hi-IN';
      case 'te':
        return 'te-IN';
      case 'kn':
        return 'kn-IN';
      case 'ta':
        return 'ta-IN';
      default:
        return 'en-IN';
    }
  }
}
