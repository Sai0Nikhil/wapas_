import 'package:flutter/material.dart';
import '../theme/app_theme.dart';

class SarkarCopilotScreen extends StatefulWidget {
  const SarkarCopilotScreen({super.key});

  @override
  State<SarkarCopilotScreen> createState() => _SarkarCopilotScreenState();
}

class _SarkarCopilotScreenState extends State<SarkarCopilotScreen> {
  final TextEditingController _msgCtrl = TextEditingController();
  final List<Map<String, dynamic>> _messages = [
    {
      "isUser": false,
      "text": "Namaste Sharma ji! Main Sarkar hoon, aapka retail copilot. Aaj dukan ka hisaab, stock ya Khata se judi koi bhi jaankari poochiye.",
      "time": "10:00 AM",
      "suggestions": ["Aaj ka turnover?", "Atta ka stock kitna hai?", "Kisne udhaar nahi diya?"],
    },
  ];

  void _handleSend(String query) {
    if (query.trim().isEmpty) return;

    final userQuery = query.trim();
    _msgCtrl.clear();

    setState(() {
      _messages.add({
        "isUser": true,
        "text": userQuery,
        "time": "Just now",
      });
    });

    // Smart Copilot Response logic based on Stitch & friend's Sarkar engine
    Future.delayed(const Duration(milliseconds: 600), () {
      String reply = "";
      List<String> nextSuggestions = [];

      final q = userQuery.toLowerCase();
      if (q.contains("turnover") || q.contains("sale") || q.contains("aaj")) {
        reply = "Aaj Sharma Kirana par ₹4,240 ki kul bikri hui hai. 3 bills Counter par kata gaya, aur ₹1,420 Paytm Recovery se recover hua hai.";
        nextSuggestions = ["Unpaid Khata kitna hai?", "Low stock items dikhao"];
      } else if (q.contains("stock") || q.contains("atta")) {
        reply = "Aashirvaad Shudh Chakki Atta 5kg ka stock abhi 34 units hai. Amul Butter 500g low hai (sirf 18 units bache hain). Kya distributor ko order bhejna hai?";
        nextSuggestions = ["Distributor PO banao", "Full inventory report"];
      } else if (q.contains("khata") || q.contains("udhaar")) {
        reply = "Aapke Khata ledger mein kul ₹10,420 ka udhaar baki hai. Anand Medicals ka ₹5,800 overdue hai. Maine WhatsApp payment link draft taiyar kiya hai.";
        nextSuggestions = ["Sabhi ko payment link bhejo", "Khata list dekho"];
      } else {
        reply = "Maine aapka request audit log mein note kar liya hai: \"$userQuery\". Data Paytm verified server se synced hai.";
        nextSuggestions = ["Aaj ka turnover?", "Atta stock check"];
      }

      if (mounted) {
        setState(() {
          _messages.add({
            "isUser": false,
            "text": reply,
            "time": "Just now",
            "suggestions": nextSuggestions,
          });
        });
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.surface,
      appBar: AppBar(
        backgroundColor: AppColors.surfaceLowest,
        title: Row(
          children: [
            Container(
              padding: const EdgeInsets.all(6),
              decoration: BoxDecoration(
                color: AppColors.secondaryContainer.withOpacity(0.15),
                shape: BoxShape.circle,
              ),
              child: const Icon(Icons.psychology, color: AppColors.secondary, size: 20),
            ),
            const SizedBox(width: 10),
            const Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text("Sarkar AI Copilot", style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
                Text("Retail & Inventory Intelligence (Sarvam-105B)", style: TextStyle(fontSize: 11, color: AppColors.outline)),
              ],
            ),
          ],
        ),
      ),
      body: Column(
        children: [
          Expanded(
            child: ListView.builder(
              padding: const EdgeInsets.all(16),
              itemCount: _messages.length,
              itemBuilder: (ctx, idx) {
                final m = _messages[idx];
                final isUser = m["isUser"] as bool;

                return Column(
                  crossAxisAlignment: isUser ? CrossAxisAlignment.end : CrossAxisAlignment.start,
                  children: [
                    Container(
                      margin: const EdgeInsets.symmetric(vertical: 4),
                      padding: const EdgeInsets.all(14),
                      constraints: BoxConstraints(maxWidth: MediaQuery.of(context).size.width * 0.78),
                      decoration: BoxDecoration(
                        color: isUser ? AppColors.secondary : AppColors.surfaceLowest,
                        borderRadius: BorderRadius.only(
                          topLeft: const Radius.circular(16),
                          topRight: const Radius.circular(16),
                          bottomLeft: Radius.circular(isUser ? 16 : 4),
                          bottomRight: Radius.circular(isUser ? 4 : 16),
                        ),
                        border: isUser ? null : Border.all(color: AppColors.outlineVariant.withOpacity(0.3)),
                        boxShadow: [
                          BoxShadow(
                            color: Colors.black.withOpacity(0.04),
                            blurRadius: 4,
                            offset: const Offset(0, 2),
                          ),
                        ],
                      ),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            m["text"],
                            style: TextStyle(
                              fontSize: 14,
                              color: isUser ? Colors.white : AppColors.onSurface,
                              height: 1.4,
                            ),
                          ),
                          const SizedBox(height: 4),
                          Align(
                            alignment: Alignment.bottomRight,
                            child: Text(
                              m["time"],
                              style: TextStyle(
                                fontSize: 10,
                                color: isUser ? Colors.white70 : AppColors.outline,
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                    if (!isUser && m["suggestions"] != null)
                      Padding(
                        padding: const EdgeInsets.only(top: 6, bottom: 10),
                        child: Wrap(
                          spacing: 6,
                          runSpacing: 6,
                          children: (m["suggestions"] as List<String>).map((sugg) {
                            return ActionChip(
                              label: Text(sugg, style: const TextStyle(fontSize: 11, color: AppColors.secondary)),
                              backgroundColor: AppColors.surfaceContainer,
                              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
                              onPressed: () => _handleSend(sugg),
                            );
                          }).toList(),
                        ),
                      ),
                  ],
                );
              },
            ),
          ),

          // Bottom Query Input
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
            color: AppColors.surfaceLowest,
            child: SafeArea(
              child: Row(
                children: [
                  IconButton(
                    icon: const Icon(Icons.mic, color: AppColors.secondary),
                    onPressed: () {
                      _handleSend("Atta ka stock kitna hai?");
                    },
                  ),
                  Expanded(
                    child: Container(
                      padding: const EdgeInsets.symmetric(horizontal: 14),
                      decoration: BoxDecoration(
                        color: AppColors.surfaceLow,
                        borderRadius: BorderRadius.circular(24),
                      ),
                      child: TextField(
                        controller: _msgCtrl,
                        onSubmitted: _handleSend,
                        decoration: const InputDecoration(
                          hintText: "Sarkar se poochiye (Hindi, English, Telugu)...",
                          hintStyle: TextStyle(fontSize: 13, color: AppColors.outline),
                          border: InputBorder.none,
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(width: 8),
                  IconButton(
                    icon: const Icon(Icons.send, color: AppColors.secondary),
                    onPressed: () => _handleSend(_msgCtrl.text),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}
