#!/usr/bin/env python3
"""
Wapas Demo Video Generator
==========================
Assembles a broadcast-quality 1080p demo video from native app screenshots:
1. Script to voice via edge-tts (en-IN-NeerjaExpressiveNeural)
2. Exact audio duration measurement via ffprobe
3. Canvas frame drawing via Pillow (1920x1080, gradient background, phone mockup, typography, narration card)
4. Slide video generation via ffmpeg concat demuxer with audio padding
5. Fast stream concatenation via ffmpeg concat demuxer without re-encoding
"""

import os
import sys
import json
import shutil
import subprocess
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter

BASE_DIR = Path("/home/sai-nikhil/wapas")
BUILD_DIR = BASE_DIR / "video_build"
AUDIO_DIR = BUILD_DIR / "audio"
FRAMES_DIR = BUILD_DIR / "frames"
SEGMENTS_DIR = BUILD_DIR / "segments"
SCREENSHOTS_DIR = BASE_DIR / "Screenshots"
OUTPUT_VIDEO = BASE_DIR / "wapas_demo_1080p.mp4"

EDGE_TTS_BIN = "/home/sai-nikhil/.local/bin/edge-tts"
VOICE = "en-IN-NeerjaExpressiveNeural"

SLIDES = [
    {
        "id": "01",
        "badge": "PAYTM BUILD FOR INDIA • TRACK 3: AUTONOMOUS REVENUE TEAMMATE",
        "title": "Meet Wapas: Autonomous Revenue Teammate",
        "subtitle": "AI proposes. Policy authorizes. Code executes. Paytm confirms.",
        "bullets": [
            "Recovers ₹7,000+ Cr annual retail losses from failed UPI & unpaid udhar",
            "Live 4G Paytm Soundbox telemetry with instant acoustic confirmation",
            "94.2% autonomous recovery rate under strict fail-closed merchant safety"
        ],
        "screenshot": "Screenshot_20261031-100950_wapas_app.png",
        "script": "Every month, over twenty crore UPI transactions fail across India, costing merchants thousands of crores in uncollected revenue. Meet Wapas, an autonomous revenue teammate built for Track 3 of the Paytm Hackathon. Wapas recovers lost revenue while the merchant sleeps: AI proposes, policy authorizes, code executes, and Paytm confirms."
    },
    {
        "id": "02",
        "badge": "FAST-TRACK POS & COUNTER BILLING",
        "title": "Unified POS Counter Checkout",
        "subtitle": "High-speed counter billing with live Paytm Soundbox heartbeat",
        "bullets": [
            "Real-time 4G Soundbox sync directly in the checkout header",
            "1-tap item catalogue with instant product search and pricing",
            "Integrated shortcuts to barcode scan, handwritten parchi OCR, and recovery"
        ],
        "screenshot": "Screenshot_20261031-100952_wapas_app.png",
        "script": "At the retail counter, speed is everything. The Wapas POS console gives shopkeepers an instant product catalog, live search, and a continuous heartbeat connection to the shop's 4G Paytm Soundbox, ensuring zero billing interruptions."
    },
    {
        "id": "03",
        "badge": "REAL-TIME CAMERA SCANNER",
        "title": "Instant Smartphone Barcode Scanner",
        "subtitle": "On-device camera vision replacing expensive hardware scanners",
        "bullets": [
            "Instant camera barcode recognition for rapid in-store item lookup",
            "Direct camera-to-cart integration with zero latency",
            "Seamless toggle between packaged item barcodes and paper parchi"
        ],
        "screenshot": "Screenshot_20261031-101025_wapas_app.png",
        "script": "Instead of forcing small merchants to buy costly handheld barcode scanners, Wapas turns their existing smartphone into a high-speed camera scanner. Barcodes are recognized in milliseconds and immediately populated into the active bill."
    },
    {
        "id": "04",
        "badge": "ORDER CHECKOUT & BILLING",
        "title": "Automated Cart & Bill Breakdown",
        "subtitle": "Itemized billing transparency with one-tap payment checkout",
        "bullets": [
            "Clear subtotal, itemized tax calculation, and net total breakdown",
            "Instant quantity adjustments and line-item deletions",
            "Single touchpoint to collect payment via UPI, cash, or credit ledger"
        ],
        "screenshot": "Screenshot_20261031-101018_wapas_app.png",
        "script": "With items added, the cart displays a clean, transparent breakdown of items, quantities, and taxes. The merchant verifies the total and proceeds to payment collection with a single tap."
    },
    {
        "id": "05",
        "badge": "SMART PAYMENT ORCHESTRATION",
        "title": "Payment Routing: Paytm QR & Khata",
        "subtitle": "Bridging instant digital settlement with managed credit",
        "bullets": [
            "Paytm Dynamic QR with automatic Soundbox audio broadcast",
            "Cash payment logging for instant offline reconciliation",
            "Add to Khata routing that hands off credit to the Recovery Tower"
        ],
        "screenshot": "Screenshot_20261031-101022_wapas_app.png",
        "script": "Merchants can collect payments through dynamic Paytm QR code, cash, or record it into the Khata credit ledger. When credit is chosen, Wapas automatically logs the customer and routes the unpaid balance directly into the AI recovery pipeline."
    },
    {
        "id": "06",
        "badge": "AUTONOMOUS REVENUE ENGINE",
        "title": "AI Recovery Control Tower",
        "subtitle": "Language adapts. Policy does not. 100% fail-closed safety.",
        "bullets": [
            "Continuously monitors pending credit across all customer accounts",
            "Drafts hyper-personalized reminders in Hindi, Telugu, and English",
            "Escalate only when it matters: shopkeeper authorizes with 1-tap"
        ],
        "screenshot": "Screenshot_20261031-100954_wapas_app.png",
        "script": "Here is the brain of Wapas: the AI Recovery Control Tower. The autonomous engine detects overdue balances and generates polite, relationship-preserving recovery messages. Because our policy is strictly fail-closed, the AI never touches money directly: the merchant reviews and authorizes dispatch with one simple tap."
    },
    {
        "id": "07",
        "badge": "DIGITAL KHATA LEDGER",
        "title": "Sarvam AI Powered Digital Khata",
        "subtitle": "Zero-dispute customer ledgers with multi-modal intelligence",
        "bullets": [
            "Real-time visibility over total outstanding dues of ₹10,870",
            "Deep integration with Sarvam-105B Indic foundation models",
            "Dual smart input: Scan Handwritten Parchi & Bolo aur Likho Voice"
        ],
        "screenshot": "Screenshot_20261031-100957_wapas_app.png",
        "script": "The Khata ledger digitizes traditional Indian bahi-khata books. Integrated with Sarvam-105B Indic intelligence, merchants get real-time visibility over total outstanding dues, backed by dual AI tools: handwritten parchi OCR scanning and spoken voice ledger entry."
    },
    {
        "id": "08",
        "badge": "ON-DEVICE VISION OCR",
        "title": "Scan & Fetch Handwritten Parchi",
        "subtitle": "Google ML Kit OCR converting paper scribbles to verified ledger entries",
        "bullets": [
            "Live camera capture or gallery upload of scribbled merchant chits",
            "Automatic extraction of customer name, item details, and bill total",
            "Interactive review and edit dialog before committing to ledger"
        ],
        "screenshot": "Screenshot_20261031-100959_wapas_app.png",
        "script": "Every Indian shopkeeper writes customer credit on small paper slips called parchi. With Scan and Fetch, the merchant simply snaps a photo. On-device ML Kit OCR reads handwritten text, fills in the customer and amount, and presents an editable review modal before saving."
    },
    {
        "id": "09",
        "badge": "INDIC VOICE INTELLIGENCE",
        "title": "Bolo aur Likho Voice Khata",
        "subtitle": "Speak naturally in Hindi, Telugu, Tamil, or Hinglish",
        "bullets": [
            "Natural voice dictation: 'Rao Garu took 300 rupees and paid 30 last month'",
            "Sarvam Indic parsing splits debit vs credit transactions accurately",
            "Built-in duplicate customer matching prevents split ledgers"
        ],
        "screenshot": "Screenshot_20261031-101001_wapas_app.png",
        "script": "With Bolo aur Likho, merchants record ledger updates just by speaking naturally: like 'Today Rao Garu took 300 rupees and paid 30.' Sarvam AI understands colloquial phrasing, splits credit and debit accurately, and automatically flags existing matching accounts."
    },
    {
        "id": "10",
        "badge": "CUSTOMER ACCOUNTS & RISK",
        "title": "Transparent Customer Account Ledgers",
        "subtitle": "We measure confirmed recoveries, not agent activity",
        "bullets": [
            "Per-customer balance sheets with complete transaction logs",
            "Individualized credit limits and dynamic grace period tracking",
            "1-tap WhatsApp statement delivery with embedded Paytm UPI links"
        ],
        "screenshot": "Screenshot_20261031-101003_wapas_app.png",
        "script": "Merchants can inspect any customer account at a glance, from Suresh Gupta to Rao Garu. Every past transaction is timestamped and auditable. Merchants can share statements over WhatsApp with an embedded Paytm payment link for immediate clearing."
    },
    {
        "id": "11",
        "badge": "SEAMLESS ONBOARDING",
        "title": "Instant Customer Account Creation",
        "subtitle": "Configurable credit caps to prevent bad debt before it happens",
        "bullets": [
            "Fast customer profile creation with phone and credit limits",
            "Automatic WhatsApp and SMS notification preferences",
            "Direct contact synchronization for frictionless communications"
        ],
        "screenshot": "Screenshot_20261031-101015_wapas_app.png",
        "script": "Adding a new customer takes just seconds. Merchants enter the customer name, phone number, and a prudent credit limit, ensuring financial discipline and risk control from day one."
    },
    {
        "id": "12",
        "badge": "SARKAR AI ASSISTANT",
        "title": "Sarkar AI Retail Copilot",
        "subtitle": "Conversational retail & inventory intelligence via Sarvam-105B",
        "bullets": [
            "Native multilingual support: English, Hinglish, Telugu, Tamil, Hindi",
            "Real microphone speech-to-text with conversational answers",
            "Actionable Kirana insights: top-selling items, low stock, and cash flow"
        ],
        "screenshot": "Screenshot_20261031-101006_wapas_app.png",
        "script": "Sarkar Copilot serves as an intelligent 24/7 retail copilot. Powered by Sarvam Indic AI, merchants can ask questions in English, Hinglish, Telugu, or Hindi, receiving instant insights into daily revenues, low stock warnings, and credit recovery status."
    },
    {
        "id": "13",
        "badge": "PAYTM HARDWARE ECOSYSTEM",
        "title": "Paytm Soundbox Live Broadcasts",
        "subtitle": "Real-time 4G telemetry and instant acoustic payment verification",
        "bullets": [
            "Continuous 4G signal telemetry, battery level, and sync tracking",
            "Live broadcast audit logs: 'Paytm par 245 rupaye praapt hue'",
            "Zero-fraud acoustic validation eliminating screenshot scams"
        ],
        "screenshot": "Screenshot_20261031-101008_wapas_app.png",
        "script": "Wapas seamlessly connects with Paytm Soundbox hardware. The app provides real-time 4G signal status, battery health, and a live broadcast log. Whenever a payment is completed, the Soundbox announces it aloud, completely eliminating customer payment fraud."
    },
    {
        "id": "14",
        "badge": "AUTONOMOUS REVENUE REVOLUTION",
        "title": "Wapas: Building for India",
        "subtitle": "Autonomous revenue teammate for 30 million Indian merchants",
        "bullets": [
            "Built for Paytm Build for India Hackathon - Track 3",
            "Full-stack integration: POS, Soundbox, Khata, and Sarvam Indic AI",
            "Autonomous recovery. Fail-closed safety. Guaranteed cash flow."
        ],
        "screenshot": "Screenshot_20261031-100948_wapas_app.png",
        "script": "Wapas bridges cutting-edge Indic AI with the trusted hardware of Paytm Soundbox. By automating credit tracking and fail-closed debt recovery, we empower India's 30 million retail merchants to run faster, safer, and more profitable stores. This is Wapas."
    }
]

