"""Customer message templates.

Written once, translated once, checked by a native speaker before the demo.
At run time only the placeholders change, so a bad translation can never be
generated live. The agent picks a template id; it never writes the text.
"""
LANG_NAMES = {"hi": "Hindi", "kn": "Kannada", "ta": "Tamil", "te": "Telugu", "en": "English"}

TEMPLATES: dict[str, dict[str, str]] = {
    "bank_issue_v1": {
        "en": "Hello {name}, your ₹{amount} payment to {merchant} could not be completed because of a bank issue. You can pay again here: {link}. Reply STOP to opt out.",
        "hi": "नमस्ते {name} जी, बैंक की तकनीकी समस्या के कारण {merchant} को आपका ₹{amount} का भुगतान पूरा नहीं हो पाया। आप यहाँ दोबारा भुगतान कर सकते हैं: {link}। संदेश बंद करने के लिए STOP भेजें।",
        "kn": "ನಮಸ್ಕಾರ {name}, ಬ್ಯಾಂಕ್ ಸಮಸ್ಯೆಯಿಂದ {merchant} ಗೆ ನಿಮ್ಮ ₹{amount} ಪಾವತಿ ಪೂರ್ಣಗೊಂಡಿಲ್ಲ. ಇಲ್ಲಿ ಮತ್ತೆ ಪಾವತಿಸಬಹುದು: {link}. ಸಂದೇಶಗಳನ್ನು ನಿಲ್ಲಿಸಲು STOP ಕಳುಹಿಸಿ.",
        "ta": "வணக்கம் {name}, வங்கிக் கோளாறு காரணமாக {merchant}-க்கான உங்கள் ₹{amount} கட்டணம் நிறைவடையவில்லை. இங்கே மீண்டும் செலுத்தலாம்: {link}. செய்திகளை நிறுத்த STOP அனுப்பவும்.",
        "te": "నమస్తే {name} గారు, బ్యాంక్ సమస్య వల్ల {merchant} కు మీ ₹{amount} చెల్లింపు పూర్తి కాలేదు. ఇక్కడ మళ్ళీ చెల్లించవచ్చు: {link}. సందేశాలు ఆపడానికి STOP పంపండి.",
    },
    "retry_later_v1": {
        "en": "Hello {name}, your ₹{amount} payment to {merchant} was not completed. You can pay whenever convenient here: {link}. Reply STOP to opt out.",
        "hi": "नमस्ते {name} जी, {merchant} को आपका ₹{amount} का भुगतान पूरा नहीं हो पाया। अपनी सुविधा के अनुसार यहाँ भुगतान करें: {link}। संदेश बंद करने के लिए STOP भेजें।",
        "kn": "ನಮಸ್ಕಾರ {name}, {merchant} ಗೆ ನಿಮ್ಮ ₹{amount} ಪಾವತಿ ಪೂರ್ಣಗೊಂಡಿಲ್ಲ. ನಿಮಗೆ ಅನುಕೂಲವಾದಾಗ ಇಲ್ಲಿ ಪಾವತಿಸಿ: {link}. ಸಂದೇಶಗಳನ್ನು ನಿಲ್ಲಿಸಲು STOP ಕಳುಹಿಸಿ.",
        "ta": "வணக்கம் {name}, {merchant}-க்கான உங்கள் ₹{amount} கட்டணம் நிறைவடையவில்லை. உங்களுக்கு வசதியான நேரத்தில் இங்கே செலுத்தவும்: {link}. செய்திகளை நிறுத்த STOP அனுப்பவும்.",
        "te": "నమస్తే {name} గారు, {merchant} కు మీ ₹{amount} చెల్లింపు పూర్తి కాలేదు. మీకు వీలైనప్పుడు ఇక్కడ చెల్లించండి: {link}. సందేశాలు ఆపడానికి STOP పంపండి.",
    },
    "reminder_v1": {
        "en": "Reminder: your ₹{amount} payment to {merchant} is still pending. Pay here: {link}. Reply STOP to opt out.",
        "hi": "याद दिलाना: {merchant} को आपका ₹{amount} का भुगतान अभी बाकी है। यहाँ भुगतान करें: {link}। संदेश बंद करने के लिए STOP भेजें।",
        "kn": "ಜ್ಞಾಪನೆ: {merchant} ಗೆ ನಿಮ್ಮ ₹{amount} ಪಾವತಿ ಇನ್ನೂ ಬಾಕಿ ಇದೆ. ಇಲ್ಲಿ ಪಾವತಿಸಿ: {link}. ಸಂದೇಶಗಳನ್ನು ನಿಲ್ಲಿಸಲು STOP ಕಳುಹಿಸಿ.",
        "ta": "நினைவூட்டல்: {merchant}-க்கான உங்கள் ₹{amount} கட்டணம் இன்னும் நிலுவையில் உள்ளது. இங்கே செலுத்தவும்: {link}. செய்திகளை நிறுத்த STOP அனுப்பவும்.",
        "te": "గుర్తు చేస్తున్నాం: {merchant} కు మీ ₹{amount} చెల్లింపు ఇంకా పెండింగ్‌లో ఉంది. ఇక్కడ చెల్లించండి: {link}. సందేశాలు ఆపడానికి STOP పంపండి.",
    },
    "thanks_v1": {
        "en": "Thank you {name}! Your ₹{amount} payment to {merchant} has been received.",
        "hi": "धन्यवाद {name} जी! {merchant} को आपका ₹{amount} का भुगतान मिल गया है।",
        "kn": "ಧನ್ಯವಾದಗಳು {name}! {merchant} ಗೆ ನಿಮ್ಮ ₹{amount} ಪಾವತಿ ತಲುಪಿದೆ.",
        "ta": "நன்றி {name}! {merchant}-க்கான உங்கள் ₹{amount} கட்டணம் பெறப்பட்டது.",
        "te": "ధన్యవాదాలు {name} గారు! {merchant} కు మీ ₹{amount} చెల్లింపు అందింది.",
    },
}

CUSTOMER_TEMPLATES = {"bank_issue_v1", "retry_later_v1"}


def fmt_inr(paise: int) -> str:
    rupees = paise // 100
    s = str(rupees)
    if len(s) > 3:  # Indian grouping: 1,23,456
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join(parts) + "," + tail
    return s


def render(template: str, language: str, *, name: str, amount_paise: int, merchant: str, link: str = "") -> str:
    lang = language if language in LANG_NAMES else "en"
    t = TEMPLATES[template].get(lang) or TEMPLATES[template]["en"]
    first = name.split()[0]
    return t.format(name=first, amount=fmt_inr(amount_paise), merchant=merchant, link=link)