def ensure_dirs():
    for d in [BUILD_DIR, AUDIO_DIR, FRAMES_DIR, SEGMENTS_DIR]:
        d.mkdir(parents=True, exist_ok=True)

def get_font(size, bold=False):
    candidates = [
        '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf' if bold else '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
        '/usr/share/fonts/truetype/ubuntu/Ubuntu[wdth,wght].ttf'
    ]
    for p in candidates:
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()

def wrap_text(draw, text, font, max_width):
    words = text.split()
    lines = []
    current_line = []
    for word in words:
        test_line = ' '.join(current_line + [word])
        bbox = draw.textbbox((0, 0), test_line, font=font)
        w = bbox[2] - bbox[0]
        if w <= max_width:
            current_line.append(word)
        else:
            if current_line:
                lines.append(' '.join(current_line))
                current_line = [word]
            else:
                lines.append(word)
    if current_line:
        lines.append(' '.join(current_line))
    return lines

def stage1_generate_voice():
    print("\n--- STAGE 1: Generating Voice Clips with edge-tts ---")
    for slide in SLIDES:
        sid = slide["id"]
        txt_path = AUDIO_DIR / f"slide_{sid}.txt"
        mp3_path = AUDIO_DIR / f"slide_{sid}.mp3"
        txt_path.write_text(slide["script"], encoding="utf-8")
        
        if not mp3_path.exists() or mp3_path.stat().st_size == 0:
            print(f"[{sid}] Generating voice narration: {mp3_path.name}")
            cmd = [
                EDGE_TTS_BIN,
                "--voice", VOICE,
                "--text", slide["script"],
                "--write-media", str(mp3_path)
            ]
            subprocess.run(cmd, check=True)
        else:
            print(f"[{sid}] Audio already exists: {mp3_path.name}")

def stage2_measure_durations():
    print("\n--- STAGE 2: Measuring Durations with ffprobe ---")
    durations = {}
    for slide in SLIDES:
        sid = slide["id"]
        mp3_path = AUDIO_DIR / f"slide_{sid}.mp3"
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "csv=p=0",
            str(mp3_path)
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        raw_dur = float(res.stdout.strip())
        durations[sid] = raw_dur
        print(f"[{sid}] Audio duration: {raw_dur:.2f}s (Total video duration: {raw_dur + 0.8:.2f}s with 0.8s breath padding)")
    return durations

def stage3_draw_frames():
    print("\n--- STAGE 3: Drawing 1080p Frames with Pillow ---")
    W, H = 1920, 1080

    font_badge = get_font(18, bold=True)
    font_title = get_font(50, bold=True)
    font_sub = get_font(26, bold=False)
    font_bullet = get_font(22, bold=False)
    font_card_head = get_font(18, bold=True)
    font_card_body = get_font(22, bold=False)

    for slide in SLIDES:
        sid = slide["id"]
        frame_path = FRAMES_DIR / f"slide_{sid}.png"
        print(f"[{sid}] Rendering 1920x1080 frame -> {frame_path.name}")

        canvas = Image.new('RGB', (W, H), color='#071120')
        draw = ImageDraw.Draw(canvas)

        # Gradient background (Midnight tech navy to deep obsidian)
        for y in range(H):
            factor = y / H
            r = int(5 + (9 - 5) * factor)
            g = int(14 + (21 - 14) * factor)
            b = int(32 + (50 - 32) * factor)
            draw.line([(0, y), (W, y)], fill=(r, g, b))

        # Ambient cyan & deep blue glow
        glow_layer = Image.new('RGBA', (W, H), (0, 0, 0, 0))
        g_draw = ImageDraw.Draw(glow_layer)
        g_draw.ellipse([(-180, -180), (820, 820)], fill=(0, 186, 242, 38))
        g_draw.ellipse([(W - 720, -180), (W + 280, 720)], fill=(0, 46, 110, 52))
        glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(110))
        canvas.paste(glow_layer, (0, 0), glow_layer)

        draw = ImageDraw.Draw(canvas)
        left_x = 90
        cur_y = 75

        # 1. Top Pill Badge
        badge_text = slide["badge"]
        bbox = draw.textbbox((0, 0), badge_text, font=font_badge)
        badge_w = bbox[2] - bbox[0] + 32
        badge_h = bbox[3] - bbox[1] + 16
        badge_img = Image.new('RGBA', (badge_w, badge_h), (0, 0, 0, 0))
        b_draw = ImageDraw.Draw(badge_img)
        b_draw.rounded_rectangle([(0, 0), (badge_w - 1, badge_h - 1)], radius=12, fill=(0, 186, 242, 30), outline=(0, 186, 242, 130), width=1)
        canvas.paste(badge_img, (left_x, cur_y), badge_img)
        draw.text((left_x + 16, cur_y + 8), badge_text, font=font_badge, fill='#00E5FF')
        cur_y += badge_h + 28

        # 2. Slide Title
        title_text = slide["title"]
        draw.text((left_x, cur_y), title_text, font=font_title, fill='#FFFFFF')
        bbox = draw.textbbox((0, 0), title_text, font=font_title)
        cur_y += (bbox[3] - bbox[1]) + 14

        # 3. Subtitle / Tagline
        sub_text = slide["subtitle"]
        sub_lines = wrap_text(draw, sub_text, font_sub, 1150)
        for sl in sub_lines:
            draw.text((left_x, cur_y), sl, font=font_sub, fill='#38BDF8')
            bbox = draw.textbbox((0, 0), sl, font=font_sub)
            cur_y += (bbox[3] - bbox[1]) + 8
        cur_y += 14

        # 4. Accent Bar (Paytm Cyan)
        accent = Image.new('RGB', (320, 4), color='#00BAF2')
        canvas.paste(accent, (left_x, cur_y))
        cur_y += 30

        # 5. Bullet points
        for b in slide["bullets"]:
            icon_box = [(left_x, cur_y + 4), (left_x + 22, cur_y + 26)]
            draw.rounded_rectangle(icon_box, radius=6, fill='#00BAF2')
            draw.text((left_x + 5, cur_y + 2), '✓', font=get_font(16, bold=True), fill='#071120')

            b_lines = wrap_text(draw, b, font_bullet, 1100)
            b_y = cur_y
            for bl in b_lines:
                draw.text((left_x + 36, b_y), bl, font=font_bullet, fill='#F1F5F9')
                bbox = draw.textbbox((0, 0), bl, font=font_bullet)
                b_y += (bbox[3] - bbox[1]) + 6
            cur_y = max(cur_y + 46, b_y + 10)
        cur_y += 18

        # 6. Narration Transcript Glass Card
        card_x = left_x
        card_y = cur_y
        card_w = 1180
        card_h = H - card_y - 70

        card_bg = Image.new('RGBA', (card_w, card_h), (0, 0, 0, 0))
        cb_draw = ImageDraw.Draw(card_bg)
        cb_draw.rounded_rectangle([(0, 0), (card_w - 1, card_h - 1)], radius=16, fill=(15, 23, 42, 215), outline=(51, 65, 85, 180), width=1)
        cb_draw.rounded_rectangle([(0, 0), (6, card_h - 1)], radius=3, fill=(0, 186, 242, 255))
        canvas.paste(card_bg, (card_x, card_y), card_bg)

        draw.text((card_x + 28, card_y + 18), '🎙️ AUDIO NARRATION TRANSCRIPT', font=font_card_head, fill='#00E5FF')

        script_lines = wrap_text(draw, slide["script"], font_card_body, card_w - 56)
        sc_y = card_y + 54
        for scl in script_lines:
            draw.text((card_x + 28, sc_y), scl, font=font_card_body, fill='#E2E8F0')
            bbox = draw.textbbox((0, 0), scl, font=font_card_body)
            sc_y += (bbox[3] - bbox[1]) + 8

        # 7. Right Mockup (Phone Chassis + Screenshot + Shadow)
        ss_file = SCREENSHOTS_DIR / slide["screenshot"]
        if ss_file.exists():
            ss = Image.open(ss_file).convert('RGBA')
            target_h = 920
            target_w = int(target_h * ss.width / ss.height)
            ss_resized = ss.resize((target_w, target_h), Image.Resampling.LANCZOS)

            phone_x = W - target_w - 90
            phone_y = (H - target_h) // 2

            # Drop Shadow
            shadow_w, shadow_h = target_w + 40, target_h + 40
            shadow = Image.new('RGBA', (shadow_w, shadow_h), (0, 0, 0, 0))
            s_draw = ImageDraw.Draw(shadow)
            s_draw.rounded_rectangle([(15, 15), (shadow_w - 15, shadow_h - 15)], radius=42, fill=(0, 0, 0, 185))
            shadow = shadow.filter(ImageFilter.GaussianBlur(25))
            canvas.paste(shadow, (phone_x - 20, phone_y - 10), shadow)

            # Bezel Chassis
            bezel = Image.new('RGBA', (target_w + 16, target_h + 16), (15, 23, 42, 255))
            b_draw = ImageDraw.Draw(bezel)
            b_draw.rounded_rectangle([(0, 0), (target_w + 15, target_h + 15)], radius=42, outline=(51, 65, 85, 255), width=3)
            canvas.paste(bezel, (phone_x - 8, phone_y - 8), bezel)

            # Screen mask
            mask = Image.new('L', (target_w, target_h), 0)
            mask_draw = ImageDraw.Draw(mask)
            mask_draw.rounded_rectangle([(0, 0), (target_w, target_h)], radius=36, fill=255)
            canvas.paste(ss_resized, (phone_x, phone_y), mask)

        canvas.save(frame_path)

def stage4_make_slide_videos(durations):
    print("\n--- STAGE 4: Making Individual Slide MP4s (30 fps CFR) with ffmpeg ---")
    for slide in SLIDES:
        sid = slide["id"]
        frame_path = FRAMES_DIR / f"slide_{sid}.png"
        mp3_path = AUDIO_DIR / f"slide_{sid}.mp3"
        seg_path = SEGMENTS_DIR / f"slide_{sid}.mp4"

        dur = durations[sid]
        total_dur = dur + 0.8  # 0.8s breath padding

        print(f"[{sid}] Rendering segment: {seg_path.name} (length: {total_dur:.2f}s @ 30 fps)")
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-framerate", "30", "-i", str(frame_path),
            "-i", str(mp3_path),
            "-af", "apad=pad_dur=0.8",
            "-t", f"{total_dur:.3f}",
            "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-r", "30", "-crf", "20",
            "-c:a", "aac", "-ar", "44100", "-ac", "2",
            str(seg_path)
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True)

def stage5_join_videos():
    print("\n--- STAGE 5: Concatenating All Slides with Zero Re-encoding ---")
    concat_list_file = BUILD_DIR / "concat_segments.txt"
    with open(concat_list_file, "w", encoding="utf-8") as f:
        for slide in SLIDES:
            sid = slide["id"]
            seg_path = SEGMENTS_DIR / f"slide_{sid}.mp4"
            f.write(f"file '{seg_path.resolve()}'\n")

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(concat_list_file),
        "-c", "copy",
        str(OUTPUT_VIDEO)
    ]
    subprocess.run(cmd, check=True)
    print(f"Concatenation finished: {OUTPUT_VIDEO}")

def stage6_verify():
    print("\n--- STAGE 6: Verification & Output Metrics ---")
    if not OUTPUT_VIDEO.exists():
        print("ERROR: Output video was not created!")
        sys.exit(1)

    file_size_mb = OUTPUT_VIDEO.stat().st_size / (1024 * 1024)
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration:stream=width,height,codec_name,r_frame_rate",
        "-of", "json",
        str(OUTPUT_VIDEO)
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    meta = json.loads(res.stdout)
    
    duration = float(meta["format"]["duration"])
    minutes = int(duration // 60)
    seconds = int(duration % 60)

    print("====================================================")
    print(f"🎬 DEMO VIDEO CREATED SUCCESSFULLY!")
    print(f"📁 Path: {OUTPUT_VIDEO}")
    print(f"⏱️ Duration: {minutes}m {seconds}s ({duration:.2f} seconds)")
    print(f"💾 File Size: {file_size_mb:.2f} MB")
    print(f"🎞️ Slides Count: {len(SLIDES)}")
    for stream in meta.get("streams", []):
        codec = stream.get("codec_name")
        w = stream.get("width")
        h = stream.get("height")
        if w and h:
            print(f"📺 Video Stream: {codec} @ {w}x{h}, {stream.get('r_frame_rate')} fps")
        else:
            print(f"🔊 Audio Stream: {codec}")
    print("====================================================")

def main():
    ensure_dirs()
    stage1_generate_voice()
    durations = stage2_measure_durations()
    stage3_draw_frames()
    stage4_make_slide_videos(durations)
    stage5_join_videos()
    stage6_verify()

if __name__ == "__main__":
    main()
